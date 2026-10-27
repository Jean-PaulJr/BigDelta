# bigdelta/ — Application Package

Five modules with distinct responsibilities. Don't let domain logic leak into `server.py` or PDF mechanics into `service.py`.

## Module Roles

### server.py — HTTP Adapter
Routes GET/POST requests to `Workspace` methods. Owns all security enforcement:
- Binds to `127.0.0.1` only (`SO_EXCLUSIVEADDRUSE` on Windows)
- Per-session CSRF token (`secrets.token_urlsafe(32)`); sent as `X-Token` header
- Host and Origin header validation on every POST
- Content-Length cap: 165 MiB total / 120 MiB per file
- File downloads: only UUID-named files referenced by saved projects (path traversal prevention)
- Route pattern: `/api/projects/{pid}/{action}` dispatches to `Workspace` method by name

### service.py — Domain Logic
`Workspace` class owns all project state. Key patterns:
- `with self.connection()` for every SQLite operation — no long-lived connections
- Full project state serialized as JSON in the `data` column; no relational decomposition
- Every mutating action appends `{"when": now(), "what": "..."}` to `p["events"]`
- `required(value, max_len)` enforces non-empty strings with length limits
- File integrity: SHA-256 checksums stored at upload; re-verified on compile
- Stale-reference detection: if a referenced revision isn't the latest, flag dependent docs
- `review_jobs` table tracks background calculation review state

### reports.py — PDF Compilation
Builds the final package PDF. Layer order matters:
1. ReportLab generates cover, section dividers, TOC text, assumptions/code register as standalone PDFs
2. pypdf merges these with source PDFs in order
3. Footer canvas overlays page numbers on every merged page (26pt external strip)
4. Bookmarks: section hierarchy → document entries → any preserved source bookmarks
5. Links: quad-point destinations recalculated per accumulated page offset
6. Warnings inline: "Stale reference" and "Unresolved change" appear in the register

### comparison.py — Raster Diff
Renders both PDF pages at ≤1,600 px edge via pypdfium2, then:
- Requires matching page size/orientation — raises otherwise
- Pixel diff threshold: 35 (0–255 scale), grayscale
- Overlay channels: old=magenta (R), new=cyan (G+B), coincident=dark
- Changed regions highlighted orange (#ef794d) via morphological filter
- Returns base64 PNG strings embedded in JSON

### revision_review.py — Calculation Review (515 lines)
Rule-based (no AI), runs in a `ProcessPoolExecutor` to isolate MuPDF threads:
- **Fingerprinting**: page content stream + XObjects + images → SHA-256; unchanged pages skipped
- **Page matching**: fingerprint comparison + bookmark-based section tracking
- **Text extraction**: PyMuPDF grouped into visual rows by baseline proximity
- **Classification**: regex patterns for loading, assumptions, geometry, results, acceptance criteria
- **Removal detection**: disappeared text flagged; relocation not auto-ruled-out
- **Grouping**: applied-load updates aggregate related result rows
- **Exclusions**: node-load tables, continuations, assignments filtered explicitly
- **Callout export**: PyMuPDF `FreeTextCallout` with leader array; source annotations preserved
- Review JSON shape: `{candidates: [{priority, text, category, disposition}]}`

## Shared Conventions

- `now()` returns ISO 8601 UTC string for all event timestamps
- UUIDs generated with `uuid.uuid4()` for all file and job IDs
- Errors bubble to `server.py` which catches and returns 400/500 with JSON body
- No threading in the HTTP server — requests handled synchronously
- Background review uses `ProcessPoolExecutor`; progress polled via `/api/projects/{pid}/review_status`
