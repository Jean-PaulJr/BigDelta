# bigdelta/static/ — Browser Frontend

Vanilla JS/HTML/CSS — no frameworks, no CDN dependencies, no build step. Served directly by `server.py`.

## Files

| File | Purpose |
|------|---------|
| `index.html` | 6-line shell: loads app.js, style.css, logo.svg; four layout divs |
| `app.js` | All client logic — state, rendering, API calls, event handling |
| `style.css` | Grid layout, brand colors, form/button styles |
| `logo.svg` | Teal triangle + amber stroke mark; embedded as `<img>` |

## app.js Conventions

**State:** Three globals — `projects` (array), `checks` (object), `token` (string refreshed on load).

**Rendering:** `render()` recomputes the full UI from state. Call it after any state mutation. No virtual DOM — full innerHTML replacement per region.

**API calls:** All go through `api(path, payload)`:
- Attaches `X-Token` header for CSRF
- POSTs JSON; GETs have no body
- File uploads encoded as base64 strings inside the JSON payload
- Errors parsed from JSON response body and surfaced as toast notifications

**Event handling:** Single delegated listener on `document`. Buttons carry `data-action` and `data-id` attributes. No inline `onclick`.

**Tabs:** "Package builder", "Project journal", "Design changes", "Drawing compare", "Calculation review". Tab content rendered by `render()` based on active tab name.

**Dialogs:** Modal `#dialog` div, reused for all forms. Content replaced per action (new project, upload revision, record event, log change, etc.).

**Review polling:** `reviewTimer` interval polls `/api/projects/{pid}/review_status` until job completes or errors. Clear the timer on navigation away.

**Persistence:** Active project ID stored in `localStorage` under `bigdelta-project`. Restored on page load.

## Brand Colors

- Navy: `#142c40` (sidebar, headers)
- Teal: `#087f83` (primary actions, logo triangle)
- Amber: `#e99b49` (logo accent, warnings)

## What Not to Add

- No external scripts or CDN links — offline-capable is a requirement
- No build tooling (webpack, vite, etc.) — the files are served as-is
- No TypeScript — keep it plain JS matching the existing style
