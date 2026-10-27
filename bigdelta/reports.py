"""ReportLab generation and pypdf assembly; see SOURCES.md for API references."""
import io
import math
import hashlib
from html import escape

from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.annotations import Link
from pypdf.generic import NameObject, RectangleObject, ArrayObject, FloatObject
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from .service import now, uid

NAVY = colors.HexColor('#142c40')
TEAL = colors.HexColor('#087f83')
PAGE = (612, 792)


def logo(c, x, y, size=40):
    c.setStrokeColor(TEAL)
    c.setLineWidth(size / 9)
    p = c.beginPath()
    p.moveTo(x, y)
    p.lineTo(x + size / 2, y + size)
    p.lineTo(x + size, y)
    p.close()
    c.drawPath(p)
    c.setStrokeColor(colors.HexColor('#e99b49'))
    c.line(x + size * .40, y + size * .22, x + size * .75, y + size * .22)


def line(c, text, x, y, font='Helvetica', size=11, color=NAVY, width=500):
    # Fit single-line labels; multi-line prose uses Platypus below.
    text = str(text).encode('cp1252', errors='replace').decode('cp1252')
    while c.stringWidth(text, font, size) > width and size > 6:
        size -= .3
    if c.stringWidth(text, font, size) > width:
        while text and c.stringWidth(text + '...', font, size) > width:
            text = text[:-1]
        text += '...'
    c.setFillColor(color)
    c.setFont(font, size)
    c.drawString(x, y, text)


def page_pdf(draw):
    stream = io.BytesIO()
    c = canvas.Canvas(stream, pagesize=PAGE)
    draw(c)
    c.save()
    return PdfReader(io.BytesIO(stream.getvalue()))


def register_pdf(p, warnings):
    records = [r for r in p['records'] if r['kind'] in ['assumption', 'code']]
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=PAGE, leftMargin=56, rightMargin=56, topMargin=65, bottomMargin=60)
    heading = ParagraphStyle('heading', fontName='Helvetica-Bold', fontSize=20, leading=26, textColor=NAVY, spaceAfter=20)
    body = ParagraphStyle('body', fontName='Helvetica', fontSize=10, leading=15, textColor=NAVY, spaceAfter=14, splitLongWords=True)
    story = [Paragraph('Assumptions and code register', heading)]
    for title, values in [('OPEN COORDINATION ITEMS', warnings),
                          ('ASSUMPTIONS', [f'{r["text"]} — {r["author"]}' for r in records if r['kind'] == 'assumption'] or ['No assumptions recorded. Engineering basis requires review.']),
                          ('CODE CITATIONS', [f'{r["text"]} — {r["author"]}' for r in records if r['kind'] == 'code'] or ['No code citations recorded. Confirm adopted codes, editions, and sections.'])]:
        if values:
            story.append(Paragraph(title, body))
            story += [Paragraph(escape(v).replace('\n', '<br/>'), body) for v in values]
            story.append(Spacer(1, 15))
    doc.build(story)
    return PdfReader(io.BytesIO(output.getvalue()))


def compile_report(p, workspace, options, warnings):
    issue = bool(options.get('issue', False))
    status = 'ISSUED' if issue else 'DRAFT - FOR REVIEW'
    entries, parts, manifest = [], [], []
    for section in p['sections']:
        docs = [(p['documents'][did], p['documents'][did]['revisions'][-1]) for did in section['document_ids']]
        docs = [(d, r) for d, r in docs if r['is_pdf']]
        if not docs:
            continue
        entries.append({'title': section['name'], 'kind': 'section', 'offset': len(parts)})
        def divider(c, section=section):
            logo(c, 56, 638)
            line(c, p['number'], 56, 595, size=11)
            line(c, section['name'], 56, 530, 'Helvetica-Bold', 30)
            line(c, p['name'], 56, 492, size=15)
            line(c, status, 56, 450, size=10, color=TEAL)
        parts.extend(page_pdf(divider).pages)
        for d, r in docs:
            offset = len(parts)
            entries.append({'title': f'{d["title"]} [{r["label"]}]', 'kind': 'document', 'offset': offset})
            content = workspace.file_path(r['file']).read_bytes()
            if hashlib.sha256(content).hexdigest() != r['sha256']:
                raise ValueError(f'Stored source checksum changed: {d["title"]}. Restore the original or upload a new revision.')
            reader = PdfReader(io.BytesIO(content))
            parts.extend(reader.pages)
            manifest.append(dict(document_id=d['id'], title=d['title'], revision_id=r['id'],
                                 revision_label=r['label'], sha256=r['sha256'], offset=offset, pages=len(reader.pages)))
    if not manifest:
        raise ValueError('Add at least one PDF before compiling a report.')
    register = register_pdf(p, warnings)
    if register:
        entries.append(dict(title='Assumptions and code register', kind='section', offset=len(parts)))
        parts.extend(register.pages)
    toc_count = max(1, math.ceil(len(entries) / 22))
    front_count = 1 + toc_count
    total = front_count + len(parts)
    writer = PdfWriter()
    def cover(c):
        c.setFillColor(NAVY)
        c.rect(0, 680, 612, 112, fill=1, stroke=0)
        logo(c, 54, 710, 35)
        line(c, 'BigDelta', 110, 721, 'Helvetica-Bold', 25, colors.white)
        line(c, 'STRUCTURAL ENGINEERING / REPORT PACKAGE', 56, 625, size=10, color=TEAL)
        line(c, p['name'], 56, 563, 'Helvetica-Bold', 30)
        line(c, f'Project {p["number"] or "Unnumbered"}  |  {p["phase"]}', 56, 523, size=13)
        line(c, f'Client: {p["client"] or "Not specified"}', 56, 489)
        line(c, status, 56, 443, 'Helvetica-Bold', 14, TEAL)
        line(c, f'Compiled {now()}  |  {len(manifest)} documents', 56, 415, size=10)
        for i, (key, label) in enumerate([('generated_by', 'Generated by'), ('checked_by', 'Checked by'), ('approved_by', 'Approved by')]):
            y = 330 - i * 69
            line(c, label.upper(), 56, y, size=9, color=TEAL)
            line(c, options.get(key) or 'Not recorded', 56, y - 22, size=13)
            c.setStrokeColor(colors.HexColor('#cbd5db'))
            c.line(56, y - 32, 556, y - 32)
        line(c, 'Names are recorded workflow fields; no digital signature or professional seal is applied.', 56, 80, size=8)
    writer.add_page(page_pdf(cover).pages[0])
    for index in range(toc_count):
        def toc(c, index=index):
            line(c, 'Contents', 56, 716, 'Helvetica-Bold', 27)
            line(c, p['name'], 56, 688, size=11, color=TEAL)
            for j, entry in enumerate(entries[index * 22:(index + 1) * 22]):
                y = 641 - j * 24
                x = 56 if entry['kind'] == 'section' else 72
                line(c, entry['title'], x, y, 'Helvetica-Bold' if entry['kind'] == 'section' else 'Helvetica', 10, width=420)
                line(c, str(front_count + entry['offset'] + 1), 526, y, size=10, width=40)
        writer.add_page(page_pdf(toc).pages[0])
    for page in parts:
        # Reserve an external footer strip: source content is never painted over.
        writer.add_page(page)
        page = writer.pages[-1]
        page.transfer_rotation_to_content()
        w, h = float(page.cropbox.width), float(page.cropbox.height)
        dx, dy = -float(page.cropbox.left), 26 - float(page.cropbox.bottom)
        page.add_transformation(Transformation().translate(dx, dy))
        # Preserve annotation alignment after adding the footer margin.
        for annotation in page.annotations or []:
            annotation = annotation.get_object()
            if '/Rect' in annotation:
                rect = annotation['/Rect']
                annotation[NameObject('/Rect')] = RectangleObject([float(rect[0])+dx, float(rect[1])+dy, float(rect[2])+dx, float(rect[3])+dy])
            if '/QuadPoints' in annotation:
                annotation[NameObject('/QuadPoints')] = ArrayObject([FloatObject(float(v)+(dx if i%2==0 else dy)) for i,v in enumerate(annotation['/QuadPoints'])])
        page.mediabox.lower_left = (0, 0)
        page.mediabox.upper_right = (w, h + 26)
        page.cropbox.lower_left = (0, 0)
        page.cropbox.upper_right = (w, h + 26)
    parent = None
    writer.add_outline_item('Cover', 0)
    writer.add_outline_item('Contents', 1)
    for i, entry in enumerate(entries):
        target = front_count + entry['offset']
        annotation = writer.add_annotation(1 + i // 22, Link(rect=(52, 637 - (i % 22) * 24, 560, 657 - (i % 22) * 24), target_page_index=target))
        # PDF explicit destinations require a page reference, not a numeric index.
        # pypdf 6.10's Link helper leaves an integer in this field.
        annotation['/Dest'][0] = writer.pages[target].indirect_reference
        bookmark = writer.add_outline_item(entry['title'], target, parent=parent if entry['kind'] == 'document' else None)
        if entry['kind'] == 'section':
            parent = bookmark
    for i, page in enumerate(writer.pages):
        stream = io.BytesIO()
        w, h = float(page.mediabox.width), float(page.mediabox.height)
        c = canvas.Canvas(stream, pagesize=(w, h))
        line(c, f'{p["number"]} | {status}', 22, 10, size=8, width=max(100, w - 180))
        line(c, f'Page {i+1} of {total}', max(30, w - 115), 10, size=8, width=100)
        c.save()
        page.merge_page(PdfReader(io.BytesIO(stream.getvalue())).pages[0])
    package_id = uid()
    relative = f'files/{package_id}.pdf'
    writer.add_metadata({'/Title': f'{p["name"]} - {status}', '/Author': 'BigDelta', '/Subject': 'Structural engineering report package'})
    writer.write(workspace.file_path(relative))
    for m in manifest:
        m['start_page'] = front_count + m.pop('offset') + 1
    return dict(id=package_id, file=relative, at=now(), issue=issue, page_count=total,
                manifest=manifest, warnings=warnings, approvals={k: str(options.get(k, ''))[:160] for k in ['generated_by', 'checked_by', 'approved_by']})
