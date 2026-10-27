import base64
import io
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader
from reportlab.pdfgen import canvas
from PIL import Image

from bigdelta.service import Workspace


def pdf(label='Drawing A', pages=1, size=(612, 792)):
    stream = io.BytesIO()
    c = canvas.Canvas(stream, pagesize=size)
    for i in range(pages):
        c.drawString(60, size[1] - 100, f'{label} - {i+1}')
        c.showPage()
    c.save()
    return base64.b64encode(stream.getvalue()).decode()


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ws = Workspace(Path(self.temp.name))
        self.p = self.ws.create_project({'name': 'River House', 'number': 'S-042'})
        self.pid = self.p['id']
        self.section = self.p['sections'][0]['id']

    def upload(self, title='Gravity calculations', **extra):
        args = dict(title=title, filename='calc.pdf', content=pdf(title), section_id=self.section,
                    label='P01', author='Engineer A', note='Initial design')
        args.update(extra)
        return self.ws.upload(self.pid, args)

    def test_projects_are_isolated_and_persistent(self):
        other = self.ws.create_project({'name': 'School'})
        self.upload()
        reopened = Workspace(Path(self.temp.name))
        self.assertEqual(len(reopened.project(self.pid)['documents']), 1)
        self.assertEqual(reopened.project(other['id'])['documents'], {})

    def test_revision_history_is_immutable_and_latest_is_used(self):
        d = self.upload()
        original = d['revisions'][0].copy()
        self.upload(document_id=d['id'], label='P02', content=pdf('Revised'))
        saved = self.ws.project(self.pid)['documents'][d['id']]
        self.assertEqual(saved['revisions'][0], original)
        self.assertEqual(saved['revisions'][-1]['label'], 'P02')
        with self.assertRaises(ValueError):
            self.upload(document_id=d['id'], label='P02')

    def test_invalid_pdf_does_not_create_document(self):
        with self.assertRaises(ValueError):
            self.upload(content=base64.b64encode(b'not a PDF').decode())
        self.assertFalse(self.ws.project(self.pid)['documents'])

    def test_pdf_annotations_survive_footer_translation(self):
        from pypdf import PdfWriter
        from pypdf.generic import NameObject, ArrayObject, FloatObject
        stream = io.BytesIO()
        c = canvas.Canvas(stream, pagesize=(612, 792))
        c.drawString(60, 690, 'Annotated drawing')
        c.linkURL('https://example.com/design', (60, 680, 200, 700))
        c.save()
        writer = PdfWriter(clone_from=io.BytesIO(stream.getvalue()))
        annotation = writer.pages[0]['/Annots'][0].get_object()
        annotation[NameObject('/QuadPoints')] = ArrayObject([
            FloatObject(v) for v in [60, 700, 200, 700, 60, 680, 200, 680]])
        writer.pages[0][NameObject('/Annots')] = writer._add_object(writer.pages[0]['/Annots'])
        source = io.BytesIO()
        writer.write(source)
        self.upload(content=base64.b64encode(source.getvalue()).decode())
        package = self.ws.compile(self.pid, {})
        reader = PdfReader(self.ws.file_path(package['file']))
        annotation = reader.pages[3]['/Annots'][0].get_object()
        self.assertEqual(list(annotation['/Rect']), [60, 706, 200, 726])
        self.assertEqual(list(annotation['/QuadPoints']), [60, 726, 200, 726, 60, 706, 200, 706])
        self.assertEqual(annotation['/A']['/URI'], 'https://example.com/design')

    def test_empty_name_rejected(self):
        with self.assertRaises(ValueError):
            self.ws.create_project({'name': '  '})

    def test_template_can_remove_empty_section_but_not_occupied(self):
        self.upload()
        self.ws.template(self.pid, {'names': ['Design basis', 'Custom framing']})
        with self.assertRaises(ValueError):
            self.ws.template(self.pid, {'names': ['Footings']})

    def test_reorder_requires_exact_same_documents(self):
        a, b = self.upload('A'), self.upload('B')
        self.ws.arrange(self.pid, {'document_id': b['id'], 'section_id': self.section, 'position': 0})
        self.assertEqual(self.ws.project(self.pid)['sections'][0]['document_ids'], [b['id'], a['id']])

    def test_stale_reference_blocks_issue(self):
        spec = self.upload('Specification')
        drawing = self.upload('Drawing', references=[{'document_id': spec['id'], 'revision_id': spec['revisions'][0]['id']}])
        self.upload(document_id=spec['id'], label='P02')
        self.assertTrue(any('Specification' in x for x in self.ws.checks(self.pid)))
        with self.assertRaises(ValueError):
            self.ws.compile(self.pid, {'issue': True})
        self.upload(document_id=drawing['id'], label='P02', references=[{'document_id': spec['id'], 'revision_id': self.ws.project(self.pid)['documents'][spec['id']]['revisions'][-1]['id']}])
        self.assertEqual(self.ws.checks(self.pid), [])

    def test_change_requires_each_impacted_document_resolution(self):
        a, b = self.upload('Calculation'), self.upload('Drawing')
        change = self.ws.add_change(self.pid, {'title': 'Opening moved', 'intent': 'Maintain load path', 'document_ids': [a['id'], b['id']]})
        self.assertEqual(len(self.ws.checks(self.pid)), 2)
        self.ws.resolve(self.pid, {'change_id': change['id'], 'document_id': a['id'], 'note': 'Checked and updated'})
        self.assertEqual(len(self.ws.checks(self.pid)), 1)
        self.ws.resolve(self.pid, {'change_id': change['id'], 'document_id': b['id'], 'note': 'Opening coordinated'})
        self.assertFalse(self.ws.checks(self.pid))

    def test_pdf_has_linked_toc_bookmarks_footers_and_latest_content(self):
        a = self.upload(content=pdf('Old'))
        self.upload(document_id=a['id'], label='P02', content=pdf('Current', 2))
        package = self.ws.compile(self.pid, {'generated_by': 'Alex', 'checked_by': 'Sam', 'approved_by': 'Jo'})
        reader = PdfReader(self.ws.file_path(package['file']))
        self.assertEqual(len(reader.pages), 6)  # cover, TOC, section, 2 source pages, basis register
        self.assertIn('Alex', reader.pages[0].extract_text())
        self.assertIn('Current', reader.pages[3].extract_text())
        self.assertIn('Page 5 of 6', reader.pages[4].extract_text())
        self.assertTrue(reader.pages[1]['/Annots'])
        self.assertGreaterEqual(len(reader.outline), 3)
        self.assertEqual(package['manifest'][0]['revision_label'], 'P02')

    def test_multi_page_toc_and_landscape(self):
        for i in range(24):
            self.upload(f'Sheet {i:02}', content=pdf(str(i), size=(1000, 600)))
        result = self.ws.compile(self.pid, {})
        reader = PdfReader(self.ws.file_path(result['file']))
        self.assertEqual(len(reader.pages), 29)  # 1 cover + 2 TOC + 1 divider + 24 + register
        self.assertGreater(float(reader.pages[-2].mediabox.width), float(reader.pages[-2].mediabox.height))
        self.assertTrue(reader.pages[2].get('/Annots'))

    def test_compiled_package_is_immutable(self):
        d = self.upload()
        first = self.ws.compile(self.pid, {})
        data = self.ws.file_path(first['file']).read_bytes()
        self.upload(document_id=d['id'], label='P02')
        second = self.ws.compile(self.pid, {})
        self.assertNotEqual(first['file'], second['file'])
        self.assertEqual(self.ws.file_path(first['file']).read_bytes(), data)

    def test_non_pdf_is_stored_but_not_compiled(self):
        self.upload(filename='estimate.csv', content=base64.b64encode(b'Item,Cost\nBeam,100').decode())
        with self.assertRaises(ValueError):
            self.ws.compile(self.pid, {})

    def test_file_paths_cannot_escape_workspace(self):
        with self.assertRaises(ValueError):
            self.ws.file_path('../outside')

    def test_notes_assumptions_and_code_citations_persist(self):
        self.upload()
        self.ws.add_record(self.pid, {'kind': 'assumption', 'text': 'Bearing pressure provided by geotechnical engineer', 'author': 'Alex'})
        self.ws.add_record(self.pid, {'kind': 'code', 'text': 'ASCE 7, edition to be confirmed, Chapter 12', 'author': 'Alex'})
        self.ws.add_record(self.pid, {'kind': 'comment', 'text': 'Review connection detail', 'author': 'Sam'})
        result = self.ws.compile(self.pid, {})
        text = '\n'.join(p.extract_text() for p in PdfReader(self.ws.file_path(result['file'])).pages)
        self.assertIn('Bearing pressure', text)
        self.assertIn('ASCE 7', text)
        self.assertEqual(len(self.ws.project(self.pid)['records']), 3)

    def test_compare_identical_and_changed_pages(self):
        d = self.upload()
        rid = d['revisions'][0]['id']
        same = self.ws.compare(self.pid, {'left': rid, 'right': rid, 'left_page': 1, 'right_page': 1})
        self.assertEqual(same['changed_percent'], 0)
        updated = self.upload(document_id=d['id'], label='P02', content=pdf('Changed geometry'))
        different = self.ws.compare(self.pid, {'left': rid, 'right': updated['revisions'][-1]['id'], 'left_page': 1, 'right_page': 1})
        self.assertGreater(different['changed_percent'], 0)
        image = Image.open(io.BytesIO(base64.b64decode(different['overlay'].split(',')[1])))
        self.assertTrue(any(r > 200 and g < 50 and b > 200 for r,g,b in image.get_flattened_data()))
        self.assertTrue(any(r < 50 and g > 200 and b > 200 for r,g,b in image.get_flattened_data()))
        with self.assertRaises(ValueError):
            self.ws.compare(self.pid, {'left': rid, 'right': rid, 'left_page': 99, 'right_page': 1})

    def test_tampered_source_is_not_silently_compiled(self):
        d = self.upload()
        self.ws.file_path(d['revisions'][0]['file']).write_bytes(base64.b64decode(pdf('Tampered')))
        with self.assertRaises(ValueError):
            self.ws.compile(self.pid, {})

    def test_reference_cannot_target_another_project(self):
        other = self.ws.create_project({'name': 'Other'})
        foreign = self.ws.upload(other['id'], {'title':'Other doc', 'filename':'a.pdf','content':pdf(),
                'label':'A','author':'A','note':'Initial','section_id':other['sections'][0]['id']})
        with self.assertRaises(ValueError):
            self.upload(references=[{'document_id':foreign['id'], 'revision_id':foreign['revisions'][0]['id']}])

    def test_references_require_one_revision_per_document(self):
        d = self.upload('Specification')
        ref = {'document_id':d['id'], 'revision_id':d['revisions'][0]['id']}
        with self.assertRaises(ValueError):
            self.upload('Drawing', references=[ref, ref])

    def test_comparison_rejects_unmatched_extents(self):
        a = self.upload()
        b = self.upload('Landscape', content=pdf(size=(1000,600)))
        with self.assertRaises(ValueError):
            self.ws.compare(self.pid, {'left':a['revisions'][0]['id'], 'right':b['revisions'][0]['id']})

    def test_issue_snapshot_records_approvals(self):
        self.upload()
        result = self.ws.compile(self.pid, {'issue':True, 'generated_by':'Alex', 'checked_by':'Sam', 'approved_by':'Jo'})
        self.assertTrue(result['issue'])
        self.assertEqual(result['approvals']['approved_by'], 'Jo')
        reader = PdfReader(self.ws.file_path(result['file']))
        self.assertIn('ISSUED', reader.pages[0].extract_text())
        toc = reader.pages[1]
        targets = [a.get_object()['/Dest'][0] for a in toc['/Annots']]
        self.assertTrue(all(t in [page.indirect_reference for page in reader.pages] for t in targets))

    def test_long_register_flows_to_multiple_pages(self):
        self.upload()
        for i in range(20):
            self.ws.add_record(self.pid, {'kind':'assumption','text':f'{i}: '+('Confirm project-specific criteria. '*25),'author':'Engineer'})
        result = self.ws.compile(self.pid, {})
        reader = PdfReader(self.ws.file_path(result['file']))
        self.assertGreater(result['page_count'], 7)
        self.assertIn('19:', '\n'.join(p.extract_text() for p in reader.pages))


if __name__ == '__main__':
    unittest.main()
