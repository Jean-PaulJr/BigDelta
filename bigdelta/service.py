"""Local workspace services. All revision and package files use immutable UUID names."""
import base64
import hashlib
import io
import json
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
        if not content or len(content) > 40 * 1024 * 1024:
            raise ValueError('File must contain data and be smaller than 40 MB.')
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
