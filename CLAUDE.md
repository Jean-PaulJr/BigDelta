# BigDelta

Local Python app for structural engineers: manage design projects, preserve document revisions, capture design intent, and compile traceable PDF report packages. Single-user, loopback-only, no cloud sync.

## Setup

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Run

```powershell
.venv\Scripts\python -m bigdelta                          # default: port 8879, data/ dir
.venv\Scripts\python -m bigdelta --port 8880              # custom port
.venv\Scripts\python -m bigdelta --data C:\path\to\data   # custom workspace
.venv\Scripts\python -m bigdelta --no-browser             # skip auto-open
```

Opens `http://127.0.0.1:8879`. Stop with Ctrl+C.

On subsequent runs, double-click `start_windows.bat`.

## CLI Commands (after `pip install -e .`)

```powershell
bigdelta                                                           # launch server
bigdelta-review compare earlier.pdf newer.pdf --output review.json
bigdelta-review export newer.pdf review.json --output reviewed.pdf
```

## Test

```powershell
.venv\Scripts\python -m unittest discover -s tests -v   # 42 tests
node --check bigdelta/static/app.js                      # JS syntax check
```

## Architecture

```
bigdelta/
  server.py          # loopback HTTP adapter, token CSRF, routing
  service.py         # domain logic, SQLite workspace, all project operations
  reports.py         # ReportLab PDF generation + pypdf assembly
  comparison.py      # raster page diff via pypdfium2 + Pillow
  revision_review.py # rule-based calc review, PyMuPDF text extraction, callout export
  static/            # vanilla JS/HTML/CSS single-page frontend
tests/               # unittest acceptance suite
examples/            # reference PDFs and manifest for workflow testing
data/                # runtime SQLite + immutable UUID-named files (git-ignored)
```

**Key design principles:**
- Immutable revisions: uploaded files get UUID names; checksums verified on compile
- Append-only event log: every action appends to `p['events']` with timestamp
- No ORM: direct SQLite with `with self.connection()` context managers
- Explicit coordination: changes and resolutions recorded by the engineer, never inferred
- Security perimeter: loopback-only bind, token CSRF, Host/Origin validation, path traversal prevention

## Data

- SQLite at `data/bigdelta.sqlite3` — two tables: `projects`, `review_jobs`; full JSON state per row
- Files at `data/files/{uuid}.pdf` — immutable, content-addressed
- Back up by copying the entire `data/` folder; no migrations needed
- No delete via UI (append-only by design)

## Dependencies

| Library | Purpose |
|---------|---------|
| `pypdf` | PDF merge, bookmarks, annotations, links |
| `reportlab` | Procedural PDF generation (covers, TOC, registers) |
| `pypdfium2` | Page rasterization for visual diff |
| `Pillow` | Pixel comparison and overlay images |
| `PyMuPDF` | Text extraction and native FreeTextCallout annotations |

See `SOURCES.md` for licenses. PyMuPDF is AGPL/commercial — review before redistribution.
