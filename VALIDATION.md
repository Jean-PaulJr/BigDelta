# Validation record

Validated on Windows with Python 3.12.14 and the exact dependency versions in requirements.txt.

## Test-driven development

- Wrote the core domain/PDF acceptance suite before implementation; the initial run failed because the service module did not exist.
- Implemented SQLite workspace operations, report compilation, and drawing comparison against those tests.
- Added HTTP integration and stronger PDF destination/source-integrity/overlay checks. Observed the new checks fail, then corrected explicit PDF page destinations, source checksum verification, and overlay channels.
- Added an annotated-PDF regression after a real project exposed untyped dictionary keys in the footer annotation translation. Observed the exact "Key must be a PdfObject" failure, then corrected both rectangle and quad-point keys to `NameObject` and checked their translated coordinates and retained URL.
- Final automated result: **25 tests passed** using `python -m unittest discover -s tests -v`.
- Browser JavaScript syntax checked with `node --check bigdelta/static/app.js`.

## Automated coverage

- Separate projects and persisted state after reopening the workspace.
- Immutable prior revisions, unique revision labels, current revision selection, original hashes.
- Invalid PDF rejection, non-PDF attachment retention, and path traversal rejection.
- Custom section templates and safe handling of occupied sections; ordered report contents.
- Explicit document references, project boundaries, one revision per referenced document, and stale-reference issue blocking.
- Per-document design-change impacts and revision-pinned resolution notes.
- Cover, workflow review fields, nested bookmarks, linked TOC destinations, continuous page numbers, and current source content.
- Multi-page TOCs, landscape source sheets, flowing multi-page assumptions/code registers.
- Immutable output package snapshots and revision manifests; detection of modified stored source files.
- Identical and changed PDF comparisons, old/new overlay colours, page-range and sheet-size checks.
- Packaged browser resources, request tokens, same-origin and Host checks, unknown download rejection.

## Browser workflow exercised

Using the local application in the in-app browser:

1. Created “River House · Demo” with project number and client.
2. Uploaded an illustrative framing PDF as P01.
3. Uploaded P02 under the same document; confirmed two revisions remained.
4. Compared P01/P02 and received a rendered overlay with 1.1349% of pixels changed.
5. Customized the template to remove unused sections.
6. Compiled a draft through the UI and confirmed its package and manifest links appeared.
7. Logged an opening coordination change affecting the drawing; confirmed the coordination count rose to one.
8. Recorded a resolution at P02; confirmed the count returned to zero and the review note remained visible.

## PDF visual QA

Rendered the five-page example package with PDFium and Poppler and inspected the cover, linked contents, section divider, landscape source drawing, and assumptions/code register. Text, margins, footer placement, and page numbering were readable and unobstructed. The example files are clearly marked as illustrative and do not contain engineering calculations or approvals.

## Limits of verification

macOS and Linux execution were not available. Portable source, launch instructions, browser-native SVG branding, and platform-neutral storage paths are included. No standalone native installer or multiuser deployment was built. Structural correctness, professional approval, semantic drawing understanding, full multilingual typesetting, and full interoperability with every PDF producer are outside the verified scope.


## Calculation revision review - 27 October 2026

- `python -m unittest discover -s tests -v`: 42 tests passed, including inserted-page alignment, exclusion of node-load tables/continuations/assignments, same-section result grouping, pass/fail transitions in both directions, formula-outcome filtering, moved checks, graphics coverage gaps, inconsistent printed bolt strengths, native callout intent/leader arrays, source preservation, source-hash protection, background process execution, review editing/export, and project isolation.
- `node --check bigdelta/static/app.js` and `git diff --check`: passed.
- Live local HTTP exercise: start the real application, compare uploaded revisions in a spawned worker, poll progress, include findings, save decisions, export a PDF, and download it through the existing authorized-file route. Passed with two exported callouts.
- Orion Revision 5 supplied pair (6,579 / 6,584 pages): approximately 10 seconds in this environment; 6,568 pages matched unchanged. The rules produced 118 reviewable candidates and retained 338 unclassified text/formula fragments separately. The 105 ksi / 50 ksi printed bolt-yield inconsistency was detected as a potential propagation finding. This automated candidate list is intentionally not represented as equivalent to the earlier 29-item manual engineering review.
- Exported that real-package finding, reopened the 6,584-page PDF, verified a native `FreeTextCallout`, and visually inspected the rendered affected page. Existing reviewer annotations were preserved; the new callout was readable in its external margin.
- Full browser interaction was not executed: Playwright's browser executable is absent in this environment. JavaScript syntax and live HTTP behavior were checked; desktop/browser UI interaction remains a validation limitation.

## Windows calculation review connection fix - 27 October 2026

- Replaced `os.kill(pid, 0)` on Windows with read-only process synchronization queries. Windows treats signal zero as process termination, so polling a running review could shut down the HTTP server and display "Failed to fetch".
- Added a guarded module entry point and a useful connection-loss message in the interface.
- All 48 unit tests passed. New regressions cover Windows API routing without signals, live/exited/inaccessible processes, handle cleanup on failure, and interrupted-job recovery. Windows API responses were mocked on Linux; native Windows execution was not available.
- Live HTTP comparison, progress polling, decisions, callout export and download passed. JavaScript syntax, Python compilation and whitespace checks passed.
