"""Local workspace services. All revision and package files use immutable UUID names."""
import base64
import hashlib
import io
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

from pypdf import PdfReader

PHASES = ['Planning', 'Design', 'Construction', 'Closeout']
TASK_STATUSES = ['on hold', 'complete', 'in progress']


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
    @staticmethod
    def normalize(p):
        p.setdefault('rfis', [])
        p.setdefault('cover', dict(generated_by='', checked_by='', approved_by=''))
        if 'tasks' not in p:
            p['legacy_progress'] = p.get('progress', 0)
            p['tasks'] = []
        total = len(p['tasks'])
        p['progress'] = int(100 * sum(t['status'] == 'complete' for t in p['tasks']) / total + 0.5) if total else 0
        return p

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
        self.normalize(p)
        p['updated'] = now()
        p['events'].append({'at': now(), 'action': action})
        with self.connection() as conn:
            conn.execute('INSERT OR REPLACE INTO projects VALUES (?, ?)', (p['id'], json.dumps(p)))
        return p

    def projects(self):
        with self.connection() as conn:
            rows = conn.execute('SELECT data FROM projects').fetchall()
        return sorted([self.normalize(json.loads(x[0])) for x in rows], key=lambda p: p['updated'], reverse=True)

    def project(self, pid):
        with self.connection() as conn:
            row = conn.execute('SELECT data FROM projects WHERE id=?', (pid,)).fetchone()
        if not row:
            raise ValueError('Project not found.')
        return self.normalize(json.loads(row[0]))

    def create_project(self, data):
        p = dict(id=uid(), name=required(data, 'name', 160), number=str(data.get('number', ''))[:80],
                 client=str(data.get('client', ''))[:160], phase='Planning', progress=0,
                 documents={}, changes=[], records=[], packages=[], events=[], sections=[], tasks=[])
        for name in ['Design basis', 'Gravity systems', 'Lateral systems', 'Foundations', 'Drawings', 'Specifications']:
            p['sections'].append(dict(id=uid(), name=name, document_ids=[]))
        return self.save(p, 'Project created')

    def update_project(self, pid, data):
        p = self.project(pid)
        if data.get('phase') not in PHASES:
            raise ValueError('Choose a valid project phase.')
        p['phase'] = data['phase']
        return self.save(p, f'Current phase changed to {p["phase"]}')

    @staticmethod
    def project_summary(p):
        tasks=p['tasks']
        complete=sum(t['status']=='complete' for t in tasks)
        status='No tasks' if not tasks else 'Complete' if complete==len(tasks) else 'In progress' if any(t['status']=='in progress' for t in tasks) else 'On hold'
        return dict(id=p['id'],name=p['name'],number=p['number'],client=p['client'],phase=p['phase'],
            status=status,progress=p['progress'],completed_tasks=complete,total_tasks=len(tasks),
            open_rfis=sum(r['status']=='Open' for r in p['rfis']),closed_rfis=sum(r['status']=='Closed' for r in p['rfis']),
            documents=len(p['documents']),coordination_items=len(Workspace.check_project(p)),updated=p['updated'])

    @staticmethod
    def apply_details(p, data):
        for key, limit in [('name',160),('number',80),('client',160)]:
            if key in data:
                value=str(data[key]).strip()
                if len(value)>limit or (key=='name' and not value):
                    raise ValueError(f'Project {key} must contain {"1-" if key=="name" else "at most "}{limit} characters.')
                p[key]=value

    def update_details(self, pid, data):
        p=self.project(pid)
        self.apply_details(p,data)
        return self.save(p,'Project name, number, and client updated')

    def update_cover(self, pid, data):
        p=self.project(pid)
        self.apply_details(p,data)
        for key in ['generated_by','checked_by','approved_by']:
            if key in data:
                value=str(data[key]).strip()
                if len(value)>160:
                    raise ValueError('Cover review names must be no longer than 160 characters.')
                p['cover'][key]=value
        return self.save(p,'Report cover page updated')

    def save_rfi(self, pid, data):
        p=self.project(pid)
        rfi_id=data.get('rfi_id')
        existing=next((r for r in p['rfis'] if r['id']==rfi_id),None)
        if rfi_id and not existing:
            raise ValueError('RFI not found in this project.')
        rfi=dict(existing) if existing else dict(id=uid(),number=f'RFI-{len(p["rfis"])+1:03d}',
            description='',requested_by='',sent_to='',sent_date='',response='',status='Open',created=now())
        for key in ['description','requested_by','sent_to','sent_date','response','status']:
            if key in data:
                rfi[key]=str(data[key]).strip()
        for key,limit in [('description',6000),('requested_by',160),('sent_to',160),('sent_date',10)]:
            rfi[key]=required(rfi,key,limit)
        if rfi['status'] not in ['Open','Closed']:
            raise ValueError('RFI status must be Open or Closed.')
        if len(rfi['response'])>12000:
            raise ValueError('RFI response must be no longer than 12000 characters.')
        try:
            if date.fromisoformat(rfi['sent_date']).isoformat()!=rfi['sent_date']:
                raise ValueError()
        except ValueError as exc:
            raise ValueError('Enter a valid date sent in YYYY-MM-DD format.') from exc
        rfi['updated']=now()
        if existing:
            p['rfis'][p['rfis'].index(existing)]=rfi
        else:
            p['rfis'].append(rfi)
        return self.save(p,f'{rfi["number"]} {"updated" if existing else "added"}: {rfi["status"]}; {rfi["requested_by"]} to {rfi["sent_to"]}')

    def save_task(self, pid, data):
        p = self.project(pid)
        task_id = data.get('task_id')
        existing = next((t for t in p['tasks'] if t['id'] == task_id), None)
        if task_id and not existing:
            raise ValueError('Task not found in this project.')
        task = dict(existing) if existing else dict(id=uid(), title='', phase=p['phase'], status='in progress',
                                                  estimated_date='', completed_date='', notes='', created=now())
        for key in ['title', 'phase', 'status', 'estimated_date', 'completed_date', 'notes']:
            if key in data:
                task[key] = str(data[key]).strip()
        task['title'] = required(task, 'title', 240)
        if task['phase'] not in PHASES or task['status'] not in TASK_STATUSES:
            raise ValueError('Choose a valid task phase and status.')
        if len(task['notes']) > 6000:
            raise ValueError('Task notes must be no longer than 6000 characters.')
        if task['status'] != 'complete':
            task['completed_date'] = ''
        if task['status'] == 'complete' and not task['completed_date']:
            raise ValueError('Enter an actual completion date for a complete task.')
        for key in ['estimated_date', 'completed_date']:
            value = task[key]
            if value:
                try:
                    if date.fromisoformat(value).isoformat() != value:
                        raise ValueError()
                except ValueError as exc:
                    raise ValueError('Task dates must be valid calendar dates in YYYY-MM-DD format.') from exc
        task['updated'] = now()
        if existing:
            p['tasks'][p['tasks'].index(existing)] = task
        else:
            p['tasks'].append(task)
        return self.save(p, f'Task {"updated" if existing else "added"}: {task["title"]} / {task["phase"]} / {task["status"]}')

    def template(self, pid, data):
        p = self.project(pid)
        existing = {s['id']: s for s in p['sections']}
        by_name = {s['name']: s for s in p['sections']}
        rows = data.get('sections')
        if rows is None:
            rows = [dict(id=by_name[n]['id'] if n in by_name else None, name=n)
                    for n in [str(x).strip() for x in data.get('names', [])]]
        if not isinstance(rows, list) or not rows or len(rows) > 100 or any(not isinstance(r, dict) for r in rows):
            raise ValueError('Enter 1-100 report sections.')
        names = [required(r, 'name', 120) for r in rows]
        if len({n.casefold() for n in names}) != len(names):
            raise ValueError('Enter 1-100 unique section names, up to 120 characters each.')
        ids = [r.get('id') for r in rows if r.get('id')]
        if len(set(ids)) != len(ids) or any(sid not in existing for sid in ids):
            raise ValueError('Section IDs must be unique and belong to this project.')
        for s in p['sections']:
            if s['id'] not in ids and s['document_ids']:
                raise ValueError(f'Move documents out of "{s["name"]}" before removing the section.')
        p['sections'] = [dict(id=r.get('id') or uid(), name=name,
                              included=existing[r['id']].get('included', True) if r.get('id') else True,
                              document_ids=existing[r['id']]['document_ids'] if r.get('id') else [])
                         for r, name in zip(rows, names)]
        return self.save(p, 'Report template updated')

    def update_section(self, pid, data):
        p = self.project(pid)
        section = next((s for s in p['sections'] if s['id'] == data.get('section_id')), None)
        if not section:
            raise ValueError('Section not found in this project.')
        if 'included' in data:
            if not isinstance(data['included'], bool):
                raise ValueError('Section inclusion must be true or false.')
            section['included'] = data['included']
        old_name = section['name']
        if 'name' in data:
            name = required(data, 'name', 120)
            if any(s['id'] != section['id'] and s['name'].casefold() == name.casefold() for s in p['sections']):
                raise ValueError('A section with this title already exists.')
            section['name'] = name
        if 'position' in data:
            position = int(data['position'])
            if not 0 <= position < len(p['sections']):
                raise ValueError('Choose a position within the report sections.')
            p['sections'].remove(section)
            p['sections'].insert(position, section)
        return self.save(p, f'Section updated: {old_name} -> {section["name"]}, position {p["sections"].index(section)+1}, included in report: {section.get("included", True)}')

    def add_section(self, pid, data):
        p = self.project(pid)
        name = required(data, 'name', 120)
        if len(p['sections']) >= 100:
            raise ValueError('A report can contain up to 100 sections.')
        if any(s['name'].casefold() == name.casefold() for s in p['sections']):
            raise ValueError('A section with this title already exists.')
        position = int(data.get('position', len(p['sections'])))
        if not 0 <= position <= len(p['sections']):
            raise ValueError('Choose a position within the report sections.')
        p['sections'].insert(position, dict(id=uid(), name=name, document_ids=[]))
        return self.save(p, f'Section added: {name}, position {position+1}')

    def delete_section(self, pid, data):
        p = self.project(pid)
        section = next((s for s in p['sections'] if s['id'] == data.get('section_id')), None)
        if not section:
            raise ValueError('Section not found in this project.')
        if len(p['sections']) == 1:
            raise ValueError('Keep at least one report section. Add another section before deleting this one.')
        destination = None
        if section['document_ids']:
            destination = next((s for s in p['sections'] if s['id'] == data.get('destination_id') and s['id'] != section['id']), None)
            if not destination:
                raise ValueError('Choose another section to receive the documents before deleting this section.')
            destination['document_ids'].extend(section['document_ids'])
        p['sections'].remove(section)
        action = f'Section deleted: {section["name"]}'
        if destination:
            action += f'; {len(section["document_ids"])} documents moved to {destination["name"]}'
        return self.save(p, action)

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
        options={**p['cover'],**data}
        package = compile_report(p, self, options, warnings)
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
