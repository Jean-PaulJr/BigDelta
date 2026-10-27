import base64
import json
from pathlib import Path
import tempfile
import time
import unittest
import pymupdf as fitz
from bigdelta.revision_review import compare_calculations, export_callouts
from bigdelta.service import Workspace


def document(path, pages, bookmarks=None):
    with fitz.open() as doc:
        for lines in pages:
            page = doc.new_page()
            for i, line in enumerate(lines):
                page.insert_text((60, 65 + i * 24), line, fontsize=11)
        if bookmarks:
            doc.set_toc(bookmarks)
        doc.save(path)
    return path


class RevisionReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.old, self.new = self.root / 'old.pdf', self.root / 'new.pdf'

    def test_inserted_pages_do_not_cascade_into_false_changes(self):
        document(self.old, [['Wind speed: 98 MPH'], ['Plate thickness: 1 in']])
        document(self.new, [['Wind speed: 98 MPH'], ['New section introduction'], ['Plate thickness: 1 in']])
        result = compare_calculations(self.old, self.new)
        self.assertEqual(result['unchanged_pages'], 2)
        self.assertTrue(all(f['newer_page'] == 2 for f in result['findings']))

    def test_node_load_regions_excluded_but_later_criteria_retained(self):
        document(self.old, [['Nodal Loads', 'Node 1 FX = 1 kip', 'Design criteria', 'Wind speed: 98 MPH']])
        document(self.new, [['Nodal Loads', 'Node 1 FX = 900 kip', 'Design criteria', 'Wind speed: 110 MPH']])
        result = compare_calculations(self.old, self.new)
        self.assertGreater(result['excluded_node_load_rows'], 0)
        self.assertEqual(len(result['findings']), 1)
        self.assertEqual(result['findings'][0]['category'], 'loading')
        self.assertNotIn('900', '\n'.join(f['summary'] for f in result['findings']))

    def test_node_load_bookmark_continuation_is_excluded(self):
        toc = [[1, 'Structure A', 1], [2, 'Nodal Loads', 1], [2, 'Repeat Loads', 3]]
        document(self.old, [['Nodal Loads'], ['Node 2 FX 1 kip'], ['Repeat Loads', 'Wind speed: 98 MPH']], toc)
        document(self.new, [['Nodal Loads'], ['Node 2 FX 9 kip'], ['Repeat Loads', 'Wind speed: 98 MPH']], toc)
        self.assertFalse(compare_calculations(self.old, self.new)['findings'])

    def test_load_grouping_scoped_acceptance_always_visible(self):
        toc = [[1, 'Structure A', 1], [1, 'Structure B', 2]]
        document(self.old, [['Wind speed: 98 MPH', 'Demand: 10 kip', 'Anchor check: PASS'], ['Demand: 20 kip']], toc)
        document(self.new, [['Wind speed: 110 MPH', 'Demand: 15 kip', 'Anchor check: FAIL'], ['Demand: 25 kip']], toc)
        r = compare_calculations(self.old, self.new)
        self.assertEqual(len(r['grouped_results']), 1)
        self.assertEqual(r['grouped_results'][0]['newer_page'], 1)
        self.assertEqual(r['findings'][0]['category'], 'acceptance')
        self.assertTrue(any(f['category'] == 'result' and f['newer_page'] == 2 for f in r['findings']))

    def test_results_flagged_when_applied_loads_unchanged(self):
        document(self.old, [['Wind speed: 98 MPH', 'Deflection: 0.002 in']])
        document(self.new, [['Wind speed: 98 MPH', 'Deflection: 0.093 in']])
        r = compare_calculations(self.old, self.new)
        self.assertFalse(r['grouped_results'])
        self.assertEqual(r['findings'][0]['category'], 'result')
        self.assertIn('0.002', r['findings'][0]['summary'])
        self.assertIn('0.093', r['findings'][0]['summary'])

    def test_failed_to_pass_is_also_priority_one(self):
        document(self.old, [['Anchor check: FAIL']])
        document(self.new, [['Anchor check: PASS']])
        self.assertEqual(compare_calculations(self.old, self.new)['findings'][0]['priority'], 1)

    def test_formula_outcome_words_not_reported_failure(self):
        document(self.old, [['Anchor check: if (ratio < 1, OK, NG)']])
        document(self.new, [['Anchor check: if (ratio <= 1, OK, NG)']])
        self.assertFalse(any(f['category'] == 'acceptance' for f in compare_calculations(self.old, self.new)['findings']))

    def test_unchanged_summary_can_conflict_with_new_failure(self):
        document(self.old, [['Anchor check: PASS', 'Summary: acceptable']])
        document(self.new, [['Anchor check: FAIL', 'Summary: acceptable']])
        self.assertTrue(any(f['category'] == 'conclusion' for f in compare_calculations(self.old, self.new)['findings']))

    def test_moved_check_not_flagged_removed(self):
        toc = [[1, 'Structure A', 1]]
        document(self.old, [['Stability check: PASS', 'Wind speed: 98 MPH'], ['Plate thickness: 1 in']], toc)
        document(self.new, [['Wind speed: 98 MPH'], ['Plate thickness: 1 in', 'Stability check: PASS']], toc)
        self.assertFalse(compare_calculations(self.old, self.new)['findings'])

    def test_graphics_only_changes_report_coverage_gap(self):
        document(self.old, [[]]); document(self.new, [[]])
        with fitz.open(self.new) as doc:
            doc[0].draw_rect((40, 40, 120, 120)); doc.saveIncr()
        r = compare_calculations(self.old, self.new)
        self.assertFalse(r['findings']); self.assertTrue(r['coverage_gaps'])

    def test_native_callouts_preserve_source_and_existing_annotations(self):
        document(self.old, [['Fy: 36 ksi', 'Plate thickness: 1.75 in']])
        document(self.new, [['Fy: 50 ksi', 'Plate thickness: 1.25 in']])
        with fitz.open(self.new) as doc:
            doc[0].add_text_annot((20, 20), 'Existing reviewer note'); doc.saveIncr()
        r = compare_calculations(self.old, self.new)
        self.assertEqual(len(r['findings']), 2)
        for f in r['findings']: f['disposition'] = 'include'
        output = self.root / 'callouts.pdf'
        details = export_callouts(self.new, output, r['findings'])
        self.assertEqual(details, {'callout_count': 2, 'page_count': 1})
        self.assertNotIn('_lines', r['findings'][0])
        with fitz.open(self.new) as source, fitz.open(output) as doc:
            self.assertIn(source[0].read_contents(), doc[0].read_contents())
            page = doc[0]; annots = list(page.annots())
            self.assertEqual(sum(a.type[1] == 'Text' for a in annots), 1)
            callouts = [a for a in annots if a.type[1] == 'FreeText']
            self.assertEqual(len(callouts), 2)
            for a in callouts:
                self.assertEqual(doc.xref_get_key(a.xref, 'IT')[1], '/FreeTextCallout')
                self.assertEqual(doc.xref_get_key(a.xref, 'CL')[0], 'array')
                self.assertTrue(page.rect.contains(a.rect)); self.assertTrue(a.get_text().strip())

    def test_pending_excluded_and_overwrite_rejected(self):
        document(self.old, [['Fy: 36 ksi']]); document(self.new, [['Fy: 50 ksi']])
        f = compare_calculations(self.old, self.new)['findings']
        with self.assertRaises(ValueError): export_callouts(self.new, self.root / 'out.pdf', f)
        f[0]['disposition'] = 'include'
        with self.assertRaises(ValueError): export_callouts(self.new, self.new, f)

    def test_rotated_page_export_rejected(self):
        document(self.old, [['Fy: 36 ksi']]); document(self.new, [['Fy: 50 ksi']])
        r = compare_calculations(self.old, self.new)
        for f in r['findings']: f['disposition'] = 'include'
        with fitz.open(self.new) as doc: doc[0].set_rotation(90); doc.saveIncr()
        with self.assertRaisesRegex(ValueError, 'rotation'):
            export_callouts(self.new, self.root / 'out.pdf', r['findings'])

    def test_service_spawn_edit_export_and_isolation(self):
        document(self.old, [['Fy: 36 ksi']]); document(self.new, [['Fy: 50 ksi']])
        ws = Workspace(self.root / 'data'); p = ws.create_project({'name': 'Test calculations'})
        did = None
        for path, label in [(self.old, 'A'), (self.new, 'B')]:
            args = dict(filename=path.name, title='Calculations', section_id=p['sections'][0]['id'], label=label,
                        author='Engineer', note='Test', content=base64.b64encode(path.read_bytes()).decode())
            if did: args['document_id'] = did
            d = ws.upload(p['id'], args); did = d['id']
        job = ws.review_start(p['id'], {'left': d['revisions'][0]['id'], 'right': d['revisions'][1]['id']})
        self.addCleanup(ws._review_pool.shutdown)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            job = ws._review_job(p['id'], job['id'])
            if job['status'] in ('complete', 'failed'): break
            time.sleep(.05)
        self.assertEqual(job['status'], 'complete', job)
        fs = job['result']['findings']; fs[0].update(disposition='include', summary='Yield strength: 36 -> 50 ksi.')
        ws.review_update(p['id'], {'job_id': job['id'], 'findings': fs})
        exported = ws.review_export(p['id'], {'job_id': job['id']})
        self.assertEqual(exported['callout_count'], 1); self.assertTrue(ws.file_path(exported['file']).is_file())
        self.assertEqual(len(ws.project(p['id'])['reviews']), 1)
        other = ws.create_project({'name': 'Other'})
        with self.assertRaises(ValueError): ws._review_job(other['id'], job['id'])
        manual = dict(id='M1', category='propagation', disposition='include', title='Downstream update',
                      summary='Confirm dependency.', newer_page=1, target_text='missing source text')
        with self.assertRaisesRegex(ValueError, 'not found'):
            ws.review_update(p['id'], {'job_id': job['id'], 'findings': fs + [manual]})
        source = ws.file_path(d['revisions'][1]['file'])
        source.write_bytes(source.read_bytes() + b'\n% changed after review')
        with self.assertRaisesRegex(ValueError, 'changed after comparison'):
            ws.review_export(p['id'], {'job_id': job['id']})


class AdditionalReviewTests(unittest.TestCase):
    setUp = RevisionReviewTests.setUp
    def test_inconsistent_bolt_strength_candidate(self):
        toc = [[1, 'Anchor calculation', 1]]
        document(self.old, [['Fy = 36 ksi Yield Strength of Bolts'], ['Old anchor worksheet']], toc)
        document(self.new, [['Fy = 105 ksi Yield Strength of Bolts'], ['Fy = 50 ksi Yield Strength of Bolts']], toc)
        findings = compare_calculations(self.old, self.new)['findings']
        self.assertTrue(any(f['category'] == 'propagation' and '105' in f['summary'] and '50' in f['summary'] for f in findings))

    def test_node_assignment_without_table_heading_excluded(self):
        document(self.old, [['Node 1 FX = 1 kip']]); document(self.new, [['Node 1 FX = 9 kip']])
        self.assertFalse(compare_calculations(self.old, self.new)['findings'])
