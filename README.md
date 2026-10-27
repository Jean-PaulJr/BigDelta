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
- Documents whose current revision is a PDF are compiled. Other files (drawings, specifications, estimates, source models, spreadsheets, responses) are stored and versioned as attachments; export them to PDF to include them in the report. A current non-PDF revision excludes that document from the package, even if an older PDF revision exists. Password-protected and empty PDFs are rejected. Each upload is limited to 40 MB.
- Existing source-page content is retained with a 26-point external footer strip. Package numbers and contents references update; page references printed inside uploaded calculations are not rewritten. Source file signatures cannot authenticate an assembled derivative PDF; original bytes remain available in History.
- Comparison uses rendered pixels, capped at 1,600 pixels on the longest edge, with a fixed difference threshold. It is intended for aligned drawing exports; no registration, OCR, or semantic change recognition is implemented.
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
