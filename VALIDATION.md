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
