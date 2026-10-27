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

    def test_unknown_files_and_traversal_rejected(self):
        self.assertEqual(self.request('GET','/../service.py')[0],404)
        self.assertEqual(self.request('GET','/download/unknown')[0],404)
        self.assertEqual(self.request('GET','/api/state',headers={'Host':'evil.example'})[0],403)

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
