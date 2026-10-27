# BigDelta

A working local Python application for structural engineers. Manage multiple projects, preserve document revisions, capture design intent, and compile repeatable PDF report packages. The interface opens in your browser; documents and metadata stay in a local SQLite workspace.

## Start on Windows

Install Python 3.11 or newer from [python.org](https://www.python.org/downloads/). Extract the application into a writable folder, open a terminal in that folder, then run:

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m bigdelta
```

After setup, double-click `start_windows.bat` to launch it again.

## Start on macOS or Linux

With Python 3.11 or newer installed, open a terminal in the extracted folder:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m bigdelta
```

On macOS you can subsequently run `sh start_mac.command` from that folder. To enable double-click launching, run `chmod +x start_mac.command` once.

Open [BigDelta on this computer](http://127.0.0.1:8879). Stop it with Ctrl+C in the terminal. If the port is in use, add `--port 8880` and open the address printed in the terminal.

The source uses portable Python, pathlib, SQLite, browser HTML/CSS/JavaScript, and an embedded SVG logo. Hardware brand is not significant. Windows was tested here; macOS/Linux source compatibility is designed in, but those operating systems have not been executed in this environment. Dependency wheels must be available for your Python version and CPU architecture. Python and dependencies are required; this delivery is source code, not a standalone installer.

## Your first project

1. Create a project with its name, number, and client.
2. Choose **Edit template** to add, remove, or reorder section names. Export/import a JSON template to reuse it. Empty sections are omitted from reports. Move existing documents before removing their section.
3. Choose **Add documents** and select multiple PDFs or attachments. Provide a revision label, author, and reason for change. Multi-file selections are appended in filename order. Use the arrows or **Move** to specify each file's exact position.
4. Use **+ Revision** on an existing document for replacements. Each revision retains its original file, timestamp, note, author, SHA-256 checksum, and explicitly declared document references. **History** downloads any prior version.
5. In **Project journal**, record assumptions and cite each applicable engineering code with its title, adopted edition, section, and source URL. Add comments and lessons for later education.
6. In **Design changes**, log criteria or geometry changes, record the design intent, and select every affected document. Update or review each document and record an impact resolution. An old drawing can be reviewed as still valid; a resolution does not require a replacement upload.
7. **Compile package** produces a cover, generated/checked/approved fields, linked table of contents, section title pages, nested bookmarks, latest PDF revisions, continuous page numbering, and an assumptions/code register. Contents links and bookmarks are recalculated on every compile. Drafts visibly list open coordination items. Issue is blocked until tracked conflicts are resolved. Download the PDF and its revision manifest under **Compiled packages**.
8. Use **Drawing compare** to select two PDF revisions and page numbers. Choose overlay, highlighted changes, or side by side. Old-only ink appears magenta; new-only ink appears cyan. Matching sheet sizes and aligned exports are required.
9. Use **Overview** to set the lifecycle phase and manual completion percentage. The history records uploads, changes, reviews, compilation, and progress edits. Create more projects from the sidebar.

## What the revision checks mean

Revision labels are user-defined, not sorted alphabetically. The most recently uploaded revision is current. Do not upload an older revision after a newer one unless you intend to supersede it. Reference relationships are recorded explicitly when uploading a revision; when a referenced document gets a newer revision, dependent current documents are flagged. Upload a revised dependent document with refreshed references to clear the flag.

A change remains open until every selected document has a recorded resolution. The resolution pins the revision that was reviewed and preserves the review note. Later document uploads preserve that historic resolution; log a new change if new impacts arise.

This is explicit coordination tracking. Matching labels such as “V3” alone do not prove congruency, and the program does not infer semantic references or structural effects from drawing geometry or calculation text.

## Assumptions and scope

- This version is a single-user local workspace. There is no cloud sync, multiuser editing, identity verification, role permissions, or tamper-proof regulatory audit. Authors and approval names are entered by the operator. The server binds only to loopback and checks local request tokens and origins; do not expose it as a shared network server.
- This is document compilation and coordination software. It does not perform structural analysis, select applicable codes, certify calculations, or validate engineering correctness. No code editions or design values are silently assumed.
- The “generated by / checked by / approved by” fields are recorded names, not cryptographic signatures, professional seals, or proof of approval.
- Documents whose current revision is a PDF are compiled. Other files (drawings, specifications, estimates, source models, spreadsheets, responses) are stored and versioned as attachments; export them to PDF to include them in the report. A current non-PDF revision excludes that document from the package, even if an older PDF revision exists. Password-protected and empty PDFs are rejected. Each upload is limited to 120 MiB.
- Existing source-page content is retained with a 26-point external footer strip. Package numbers and contents references update; page references printed inside uploaded calculations are not rewritten. Source file signatures cannot authenticate an assembled derivative PDF; original bytes remain available in History.
- **Drawing compare** uses rendered pixels, capped at 1,600 pixels on the longest edge, with a fixed difference threshold. It is intended for aligned drawing exports; registration and OCR are not implemented. The separate Calculation review workflow is described below.
- The default template covers common engineering sections. The cover layout is fixed; section structure and review names are configurable. A template is a section-name list, not an arbitrary executable document template.
- Progress is an engineering team's manual assessment. Comments, assumptions, code citations, revisions, and package history are append-only through the interface. Local files can still be edited by someone with filesystem access.
- Generated report text uses standard PDF fonts for portability; Latin text is supported. Full multilingual typesetting is not implemented. Existing PDFs retain their own fonts.

## Storage and backup

By default, `data/` is created in the current working folder. It contains `bigdelta.sqlite3` plus immutable UUID-named files under `files/`. Launch scripts always use the application directory. Select another location with:

```sh
python -m bigdelta --data /path/to/workspace --port 8879
```

`BIGDELTA_DATA` can also set the data path. Stop the app and copy the **entire data folder** for backup or migration between computers. Keep the database and files together. A project register export includes metadata only and is not a full backup. PDFs and JSON templates are portable. The application does not delete uploaded originals or previous compilations.

## Tests and TDD

The project uses Python's built-in `unittest` framework, requiring no separate test runner. Core acceptance tests were written first, observed failing for the missing implementation, then implemented and exercised against real generated PDFs and SQLite storage.

```sh
python -m unittest discover -s tests -v
```

Tests cover project isolation/persistence, immutable revision history and packages, upload validation, section removal and order, stale references, change impact resolution, linked TOCs, bookmarks, pagination including multi-page contents, mixed page orientations, comparison, assumptions/code inclusion, and local HTTP protections. See `VALIDATION.md` for the recorded results.

## Project layout

```text
bigdelta/service.py       SQLite workspace and domain operations
bigdelta/reports.py       ReportLab/pypdf package compiler
bigdelta/comparison.py    PDFium/Pillow raster comparison
bigdelta/revision_review.py  Calculation candidates, priorities and native callouts
bigdelta/server.py        Local HTTP adapter and launch command
bigdelta/static/          Browser interface and embedded vector logo
tests/                   unittest acceptance and HTTP tests
requirements.txt         Exact tested dependency versions
SOURCES.md               Third-party code/API and license references
```

All BigDelta application code and its delta/truss-inspired logo were authored for this project. Third-party dependencies are cited in `SOURCES.md`. Engineering code citations are user-entered project records and appear in the report register.

## Developers

- Damian Valencia
- Jean-Paul Sandrock Jr.

## Calculation revision review

Update the Python environment once after pulling this change:

```powershell
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m bigdelta
```

1. Upload the earlier and newer PDFs using **Add documents** or **+ Revision**. Uploads now accept files up to 120 MiB, including the Orion test packages. Revision labels within one document must be unique even if both PDF covers show the same revision number.
2. Open **Calculation review**, explicitly select **Earlier PDF** and **Newer PDF**, and choose **Analyze calculation packages**. Comparison runs in a separate process; the interface displays progress and saved comparisons.
3. Review each candidate's source page, title, category and change summary. Choose **Include**, **Exclude**, or leave **Pending**. Use **Add finding** for engineering discrepancies the rules cannot interpret; optional exact target text locates the callout on its newer source page.
4. **Save decisions**, then **Export callout PDF**. Only included findings are exported. Each becomes one native, editable `FreeTextCallout` with a leader line and visible description. An external review margin keeps callout text away from calculations. Existing source content, annotations, page positions and bookmarks are preserved. Exports use immutable file names and retain the reviewed finding snapshot.
5. Download under **Exported callout copies**. **Export review JSON** includes candidates, grouped results, unclassified formula/text fragments and coverage gaps.

Review priorities, in order:

1. Acceptance changes in either direction.
2. Fundamental assumptions.
3. Loading conditions and combinations.
4. Disappeared checks, marked as possible removal until relocation/replacement is ruled out.
5. Inputs without downstream updates; includes a candidate check for inconsistent printed bolt yield strengths within a revised calculation section.
6. Geometry and material grades.
7. Conclusions that conflict with explicit failing results.

Calculated-demand, reaction, capacity and acceptance values are grouped when an applied-load update is identified in the **same calculation section**. Pass/fail transitions remain separate. Top-level PDF bookmarks establish sections; without them, grouping is conservatively limited to the same page. **Node-load tables and individual node-load assignments are excluded.** Connection reactions remain in scope.

This is a local, rule-based review assistant, not an automatic structural checker. It produces reviewable text-change candidates; it cannot reproduce every interpretation in a human engineering review. Scans need searchable text. Unlabeled equations, numeric-only tables, vector geometry, units/equivalence and complex dependencies may require manual findings. Unclassified fragments and coverage gaps are retained instead of claiming an all-clear. At most 3,000 prioritized candidates are shown per comparison; the coverage list reports any omitted count. Compare smaller sections if that limit is reached. Callout export explicitly rejects rotated/nonstandard cropboxes; normalize those PDFs first. Shorten descriptions or select fewer items if a page cannot hold legible callouts even with a wider margin.

### Python and command-line use

The reusable functions are `compare_calculations(earlier_path, newer_path)` and `export_callouts(newer_path, output_path, findings)` in `bigdelta/revision_review.py`. They make no network/AI calls. Output is a new file, and existing output files are not overwritten.

```sh
python -m bigdelta.revision_review compare earlier.pdf newer.pdf --output review.json
# Review review.json; edit summaries/categories and set chosen dispositions to "include".
python -m bigdelta.revision_review export newer.pdf review.json --output reviewed.pdf
```

Installing the project with `pip install -e .` also provides `bigdelta-review compare ...` and `bigdelta-review export ...`. JSON records the source SHA-256 hashes; export rejects a changed or different newer source file.
