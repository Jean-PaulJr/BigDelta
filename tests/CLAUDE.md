# tests/ — Acceptance Test Suite

42 tests using Python `unittest`. Tests are written to acceptance criteria — they verify observable behavior, not implementation details.

## Files

| File | Covers |
|------|--------|
| `test_bigdelta.py` | Core domain: project isolation, revisions, PDF compilation, TOC, bookmarks, registers, stale refs, change resolution |
| `test_http.py` | HTTP security: token validation, Host/Origin checks, unknown downloads, CORS |
| `test_revision_review.py` | Calculation review: fingerprinting, page matching, classification, grouping, exclusions, callout export |

## Run

```powershell
.venv\Scripts\python -m unittest discover -s tests -v
```

## Conventions

- Each test class creates an isolated temp `Workspace` in `setUp`
- `pdf()` helper in `test_bigdelta.py` generates minimal valid PDFs via ReportLab for upload
- No mocks for the database — tests hit a real SQLite file in a temp directory
- Assertions check returned dicts/lists, file existence on disk, and PDF structural integrity (page count, bookmark presence)
- `test_revision_review.py` includes a live browser exercise: starts the app, compares two revisions, polls progress, exports PDF

## Adding Tests

- New domain behavior → `test_bigdelta.py`
- New HTTP endpoint or security check → `test_http.py`
- New review classification or callout behavior → `test_revision_review.py`
- Match the existing pattern: small focused test methods, descriptive names, real files not mocks
