"""Local workspace services. All revision and package files use immutable UUID names."""
import base64
import hashlib
import io
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader


def uid():
    return uuid.uuid4().hex


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _windows_process_alive(pid):
    """Query a process without sending a signal or requesting terminate access."""
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE only
    if not handle:
        error = ctypes.get_last_error()
        if error == 87:  # ERROR_INVALID_PARAMETER: process no longer exists
            return False
        if error == 5:  # ERROR_ACCESS_DENIED: do not declare it dead
            return True
        raise ctypes.WinError(error)
    try:
        result = kernel.WaitForSingleObject(handle, 0)
        if result == 0:  # WAIT_OBJECT_0: process exited
            return False
        if result == 258:  # WAIT_TIMEOUT: process still running
            return True
        raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.CloseHandle(handle)


def _process_alive(pid):
    # os.kill(pid, 0) terminates the target on Windows, including our server.
    if os.name == 'nt':
        return _windows_process_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def required(data, key, limit=500):
    value = str(data.get(key, '')).strip()
    if not value or len(value) > limit:
        raise ValueError(f'{key.replace("_", " ").title()} is required (maximum {limit} characters).')
    return value


class Workspace:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / 'files').mkdir(exist_ok=True)
        self.db = self.root / 'bigdelta.sqlite3'
        with self.connection() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            conn.execute('CREATE TABLE IF NOT EXISTS review_jobs (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, data TEXT NOT NULL)')

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.db)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def save(self, p, action):
        p['updated'] = now()
        p['events'].append({'at': now(), 'action': action})
        with self.connection() as conn:
            conn.execute('INSERT OR REPLACE INTO projects VALUES (?, ?)', (p['id'], json.dumps(p)))
        return p

    def projects(self):
        with self.connection() as conn:
            rows = conn.execute('SELECT data FROM projects').fetchall()
        return sorted([json.loads(x[0]) for x in rows], key=lambda p: p['updated'], reverse=True)

    def project(self, pid):
        with self.connection() as conn:
            row = conn.execute('SELECT data FROM projects WHERE id=?', (pid,)).fetchone()
        if not row:
            raise ValueError('Project not found.')
        return json.loads(row[0])

    def create_project(self, data):
        p = dict(id=uid(), name=required(data, 'name', 160), number=str(data.get('number', ''))[:80],
                 client=str(data.get('client', ''))[:160], phase='Planning', progress=0,
                 documents={}, changes=[], records=[], packages=[], events=[], sections=[])
        for name in ['Design basis', 'Gravity systems', 'Lateral systems', 'Foundations', 'Drawings', 'Specifications']:
            p['sections'].append(dict(id=uid(), name=name, document_ids=[]))
        return self.save(p, 'Project created')

    def update_project(self, pid, data):
        p = self.project(pid)
        if data.get('phase') not in ['Planning', 'Design', 'Construction', 'Closeout']:
            raise ValueError('Choose a valid project phase.')
        value = int(data.get('progress', 0))
        if not 0 <= value <= 100:
            raise ValueError('Progress must be from 0 to 100.')
        p.update(phase=data['phase'], progress=value)
        return self.save(p, f'Progress updated: {value}% / {p["phase"]}')

    def template(self, pid, data):
        p = self.project(pid)
        names = [str(x).strip() for x in data.get('names', [])]
        if not names or len(names) > 100 or any(not n or len(n) > 120 for n in names) or len(set(names)) != len(names):
            raise ValueError('Enter 1-100 unique section names, up to 120 characters each.')
        for s in p['sections']:
            if s['name'] not in names and s['document_ids']:
                raise ValueError(f'Move documents out of "{s["name"]}" before removing the section.')
        existing = {s['name']: s for s in p['sections']}
        p['sections'] = [existing.get(n, dict(id=uid(), name=n, document_ids=[])) for n in names]
        return self.save(p, 'Report template updated')

    def upload(self, pid, data):
        p = self.project(pid)
        label = required(data, 'label', 50)
        author = required(data, 'author', 120)
        note = required(data, 'note', 4000)
        filename = required(data, 'filename', 240).replace('\\', '/').split('/')[-1]
        try:
            content = base64.b64decode(data.get('content', ''), validate=True)
        except Exception as exc:
            raise ValueError('Invalid upload encoding.') from exc
        if not content or len(content) > 120 * 1024 * 1024:
            raise ValueError('File must contain data and be smaller than 120 MB.')
        is_pdf = filename.lower().endswith('.pdf')
        pages = 0
        if is_pdf:
            try:
                reader = PdfReader(io.BytesIO(content))
                if reader.is_encrypted:
                    raise ValueError('Password protected PDFs are not supported.')
                pages = len(reader.pages)
                if not pages:
                    raise ValueError('PDF has no pages.')
            except Exception as exc:
                raise ValueError('Upload a readable, unencrypted PDF with at least one page.') from exc
        did = data.get('document_id')
        if did:
            if did not in p['documents']:
                raise ValueError('Document not found in this project.')
            d = p['documents'][did]
            if any(r['label'] == label for r in d['revisions']):
                raise ValueError('Revision labels must be unique for each document.')
        else:
            title = required(data, 'title', 180)
            section = next((s for s in p['sections'] if s['id'] == data.get('section_id')), None)
            if not section:
                raise ValueError('Choose a report section.')
            d = dict(id=uid(), title=title, revisions=[])
            p['documents'][d['id']] = d
            section['document_ids'].append(d['id'])
        refs = data.get('references', [])
        if not isinstance(refs, list):
            raise ValueError('References must be a list.')
        seen = set()
        for ref in refs:
            if not isinstance(ref, dict) or ref.get('document_id') in seen:
                raise ValueError('Choose one referenced revision per document.')
            seen.add(ref.get('document_id'))
            target = p['documents'].get(ref.get('document_id'))
            if not target or target['id'] == d['id'] or not any(r['id'] == ref.get('revision_id') for r in target['revisions']):
                raise ValueError('Each reference must identify an existing revision of another document in this project.')
        revision = dict(id=uid(), label=label, author=author, note=note, at=now(), filename=filename,
                        is_pdf=is_pdf, pages=pages, sha256=hashlib.sha256(content).hexdigest(), references=refs)
        revision['file'] = f'files/{revision["id"]}.{"pdf" if is_pdf else "bin"}'
        self.file_path(revision['file']).write_bytes(content)
        d['revisions'].append(revision)
        self.save(p, f'{d["title"]}: revision {label} uploaded by {author}')
        return d

    def arrange(self, pid, data):
        p = self.project(pid)
        did = data.get('document_id')
        target = next((s for s in p['sections'] if s['id'] == data.get('section_id')), None)
        if did not in p['documents'] or not target:
            raise ValueError('Document or section not found.')
        for s in p['sections']:
            if did in s['document_ids']:
                s['document_ids'].remove(did)
        position = max(0, min(int(data.get('position', len(target['document_ids']))), len(target['document_ids'])))
        target['document_ids'].insert(position, did)
        return self.save(p, 'Document order updated')

    def add_record(self, pid, data):
        p = self.project(pid)
        if data.get('kind') not in ['comment', 'assumption', 'code']:
            raise ValueError('Unknown record type.')
        p['records'].append(dict(id=uid(), kind=data['kind'], text=required(data, 'text', 6000),
                                 author=required(data, 'author', 120), at=now()))
        return self.save(p, f'{data["kind"].title()} recorded')

    def add_change(self, pid, data):
        p = self.project(pid)
        ids = data.get('document_ids', [])
        if not ids or any(did not in p['documents'] for did in ids):
            raise ValueError('Select at least one affected document from this project.')
        c = dict(id=uid(), title=required(data, 'title', 200), intent=required(data, 'intent', 4000),
                 at=now(), impacts={did: None for did in dict.fromkeys(ids)})
        p['changes'].append(c)
        self.save(p, f'Design change logged: {c["title"]}')
        return c

    def resolve(self, pid, data):
        p = self.project(pid)
        change = next((c for c in p['changes'] if c['id'] == data.get('change_id')), None)
        did = data.get('document_id')
        if not change or did not in change['impacts']:
            raise ValueError('Change impact not found.')
        change['impacts'][did] = dict(revision_id=p['documents'][did]['revisions'][-1]['id'],
                                     note=required(data, 'note', 4000), at=now())
        return self.save(p, f'Impact reviewed: {change["title"]} / {p["documents"][did]["title"]}')

    def checks(self, pid):
        return self.check_project(self.project(pid))

    @staticmethod
    def check_project(p):
        warnings = []
        for c in p['changes']:
            for did, resolution in c['impacts'].items():
                if not resolution:
                    warnings.append(f'Unresolved change: {c["title"]} / {p["documents"][did]["title"]}')
        for d in p['documents'].values():
            for ref in d['revisions'][-1]['references']:
                target = p['documents'][ref['document_id']]
                if target['revisions'][-1]['id'] != ref['revision_id']:
                    warnings.append(f'Stale reference: {d["title"]} references an older revision of {target["title"]}')
        return warnings

    def compile(self, pid, data):
        from .reports import compile_report
        p = self.project(pid)
        warnings = self.check_project(p)
        issue = bool(data.get('issue', False))
        if issue and warnings:
            raise ValueError('Issue blocked. Resolve all change impacts and stale references first.')
        package = compile_report(p, self, data, warnings)
        p['packages'].append(package)
        self.save(p, f'{"Issued" if issue else "Draft"} package compiled: {package["id"][:8]}')
        return package

    def file_path(self, relative):
        path = (self.root / relative).resolve()
        if path.parent != self.root / 'files':
            raise ValueError('Invalid file path.')
        return path

    def compare(self, pid, data):
        from .comparison import compare
        p = self.project(pid)
        revisions = {r['id']: r for d in p['documents'].values() for r in d['revisions']}
        left, right = revisions.get(data.get('left')), revisions.get(data.get('right'))
        if not left or not right or not left['is_pdf'] or not right['is_pdf']:
            raise ValueError('Choose two PDF revisions in this project.')
        return compare(self.file_path(left['file']), self.file_path(right['file']),
                       int(data.get('left_page', 1)), int(data.get('right_page', 1)))

    def _review_job(self, pid, job_id):
        self.project(pid)  # project ownership / existence check
        with self.connection() as conn:
            row = conn.execute('SELECT data FROM review_jobs WHERE id=? AND project_id=?', (job_id, pid)).fetchone()
        if not row:
            raise ValueError('Calculation review not found in this project.')
        job = json.loads(row[0])
        return self._check_review_owner(pid, job)

    def _check_review_owner(self, pid, job):
        if job['status'] in ('queued', 'running') and job.get('owner_pid'):
            if not _process_alive(job['owner_pid']):
                job.update(status='failed', message='Previous application session stopped. Start a new comparison.', error='Review interrupted by application shutdown.')
                self._save_review_job(pid, job)
        return job

    def _save_review_job(self, pid, job):
        with self.connection() as conn:
            conn.execute('INSERT OR REPLACE INTO review_jobs VALUES (?, ?, ?)', (job['id'], pid, json.dumps(job)))

    def review_jobs(self, pid):
        self.project(pid)
        with self.connection() as conn:
            rows = conn.execute('SELECT data FROM review_jobs WHERE project_id=?', (pid,)).fetchall()
        jobs = [self._check_review_owner(pid, json.loads(row[0])) for row in rows]
        return [{k: v for k, v in job.items() if k != 'result'} for job in sorted(jobs, key=lambda j: j['at'], reverse=True)]

    def review_start(self, pid, data):
        from concurrent.futures import ProcessPoolExecutor
        from multiprocessing import get_context
        p = self.project(pid)
        revisions = {r['id']: r for d in p['documents'].values() for r in d['revisions']}
        left, right = revisions.get(data.get('left')), revisions.get(data.get('right'))
        if not left or not right or not left['is_pdf'] or not right['is_pdf'] or left['id'] == right['id']:
            raise ValueError('Choose different earlier and newer PDF revisions in this project.')
        if any(j['status'] in ('queued', 'running') for j in self.review_jobs(pid)):
            raise ValueError('A calculation review is already running for this project.')
        job = dict(id=uid(), at=now(), left=left['id'], right=right['id'], status='queued', progress=0,
                   message='Waiting to compare PDFs', owner_pid=os.getpid(), earlier_name=left['filename'], newer_name=right['filename'])
        self._save_review_job(pid, job)
        # MuPDF is not thread-safe. Run comparison in a separate spawned process;
        # the HTTP server remains responsive while large packages are analyzed.
        if not hasattr(self, '_review_pool'):
            self._review_pool = ProcessPoolExecutor(max_workers=1, mp_context=get_context('spawn'))
        future = self._review_pool.submit(_execute_review, str(self.root), pid, job['id'])
        def failed(f):
            try:
                exc = f.exception()
            except Exception as error:
                exc = error
            if exc:
                saved = self._review_job(pid, job['id'])
                saved.update(status='failed', message='Review process stopped. Restart the review.', error=str(exc)[:1000])
                self._save_review_job(pid, saved)
        future.add_done_callback(failed)
        return job

    def review_update(self, pid, data):
        from .revision_review import validate_findings
        job = self._review_job(pid, required(data, 'job_id', 80))
        if job['status'] != 'complete':
            raise ValueError('Wait for the calculation comparison to finish.')
        incoming = data.get('findings')
        result = job['result']
        validate_findings(incoming, result['newer_pages'])
        original = {f['id']: f for f in result['findings']}
        cleaned = []
        p = self.project(pid)
        newer = next(r for d in p['documents'].values() for r in d['revisions'] if r['id'] == job['right'])
        for f in incoming:
            if f['id'] in original:
                saved = dict(original[f['id']])
                # Evidence locations/direction cannot be forged by a UI edit.
                for key in ('title', 'summary', 'category', 'priority', 'disposition'):
                    saved[key] = f[key]
            else:
                if not f['id'].startswith('M'):
                    raise ValueError('New manual findings must have IDs beginning with M.')
                import pymupdf as fitz
                with fitz.open(self.file_path(newer['file'])) as doc:
                    page = doc[f['newer_page'] - 1]
                    target = str(f.get('target_text', '')).strip()
                    matches = page.search_for(target) if target else []
                    if target and not matches:
                        raise ValueError('Target text was not found on the selected newer PDF page.')
                    rect = list(matches[0]) if matches else [40, 40, min(250, page.rect.width - 30), 70]
                saved = {k: f.get(k) for k in ('id', 'title', 'summary', 'category', 'priority', 'disposition', 'newer_page')}
                saved.update(rect=rect, earlier_page=None, confidence='manual', kind='manual', section='Manual finding')
            cleaned.append(saved)
        if not set(original).issubset({f['id'] for f in cleaned}):
            raise ValueError('Keep existing findings and mark unwanted items Exclude.')
        result['findings'] = sorted(cleaned, key=lambda f: (f['priority'], f['newer_page'], f['id']))
        job['reviewed_at'] = now()
        self._save_review_job(pid, job)
        return job

    def review_export(self, pid, data):
        from .revision_review import export_callouts, file_sha256
        job = self._review_job(pid, required(data, 'job_id', 80))
        if job['status'] != 'complete':
            raise ValueError('Wait for the calculation comparison to finish.')
        p = self.project(pid)
        newer = next(r for d in p['documents'].values() for r in d['revisions'] if r['id'] == job['right'])
        if file_sha256(self.file_path(newer['file'])) != job['result']['newer_sha256']:
            raise ValueError('The newer source PDF changed after comparison. Run a new review.')
        export_id = uid()
        relative = f'files/{export_id}.pdf'
        output = self.file_path(relative)
        try:
            details = export_callouts(self.file_path(newer['file']), output, job['result']['findings'])
        except Exception:
            output.unlink(missing_ok=True)
            raise
        item = dict(id=export_id, file=relative, is_pdf=True, at=now(), job_id=job['id'],
                    earlier_revision_id=job['left'], newer_revision_id=job['right'],
                    source_sha256=job['result']['newer_sha256'], sha256=file_sha256(output), **details,
                    findings=[f for f in job['result']['findings'] if f['disposition'] == 'include'])
        # Reload after the long PDF write so simultaneous project changes survive.
        p = self.project(pid)
        p.setdefault('reviews', []).append(item)
        self.save(p, f'Calculation review exported: {details["callout_count"]} individual callouts')
        return item


def _execute_review(root, pid, job_id):
    """Spawn-safe worker; progress is stored separately from project mutations."""
    from .revision_review import compare_calculations
    ws = Workspace(root)
    job = ws._review_job(pid, job_id)
    def progress(percent, message):
        job.update(status='running', progress=percent, message=message)
        ws._save_review_job(pid, job)
    try:
        p = ws.project(pid)
        revisions = {r['id']: r for d in p['documents'].values() for r in d['revisions']}
        progress(0, 'Opening calculation packages')
        result = compare_calculations(ws.file_path(revisions[job['left']]['file']),
                                      ws.file_path(revisions[job['right']]['file']), progress)
        job.update(status='complete', progress=100, message='Candidates ready for review', result=result)
    except Exception as exc:
        job.update(status='failed', message='Calculation review failed', error=str(exc)[:1500])
    ws._save_review_job(pid, job)
