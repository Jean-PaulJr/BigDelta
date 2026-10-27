"""Local, evidence-based calculation revision candidates and native PDF callouts.

No external AI requests are made. Candidates require human disposition. Scanned
pages and changes to drawings/formulas without readable labels are coverage gaps.
"""
from collections import defaultdict
from difflib import SequenceMatcher
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
import re
import unicodedata

import pymupdf as fitz

PRIORITIES = {
    'acceptance': (1, 'Acceptance changed'),
    'assumption': (2, 'Fundamental assumption changed'),
    'loading': (3, 'Loading condition changed'),
    'removed_check': (4, 'Check disappeared'),
    'propagation': (5, 'Input without downstream update'),
    'geometry_material': (6, 'Geometry or material changed'),
    'conclusion': (7, 'Conclusion conflicts with results'),
    'result': (8, 'Calculated result changed'),
    'other': (9, 'Other content change'),
}
NUMBER = re.compile(r'(?<![A-Za-z])[-+]?\d+(?:[.,]\d+)*(?:[eE][-+]?\d+)?')
NODE = re.compile(r'\b(?:nodal|node)\s*[-_ ]?loads?\b', re.I)
SECTION_END = re.compile(r'^(?:repeat loads|wind loads|beam loads|temperature loads|selfweights|notional loads|reactions|node displacements|utilization ratio|failed members|sections|materials|supports|load case table|primary load cases|design criteria|load combinations)\b', re.I)
STATUS = re.compile(r'\b(PASS(?:ED)?|FAIL(?:ED|ING)?|OK|NG)\b["\u201d]?\s*$', re.I)
METADATA = re.compile(r'(software licensed|connected user|staad\.pro|^date time|\b\d{1,2}[-/]\w{2,9}[-/]\d{2,4}\b|^\d+ of \d+$|\.(?:mcdx|xlsx|std)\b)', re.I)
LOADING = re.compile(r'(wind\s*(?:speed|velocity)|\bmph\b|\bSDS\b|\bSD1\b|seismic\s*(?:coefficient|parameter)|(?:ice|icing|snow)\s*(?:load|thickness)|fault\s*current|equipment\s*weight|insul[_ ]*weight|load\s*combination|(?:dead|live)\s*load\s*(?:input|criteria))', re.I)
ASSUMPTION = re.compile(r'(\bpinned\b|\bfixed\b|\bfixity\b|\borientation\b|\brelease\b|effective\s*length|second.order|stiffness\s*modifier|analysis\s*method|load.sharing|\bQAB\b)', re.I)
RESULT = re.compile(r'(utilization|deflection|demand|reaction|capacity|allowable|\bmax\b|\b[TCV]max\b|\bPbolt|max_|required|reqd|_check|\bcheck\b|_allowable)', re.I)
GEOMETRY = re.compile(r'(\bFy\b|\bFu\b|grade|\bA36\b|F1554|\bHSS\b|HSS\d|\bW\d+X|material|diameter|thickness|height|span|length|\bcolumn\b|main[_ ]beam|anchor[_ ]bolts|plate[_ ]thick|\bRows[xz]\b|\bS[xz]\b)', re.I)


def file_sha256(path):
    h = sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def clean(text):
    return ' '.join(unicodedata.normalize('NFKC', text).split())


def key(text):
    text = STATUS.sub(' <status>', text)
    return re.sub(r'[^a-z_]+', '', NUMBER.sub('#', text).lower())


def status(text):
    # An equation containing both possible outcomes is not a reported result.
    if re.search(r'\bif\s*\(?', text, re.I):
        return None
    m = STATUS.search(text)
    if not m:
        return None
    return 'pass' if m[1].upper() in ('PASS', 'PASSED', 'OK') else 'fail'


def classify(text, removed=False):
    if NODE.search(text):
        return None
    if removed and re.search(r'check|verification|stability', text, re.I):
        return 'removed_check'
    if LOADING.search(text):
        return 'loading'
    if ASSUMPTION.search(text):
        return 'assumption'
    if RESULT.search(text):
        return 'result'
    if GEOMETRY.search(text):
        return 'geometry_material'
    return 'other'


def _section_names(doc):
    starts = {p - 1: clean(title) for level, title, p in doc.get_toc() if level == 1}
    result, current = [], 'Document'
    for i in range(len(doc)):
        current = starts.get(i, current)
        result.append(current if starts else f'Unbookmarked page {i + 1}')
    return result


def _fingerprints(doc, progress, offset, total):
    """Check page streams and reused XObjects/images without interpreting node loads."""
    cache, result = {}, []
    def digest(xref):
        if xref not in cache:
            cache[xref] = sha256(doc.xref_stream(xref) or b'').digest()
        return cache[xref]
    for i, page in enumerate(doc):
        h = sha256(page.read_contents())
        h.update(str((list(page.mediabox), list(page.cropbox), page.rotation)).encode())
        for obj in page.get_xobjects():
            h.update(digest(obj[0]))
        for image in page.get_images(full=True):
            h.update(str(image[2:7]).encode())
            h.update(digest(image[0]))
            if image[1]:
                h.update(digest(image[1]))
        result.append(h.hexdigest())
        if progress and (i % 50 == 0 or i == len(doc) - 1):
            progress(min(55, int((offset + i + 1) / total * 55)), 'Matching document pages')
    return result


def _node_bookmark_state(doc):
    """Whether a node-load table was active before the beginning of each page."""
    entries = [(p - 1, title) for level, title, p in doc.get_toc() if level >= 2]
    entries.sort(key=lambda x: x[0])
    result, cursor, active = [], 0, False
    for page in range(len(doc)):
        while cursor < len(entries) and entries[cursor][0] < page:
            active = bool(NODE.search(entries[cursor][1]))
            cursor += 1
        result.append(active)
    return result


def _rows(page, node_active=False):
    # TEXTFLAGS_TEXT excludes image bytes and annotation text. Visual rows pair
    # Mathcad labels with values when they share a baseline.
    raw = []
    for block in page.get_text('dict', flags=fitz.TEXTFLAGS_TEXT)['blocks']:
        for line in block.get('lines', []):
            spans = line['spans']
            text = clean(''.join(s['text'] for s in spans))
            if text:
                raw.append((line['bbox'], text))
    raw.sort(key=lambda item: (round(item[0][1], 0), item[0][0]))
    groups = []
    for rect, text in raw:
        if groups and abs(rect[1] - groups[-1][0][1]) <= 2:
            groups[-1][1].append((rect[0], text))
            groups[-1][0] |= fitz.Rect(rect)
        else:
            groups.append([fitz.Rect(rect), [(rect[0], text)]])
    rows, excluded = [], 0
    for rect, parts in groups:
        text = clean(' '.join(t for _, t in sorted(parts)))
        text = re.sub(r'\.{3,}\s*\d+\s*$', '', text).strip()
        if NODE.search(text):
            node_active = True
            excluded += 1
            continue
        if node_active and SECTION_END.search(text):
            node_active = False
        if node_active:
            excluded += 1
            continue
        if re.match(r'^(?:node|joint)\s*\d+\b', text, re.I) and not re.search(r'reaction|support', text, re.I):
            excluded += 1
            continue
        if rect.y0 > page.rect.height - 26 or METADATA.search(text):
            continue
        if not re.search(r'[A-Za-z]{2}', text) or not key(text):
            continue  # bare numeric tables are not interpreted as engineering facts
        rows.append({'text': text, 'rect': list(rect), 'key': key(text)})
    return rows, excluded


def _candidate(old, new, old_page, new_page, section, category=None):
    before, after = old['text'] if old else '', new['text'] if new else ''
    category = category or classify(after or before, removed=not new)
    if category is None:
        return None
    changed_status = old and new and status(before) and status(after) and status(before) != status(after)
    if changed_status:
        category = 'acceptance'
    label = PRIORITIES[category][1]
    if old and new:
        summary = f'Earlier: {before}\nNewer: {after}'
        title = f'{label}: {after[:100]}'
    elif new:
        summary = f'Newly listed content: {after}\nConfirm whether this is added scope or relocated/reformatted calculation content.'
        title = f'Added content: {after[:100]}'
    else:
        summary = f'Earlier content not matched in this changed section: {before}\nConfirm removal versus replacement or relocation before treating this as a disappeared check.'
        title = f'Unmatched earlier content: {before[:100]}'
    return dict(category=category, priority=PRIORITIES[category][0], title=title,
                summary=summary, earlier_page=old_page, newer_page=new_page,
                rect=(new or old)['rect'], section=section, disposition='pending',
                confidence='candidate', before=before, after=after,
                kind='changed' if old and new else ('added' if new else 'unmatched_earlier'))


def compare_calculations(earlier_path, newer_path, progress=None):
    """Return prioritized candidates, grouped result changes, and coverage gaps.

    The caller supplies revision direction explicitly. Metadata never silently
    reverses the user's earlier/newer selections.
    """
    findings, grouped, coverage = [], [], []
    unclassified = []
    strengths = {'earlier': defaultdict(list), 'newer': defaultdict(list)}
    excluded_rows = 0
    with fitz.open(earlier_path) as old, fitz.open(newer_path) as new:
        if old.needs_pass or new.needs_pass or not len(old) or not len(new):
            raise ValueError('Choose two readable, unencrypted PDFs with at least one page.')
        sections = _section_names(new)
        old_sections = _section_names(old)
        old_node, new_node = _node_bookmark_state(old), _node_bookmark_state(new)
        total = len(old) + len(new)
        ah = _fingerprints(old, progress, 0, total)
        bh = _fingerprints(new, progress, len(old), total)
        opcodes = SequenceMatcher(None, ah, bh, autojunk=False).get_opcodes()
        unchanged = 0
        for op_index, (tag, a1, a2, b1, b2) in enumerate(opcodes):
            if tag == 'equal':
                unchanged += a2 - a1
                continue
            if progress:
                progress(55 + int(op_index / max(1, len(opcodes)) * 35), 'Finding calculation changes')
            # Match labeled facts across a changed run, accommodating inserted,
            # removed and repaginated calculation sheets without ordinal pairing.
            earlier, later = [], []
            for doc, start, end, node_states, target in [(old, a1, a2, old_node, earlier), (new, b1, b2, new_node, later)]:
                for index in range(start, end):
                    rows, skipped = _rows(doc[index], node_states[index])
                    excluded_rows += skipped
                    if not rows and not skipped:
                        coverage.append({'side': 'earlier' if doc is old else 'newer', 'page': index + 1,
                                         'reason': 'No usable text: scanned, blank, or graphics-only page; inspect visually.'})
                    names = old_sections if doc is old else sections
                    side = 'earlier' if doc is old else 'newer'
                    for row in rows:
                        if re.search(r'yield\s+strength\s+of\s+bolts', row['text'], re.I):
                            m = re.search(r'\bFy\b.*?([0-9]+(?:\.[0-9]+)?)\s*ksi', row['text'], re.I)
                            if m:
                                strengths[side][names[index]].append((float(m[1]), index + 1, row))
                    target.extend(dict(row, page=index + 1, scope=names[index]) for row in rows)
            old_by_key = defaultdict(list)
            for index, row in enumerate(earlier):
                old_by_key[(row['scope'], row['key'])].append(index)
            used = set()
            # Consume exact matches first, including facts moved to another page.
            pending = []
            for row in later:
                exact = next((i for i in old_by_key[(row['scope'], row['key'])] if i not in used and earlier[i]['text'] == row['text']), None)
                if exact is not None:
                    used.add(exact)
                else:
                    pending.append(row)
            run_findings = []
            for row in pending:
                candidates = [i for i in old_by_key[(row['scope'], row['key'])] if i not in used]
                if candidates:
                    best = max(candidates, key=lambda i: SequenceMatcher(None, earlier[i]['text'], row['text'], autojunk=False).ratio())
                    used.add(best)
                    before = earlier[best]
                    f = _candidate(before, row, before['page'], row['page'], sections[row['page'] - 1])
                else:
                    f = _candidate(None, row, None, row['page'], sections[row['page'] - 1])
                if f:
                    run_findings.append(f)
            for i, row in enumerate(earlier):
                if i in used:
                    continue
                anchor = min(b1 + 1, len(new))
                f = _candidate(row, None, row['page'], anchor, sections[anchor - 1])
                if f:
                    # A deleted item has no new source rectangle: anchor its
                    # callout to the first surviving page at the deletion point.
                    f['rect'] = [40, 40, min(250, new[anchor - 1].rect.width - 30), 70]
                    run_findings.append(f)
            # A difference consisting only of images/geometry is a coverage gap,
            # never a fabricated semantic finding or an automatic all-clear.
            if not run_findings and (a2 > a1 or b2 > b1):
                coverage.append({'side': 'both', 'earlier_pages': [a1 + 1, a2], 'newer_pages': [b1 + 1, b2],
                                 'reason': 'Changed page content has no matched labeled-text change; review graphics, formulas or formatting visually.'})
            for f in run_findings:
                text = f['after'] or f['before']
                prose = len(re.findall(r'\b[A-Za-z]{3,}\b', text)) >= 5
                value = bool(re.search(r'[-+]?\d+(?:\.\d+)?\s*(?:ksi|kip|in\b|ft\b|lbf|mph|%)', text, re.I))
                if (f['category'] == 'other' and not prose) or (f['category'] in ('geometry_material', 'result') and not value and not status(text) and not re.search(r'check|HSS\d|W\d+X', text, re.I)):
                    unclassified.append(f)
                else:
                    findings.append(f)
        for section, items in strengths['newer'].items():
            earlier_values = {value for value, _, _ in strengths['earlier'].get(section, [])}
            newer_values = {value for value, _, _ in items}
            if len(newer_values) > 1 and newer_values != earlier_values:
                reference = items[0]
                for value, number, row in items[1:]:
                    if value == reference[0]:
                        continue
                    f = _candidate(None, row, None, number, section, 'propagation')
                    f['title'] = 'Potential inconsistent bolt yield strength'
                    f['summary'] = f'The revised section prints bolt Fy={reference[0]:g} ksi on p{reference[1]} and Fy={value:g} ksi on p{number}. Earlier changed-section values were {sorted(earlier_values)} ksi. Confirm whether these refer to the same anchor material and reconcile dependent checks.'
                    findings.append(f)

        # A loading update suppresses only downstream numerical results in the
        # same calculation section. Acceptance transitions are never suppressed.
        load_sections = {f['section'] for f in findings if f['category'] == 'loading' and f['kind'] == 'changed'}
        visible = []
        for f in findings:
            if f['category'] == 'result' and f['section'] in load_sections:
                f['grouping_reason'] = 'Corresponding calculation section has an applied-load update.'
                grouped.append(f)
            else:
                visible.append(f)
        # Flag possible conclusion conflicts only against explicit reported
        # failures on the same new page (not formulas listing both outcomes).
        failures = {f['newer_page'] for f in visible if status(f['after']) == 'fail'}
        for page_number in failures:
            rows, _ = _rows(new[page_number - 1], new_node[page_number - 1])
            for row in rows:
                if re.search(r'\b(?:conclusion|summary)\b.*\bacceptable\b', row['text'], re.I):
                    f = _candidate(None, row, None, page_number, sections[page_number - 1], 'conclusion')
                    f['title'] = 'Potential conclusion conflict'
                    f['summary'] = f'Newer summary says: {row["text"]}\nAn explicit failing result is also reported on this page. Reconcile the conclusion with the detailed check.'
                    visible.append(f)
        visible.sort(key=lambda f: (f['priority'], f['newer_page'], f['rect'][1]))
        if len(visible) > 3000:
            coverage.append({'side': 'both', 'reason': f'{len(visible) - 3000} additional candidates exceed the 3,000-item review limit. Review smaller calculation sections separately.'})
            visible = visible[:3000]
        for index, f in enumerate(visible, 1):
            f['id'] = f'F{index:04d}'
        for index, f in enumerate(grouped, 1):
            f['id'] = f'G{index:04d}'
        return dict(findings=visible, grouped_results=grouped, coverage_gaps=coverage, unclassified_changes=unclassified,
                    earlier_sha256=file_sha256(earlier_path), newer_sha256=file_sha256(newer_path),
                    earlier_pages=len(old), newer_pages=len(new), unchanged_pages=unchanged,
                    excluded_node_load_rows=excluded_rows,
                    rules={'node_loads': 'excluded', 'callouts': 'one per selected finding',
                           'priorities': {k: {'order': v[0], 'label': v[1]} for k, v in PRIORITIES.items()}},
                    limitations=['Rule-based candidates require engineering review.',
                                 'No OCR, model rerun, catalog verification, or hidden-formula analysis.',
                                 'Unlabeled equations, numeric-only tables and semantic equivalence may require manually added findings.',
                                 'Scope grouping uses top-level PDF bookmarks; review sections when bookmarks are missing or unsuitable.'])


def validate_findings(findings, page_count):
    if not isinstance(findings, list) or len(findings) > 3000:
        raise ValueError('Provide no more than 3,000 findings.')
    seen = set()
    for f in findings:
        if not isinstance(f, dict) or not isinstance(f.get('id'), str) or not f['id'] or f['id'] in seen:
            raise ValueError('Each finding must have a unique ID.')
        seen.add(f['id'])
        if f.get('category') not in PRIORITIES or f.get('disposition') not in ('pending', 'include', 'exclude'):
            raise ValueError('Choose a valid category and disposition.')
        if not isinstance(f.get('newer_page'), int) or not 1 <= f['newer_page'] <= page_count:
            raise ValueError('Finding page is outside the newer document.')
        for field, limit in [('title', 240), ('summary', 6000)]:
            if not isinstance(f.get(field), str) or not f[field].strip() or len(f[field]) > limit:
                raise ValueError(f'Finding {field} is required (maximum {limit} characters).')
        if NODE.search(f['title']):
            raise ValueError('Node-load discrepancies are excluded from calculation review.')
        f['priority'] = PRIORITIES[f['category']][0]
    return findings


def _wrap(text, font, size, width):
    lines = []
    for paragraph in text.split('\n'):
        if not paragraph.strip():
            lines.append('')
            continue
        line = ''
        for word in paragraph.split():
            # Break unusually long equation tokens so callouts cannot clip.
            while font.text_length(word, fontsize=size) > width:
                cut = len(word) - 1
                while font.text_length(word[:cut], fontsize=size) > width:
                    cut -= 1
                if line:
                    lines.append(line)
                    line = ''
                lines.append(word[:cut])
                word = word[cut:]
            trial = (line + ' ' + word).strip()
            if line and font.text_length(trial, fontsize=size) > width:
                lines.append(line)
                line = word
            else:
                line = trial
        lines.append(line)
    return lines


def _export_callouts_to_path(newer_path, output_path, findings):
    """Write one editable FreeTextCallout per included finding, preserving sources.

    A review margin is added only to affected pages and widens as needed.
    Unusual page geometry is rejected rather than moving existing annotations.
    """
    if Path(newer_path).resolve() == Path(output_path).resolve():
        raise ValueError('Export must be a separate copy of the source PDF.')
    with fitz.open(newer_path) as doc:
        validate_findings(findings, len(doc))
        selected = [dict(f) for f in findings if f['disposition'] == 'include']
        source_page_count = len(doc)
        export_id = uuid4().hex
        if not selected:
            raise ValueError('Include at least one reviewed finding before exporting.')
        by_page = defaultdict(list)
        for f in selected:
            by_page[f['newer_page']].append(f)
        font, size = fitz.Font('helv'), 10
        for number, items in by_page.items():
            page = doc[number - 1]
            if page.rotation or page.cropbox != page.mediabox or page.mediabox.x0 or page.mediabox.y0:
                raise ValueError(f'Page {number} has rotation or a nonstandard cropbox. Normalize this PDF before callout export.')
            w, h = page.rect.width, page.rect.height
            items.sort(key=lambda f: (f['priority'], f['id']))
            for margin in range(420, 1801, 120):
                for f in items:
                    text = f'{f["id"]} | {PRIORITIES[f["category"]][1]}\n\n{f["title"]}\n{f["summary"]}\nEarlier p{f.get("earlier_page") or "unmatched"} -> newer p{number}.'
                    text = unicodedata.normalize('NFKC', text).encode('cp1252', 'replace').decode('cp1252')
                    f['_lines'] = _wrap(text, font, size, margin - 65)
                    f['_height'] = len(f['_lines']) * size * 1.35 + 26
                if 52 + sum(f['_height'] + 14 for f in items) <= h:
                    break
            else:
                raise ValueError(f'Page {number} has too many callouts to fit legibly. Include fewer findings or shorten descriptions.')
            page.set_mediabox(fitz.Rect(0, 0, w + margin, h))
            page.set_cropbox(fitz.Rect(0, 0, w + margin, h))
            page.insert_text((w + 28, 19), 'BIGDELTA | CALCULATION REVIEW', fontsize=9, fontname='hebo')
            y = 32
            for f in items:
                r = fitz.Rect(f.get('rect') or (40, 40, min(w - 25, 250), 70)) & fitz.Rect(0, 0, w, h)
                if r.is_empty or r.is_infinite:
                    raise ValueError('Finding location is outside its source page.')
                mark = page.add_rect_annot(r)
                mark.set_colors(stroke=(0.86, 0.36, 0.12))
                mark.set_border(width=.8)
                mark.set_info(title='BigDelta', subject=f['id'] + ' - affected area')
                mark.update()
                box = fitz.Rect(w + 28, y, w + margin - 16, y + f['_height'])
                tip = fitz.Point(r.x1, min(h - 10, r.y1 + 2))
                annot = page.add_freetext_annot(box, '\n'.join(f['_lines']), fontsize=size,
                    fontname='Helv', fill_color=(1, .99, .94), text_color=(.08, .13, .17),
                    border_width=.8, callout=[tip, fitz.Point(w + 12, tip.y), fitz.Point(box.x0, y + 20)],
                    line_end=fitz.PDF_ANNOT_LE_OPEN_ARROW)
                annot.set_info(title='BigDelta', subject=f['id'] + ' - ' + f['title'])
                doc.xref_set_key(annot.xref, 'NM', fitz.get_pdf_str(f'BigDelta-{export_id}-{f["id"]}'))
                annot.update()
                annot.set_flags(fitz.PDF_ANNOT_IS_PRINT)
                y += f['_height'] + 14
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        doc.save(output_path, garbage=3, deflate=True)
    # Verify actual native intent, leaders and rendered text, not just appearance.
    with fitz.open(output_path) as result:
        callouts = []
        for number in by_page:
            page = result[number - 1]
            for annot in page.annots() or []:
                if annot.type[1] == 'FreeText' and annot.info.get('id', '').startswith(f'BigDelta-{export_id}-'):
                    if result.xref_get_key(annot.xref, 'IT')[1] != '/FreeTextCallout':
                        raise ValueError('Exported annotation is not a native PDF callout.')
                    if not page.rect.contains(annot.rect) or not annot.get_text().strip() or annot.info['content'].split()[-1] not in annot.get_text().split():
                        raise ValueError('Exported callout is outside the page or has no visible text.')
                    callouts.append(annot)
        if len(callouts) != len(selected):
            raise ValueError('Callout count does not match the selected findings.')
    return {'callout_count': len(selected), 'page_count': source_page_count}


def export_callouts(newer_path, output_path, findings):
    """Atomically create a new reviewed copy; never overwrite an existing file."""
    output = Path(output_path).resolve()
    if output == Path(newer_path).resolve() or output.exists():
        raise ValueError('Choose a new output filename; existing files are not overwritten.')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f'.{output.stem}.{uuid4().hex}.tmp.pdf')
    try:
        result = _export_callouts_to_path(newer_path, temporary, findings)
        temporary.replace(output)
        return result
    finally:
        temporary.unlink(missing_ok=True)


def main():
    """Two-step CLI: compare to JSON, review dispositions, export selected items."""
    import argparse
    import json
    parser = argparse.ArgumentParser(description='BigDelta calculation revision review (local processing)')
    commands = parser.add_subparsers(dest='command', required=True)
    compare = commands.add_parser('compare', help='Generate review candidates as JSON')
    compare.add_argument('earlier', type=Path)
    compare.add_argument('newer', type=Path)
    compare.add_argument('--output', type=Path, required=True)
    export = commands.add_parser('export', help='Export findings marked disposition=include as native callouts')
    export.add_argument('newer', type=Path)
    export.add_argument('review_json', type=Path)
    export.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'compare':
            if args.output.resolve() in (args.earlier.resolve(), args.newer.resolve()):
                raise ValueError('Review JSON must not overwrite a source PDF.')
            report = compare_calculations(args.earlier, args.newer)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
            print(f'{len(report["findings"])} candidates written to {args.output}. Review before exporting.')
        else:
            report = json.loads(args.review_json.read_text(encoding='utf-8'))
            if report.get('newer_sha256') != file_sha256(args.newer):
                raise ValueError('Newer PDF does not match the reviewed source hash. Compare again.')
            result = export_callouts(args.newer, args.output, report['findings'])
            print(f'{result["callout_count"]} individual callouts written to {args.output}.')
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(2, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
