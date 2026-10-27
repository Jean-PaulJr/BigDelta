import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from bigdelta.server import LocalServer, handler_for
from bigdelta.service import Workspace


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Workspace(Path(self.temp.name))
        self.server = LocalServer(('127.0.0.1', 0), handler_for(self.workspace))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, method, path, data=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        try:
            conn.request(method, path, body=json.dumps(data).encode() if data is not None else None, headers=headers or {})
            response = conn.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            conn.close()

    def test_static_ui_and_logo_are_packaged(self):
        for path in ['/', '/app.js', '/style.css', '/logo.svg']:
            status, body, headers = self.request('GET', path)
            self.assertEqual(status, 200)
            self.assertTrue(body)
            self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')

    def test_mutation_requires_session_token_and_same_origin(self):
        status, body, _ = self.request('GET','/api/state')
        token = json.loads(body)['token']
        self.assertEqual(self.request('POST','/api/projects',{'name':'A'})[0],403)
        self.assertEqual(self.request('POST','/api/projects',{'name':'A'}, {'X-BigDelta-Token':token,'Origin':'https://example.com'})[0],403)
        self.assertEqual(self.request('POST','/api/projects',{'name':'A'}, {'X-BigDelta-Token':token})[0],201)
        _, body, _ = self.request('GET','/api/state')
        self.assertEqual(len(json.loads(body)['projects']),1)
        self.assertEqual(json.loads(body)['summaries'][0]['name'],'A')
        self.assertEqual(json.loads(body)['summaries'][0]['status'],'No tasks')

    def test_unknown_files_and_traversal_rejected(self):
        self.assertEqual(self.request('GET','/../service.py')[0],404)
        self.assertEqual(self.request('GET','/download/unknown')[0],404)
        self.assertEqual(self.request('GET','/api/state',headers={'Host':'evil.example'})[0],403)

    def test_section_titles_and_order_can_be_changed_through_api(self):
        _, body, _ = self.request('GET','/api/state')
        headers={'X-BigDelta-Token':json.loads(body)['token']}
        _, body, _ = self.request('POST','/api/projects',{'name':'Section editing'},headers)
        project=json.loads(body)
        sid=project['sections'][1]['id']
        status,body,_=self.request('POST',f'/api/projects/{project["id"]}/section',
                                 {'section_id':sid,'name':'Custom framing','position':0},headers)
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body)['sections'][0]['name'],'Custom framing')
        self.assertEqual(json.loads(body)['sections'][0]['id'],sid)

    def test_sections_can_be_added_and_deleted_through_api(self):
        _,body,_=self.request('GET','/api/state')
        headers={'X-BigDelta-Token':json.loads(body)['token']}
        _,body,_=self.request('POST','/api/projects',{'name':'Section lifecycle'},headers)
        project=json.loads(body)
        base=f'/api/projects/{project["id"]}'
        status,body,_=self.request('POST',base+'/section_add',{'name':'Connections'},headers)
        self.assertEqual(status,200)
        added=json.loads(body)['sections'][-1]
        status,body,_=self.request('POST',base+'/section_delete',{'section_id':added['id']},headers)
        self.assertEqual(status,200)
        self.assertNotIn(added['id'],[s['id'] for s in json.loads(body)['sections']])

    def test_task_endpoint_updates_completion_and_dates(self):
        _,body,_=self.request('GET','/api/state')
        headers={'X-BigDelta-Token':json.loads(body)['token']}
        _,body,_=self.request('POST','/api/projects',{'name':'Task plan'},headers)
        pid=json.loads(body)['id']
        status,body,_=self.request('POST',f'/api/projects/{pid}/task',
            {'title':'Review criteria','phase':'Planning','status':'complete','completed_date':'2026-10-27','estimated_date':'2026-10-28'},headers)
        self.assertEqual(status,200)
        p=json.loads(body)
        self.assertEqual(p['progress'],100)
        status,body,_=self.request('POST',f'/api/projects/{pid}/task',{'task_id':p['tasks'][0]['id'],'status':'on hold'},headers)
        self.assertEqual(status,200)
        p=json.loads(body)
        self.assertEqual(p['progress'],0)
        self.assertEqual(p['tasks'][0]['completed_date'],'')

    def test_rfi_endpoint_creates_and_updates_project_requests(self):
        _,body,_=self.request('GET','/api/state')
        headers={'X-BigDelta-Token':json.loads(body)['token']}
        p=self.workspace.create_project({'name':'RFI project'})
        url=f'/api/projects/{p["id"]}/rfi'
        status,body,_=self.request('POST',url,{'description':'Confirm design intent','requested_by':'Engineer','sent_to':'Architect','sent_date':'2026-10-27'},headers)
        self.assertEqual(status,200)
        rfi=json.loads(body)['rfis'][0]
        self.assertEqual(rfi['number'],'RFI-001')
        status,body,_=self.request('POST',url,{'rfi_id':rfi['id'],'response':'See revised detail','status':'Closed'},headers)
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body)['rfis'][0]['response'],'See revised detail')
        self.assertEqual(json.loads(body)['rfis'][0]['status'],'Closed')

    def test_cover_details_and_pdf_download_filename(self):
        import base64
        import io
        from reportlab.pdfgen import canvas
        _,body,_=self.request('GET','/api/state')
        headers={'X-BigDelta-Token':json.loads(body)['token']}
        p=self.workspace.create_project({'name':'Initial'})
        status,body,_=self.request('POST',f'/api/projects/{p["id"]}/details',{'name':'Updated','number':'BD-200','client':'Client'},headers)
        self.assertEqual(status,200)
        status,body,_=self.request('POST',f'/api/projects/{p["id"]}/cover',{'generated_by':'Alex','checked_by':'Sam','approved_by':'Jo'},headers)
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body)['cover']['checked_by'],'Sam')
        stream=io.BytesIO()
        c=canvas.Canvas(stream);c.drawString(50,700,'Sample');c.save()
        self.workspace.upload(p['id'],{'title':'Sample','section_id':p['sections'][0]['id'],'label':'A','author':'Alex','note':'Initial','filename':'sample.pdf','content':base64.b64encode(stream.getvalue()).decode()})
        status,body,_=self.request('POST',f'/api/projects/{p["id"]}/compile',{},headers)
        self.assertEqual(status,200)
        package=json.loads(body)
        status,body,response_headers=self.request('GET',f'/download/{package["id"]}')
        self.assertEqual(status,200)
        self.assertTrue(body.startswith(b'%PDF'))
        self.assertIn(package['filename'],response_headers['Content-Disposition'])
    def test_calculation_review_routes_preserve_project_isolation_and_tokens(self):
        p = self.workspace.create_project({'name': 'Calculation review'})
        other = self.workspace.create_project({'name': 'Other project'})
        self.workspace._save_review_job(p['id'], {'id': 'job1', 'at': '2026-01-01', 'status': 'complete', 'result': {'findings': []}})
        status, body, _ = self.request('GET', f"/api/projects/{p['id']}/reviews/job1")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['id'], 'job1')
        self.assertEqual(self.request('GET', f"/api/projects/{other['id']}/reviews/job1")[0], 404)
        self.assertEqual(self.request('POST', f"/api/projects/{p['id']}/review_export", {'job_id': 'job1'})[0], 403)
        self.assertEqual(self.request('GET', f"/api/projects/{p['id']}/reviews")[0], 200)
