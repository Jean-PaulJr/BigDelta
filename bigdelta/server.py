"""Loopback-only, single-user HTTP adapter with same-origin mutation checks."""
import argparse
import json
import mimetypes
import os
import secrets
import socket
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import quote, urlsplit

from .service import Workspace

STATIC = Path(__file__).parent / 'static'
MAX_REQUEST = 165 * 1024 * 1024


class LocalServer(HTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def handler_for(workspace):
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def send(self, status, body, content_type='application/json', attachment=False):
            if not isinstance(body, bytes):
                body = json.dumps(body).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'")
            if attachment:
                filename=attachment if isinstance(attachment,str) else 'bigdelta-document.pdf'
                self.send_header('Content-Disposition', "attachment; filename*=UTF-8''"+quote(filename,safe=''))
            self.end_headers()
            self.wfile.write(body)

        def valid_host(self):
            return self.headers.get('Host') in [f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}']

        def do_GET(self):
            if not self.valid_host():
                return self.send(403, {'error': 'Localhost access only.'})
            path = urlsplit(self.path).path
            try:
                if path == '/api/state':
                    projects = workspace.projects()
                    return self.send(200, dict(projects=projects, summaries=[workspace.project_summary(p) for p in projects], checks={p['id']: workspace.check_project(p) for p in projects}, token=token))
                parts = path.strip('/').split('/')
                if len(parts) in (4, 5) and parts[:2] == ['api', 'projects'] and parts[3] == 'reviews':
                    return self.send(200, workspace.review_jobs(parts[2]) if len(parts) == 4 else workspace._review_job(parts[2], parts[4]))
                if path.startswith('/download/'):
                    # Only files referenced by a saved project can be downloaded.
                    file_id = path.removeprefix('/download/')
                    for p in workspace.projects():
                        all_files = [r for d in p['documents'].values() for r in d['revisions']] + p['packages'] + p.get('reviews', [])
                        match = next((r for r in all_files if r['id'] == file_id), None)
                        if match:
                            return self.send(200, workspace.file_path(match['file']).read_bytes(),
                                             'application/pdf' if match.get('is_pdf', True) else 'application/octet-stream', match.get('filename',f'BigDelta-package-{match["id"][:8]}.pdf'))
                    return self.send(404, {'error': 'File not found.'})
                if path.startswith('/manifest/'):
                    package_id = path.removeprefix('/manifest/')
                    for p in workspace.projects():
                        package = next((x for x in p['packages'] if x['id'] == package_id), None)
                        if package:
                            return self.send(200, package)
                    return self.send(404, {'error': 'Package not found.'})
                name = 'index.html' if path == '/' else path.lstrip('/')
                target = (STATIC / name).resolve()
                if target.parent != STATIC.resolve() or not target.is_file():
                    return self.send(404, {'error': 'Not found.'})
                types = {'.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.html': 'text/html'}
                return self.send(200, target.read_bytes(), types.get(target.suffix, 'application/octet-stream') + '; charset=utf-8')
            except (ValueError, OSError):
                return self.send(404, {'error': 'Resource unavailable.'})

        def do_POST(self):
            if not self.valid_host() or self.headers.get('X-BigDelta-Token') != token:
                return self.send(403, {'error': 'Reload BigDelta before continuing.'})
            origin = self.headers.get('Origin')
            if origin and origin not in [f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}']:
                return self.send(403, {'error': 'Same-origin requests only.'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= MAX_REQUEST:
                    return self.send(413, {'error': 'Upload exceeds the request limit.'})
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError('Expected a JSON object.')
                parts = urlsplit(self.path).path.strip('/').split('/')
                if parts == ['api', 'projects']:
                    return self.send(201, workspace.create_project(data))
                if len(parts) != 4 or parts[:2] != ['api', 'projects']:
                    return self.send(404, {'error': 'Action not found.'})
                actions = dict(update=workspace.update_project, details=workspace.update_details, cover=workspace.update_cover, task=workspace.save_task, rfi=workspace.save_rfi, template=workspace.template, section=workspace.update_section,
                               section_add=workspace.add_section, section_delete=workspace.delete_section,
                               upload=workspace.upload, arrange=workspace.arrange, record=workspace.add_record,
                               change=workspace.add_change, resolve=workspace.resolve,
                               compile=workspace.compile, compare=workspace.compare,
                               review_start=workspace.review_start, review_update=workspace.review_update,
                               review_export=workspace.review_export)
                action = actions.get(parts[3])
                if not action:
                    return self.send(404, {'error': 'Action not found.'})
                return self.send(200, action(parts[2], data))
            except (ValueError, KeyError, TypeError) as exc:
                return self.send(400, {'error': str(exc) or 'Invalid input.'})
            except Exception:
                traceback.print_exc()
                return self.send(500, {'error': 'The operation failed. See the terminal for details.'})

    return Handler


def main():
    parser = argparse.ArgumentParser(description='BigDelta local project workspace')
    parser.add_argument('--data', type=Path, default=Path(os.environ.get('BIGDELTA_DATA', Path.cwd() / 'data')))
    parser.add_argument('--port', type=int, default=8879)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    server = LocalServer(('127.0.0.1', args.port), handler_for(Workspace(args.data)))
    url = f'http://127.0.0.1:{server.server_port}'
    print(f'BigDelta is running at {url}\nData: {args.data.resolve()}\nPress Ctrl+C to stop.', flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
