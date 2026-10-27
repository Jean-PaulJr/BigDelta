# Sources, code use, and attribution

BigDelta's Python, HTML, CSS, JavaScript, tests, and logo are original work created for this request. No external UI libraries, fonts, CDNs, or copied application templates are used. The triangle represents delta/change and a structural truss; the amber internal stroke represents a revision.

## Runtime dependencies

| Component | Use | Authoritative documentation / source | License reference |
| --- | --- | --- | --- |
| Python standard library | `unittest`, SQLite, HTTP server, JSON, filesystem paths, UUIDs, hashing | [Python docs](https://docs.python.org/3/), [unittest](https://docs.python.org/3/library/unittest.html), [SQLite context managers](https://docs.python.org/3/library/sqlite3.html#how-to-use-the-connection-context-manager), [http.server](https://docs.python.org/3/library/http.server.html) | [Python license](https://docs.python.org/3/license.html) |
| pypdf 6.10.0 | Read, merge and number PDF pages; bookmarks and linked contents | [PdfWriter API](https://pypdf.readthedocs.io/en/6.10.0/modules/PdfWriter.html), [annotations](https://pypdf.readthedocs.io/en/6.10.0/user/adding-pdf-annotations.html), [project](https://github.com/py-pdf/pypdf) | [BSD-3-Clause](https://github.com/py-pdf/pypdf/blob/main/LICENSE) |
| ReportLab 4.4.9 | Covers, section dividers, TOC text, footer overlays, flowing assumptions/code register | [pdfgen guide](https://docs.reportlab.com/reportlab/userguide/ch2_graphics/), [Platypus guide](https://docs.reportlab.com/reportlab/userguide/ch5_platypus/) | [ReportLab license](https://hg.reportlab.com/hg-public/reportlab/file/tip/LICENSE.txt) |
| pypdfium2 5.14.0 | Render PDF pages for visual comparison | [Python API](https://pypdfium2.readthedocs.io/en/stable/python_api.html), [project](https://github.com/pypdfium2-team/pypdfium2) | [License directory / PDFium notices](https://github.com/pypdfium2-team/pypdfium2/tree/main/LICENSES); bundled PDFium has its own third-party notices |
| Pillow 12.3.0 | Pixel differences, overlays, and PNG comparison output | [ImageChops docs](https://pillow.readthedocs.io/en/stable/reference/ImageChops.html), [project](https://github.com/python-pillow/Pillow) | [HPND license](https://github.com/python-pillow/Pillow/blob/main/LICENSE) |

These libraries are installed from the pinned requirements; this source archive does not redistribute dependency binaries. Their transitive dependencies and native wheels carry their own licenses. Preserve their packaged license notices when creating a standalone distribution.

## Browser file saving

Save As uses the native File System Access API (`showSaveFilePicker`, `createWritable`, `write`, `close`, and `abort`), documented in the [Chrome for Developers guide](https://developer.chrome.com/docs/capabilities/web-apis/file-system-access). Browsers without a save picker use an ordinary download. No additional browser library is used.

## Engineering code citations

No engineering formula or specific adopted building-code provision is implemented or assumed. Project users record each code's title, adopted edition, section, and URL in **Project journal → Code citation**. These records are compiled into the final report. No proprietary standards text is bundled. User-provided calculation PDFs remain the engineering sources of record.

## Calculation revision review

- PyMuPDF 1.26.6: PDF text/location extraction, page matching resources, and native `FreeTextCallout` annotations. Official API: https://pymupdf.readthedocs.io/en/latest/page.html#Page.add_freetext_annot . License information: https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright . Review the applicable PyMuPDF licensing terms before distributing a derivative application.
- Python standard library `concurrent.futures.ProcessPoolExecutor`: isolated background comparisons so MuPDF operations do not share threads.
- The rule categories and exclusions implement the project owner's calculation-review requirements; they are not engineering-code compliance rules.
