# examples/ — Reference Files

Illustrative files for manually exercising the workflow. Not engineering calculations — for demo and visual QA only.

## Files

| File | Purpose |
|------|---------|
| `Framing-P01.pdf` | Drawing revision P01 (baseline) |
| `Framing-P02.pdf` | Drawing revision P02 — same sheet with relocated opening |
| `example-package.pdf` | Compiled 5-page output: cover, linked TOC, section divider, landscape sheet, assumptions register |
| `example-manifest.json` | Package metadata: revision IDs, document titles, labels (IDs are demo-only, not reusable) |

## Workflow Exercise

1. Launch BigDelta and create a new project
2. Upload `Framing-P01.pdf` as the "Framing" document
3. Upload `Framing-P02.pdf` as a new revision of the same document
4. Open **Drawing compare** → select P01 vs P02 → page 1 vs 1
5. Expected overlay: magenta where P01 had content, cyan where P02 has content, dark where they coincide
6. Log a design change referencing the relocated opening
7. Mark resolution at P02
8. Compile package and compare output against `example-package.pdf`

## What "Correct" Looks Like

Use `example-package.pdf` as the visual QA baseline:
- Cover page with project name and issue date
- Linked table of contents (click entries → jump to section)
- Continuous page numbering in footer
- Section divider before each document
- Assumptions/code register on the final page
