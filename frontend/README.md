Recipe Clipper Frontend Share Import Flow

Android share companion should launch:
- `http://localhost:8010/share.html?url=...&title=...&text=...`

`share.html` behavior:
- Reads `url`, `title`, and `text` query params
- Stores a pending payload in `localStorage` (`recipe_clipper_pending_share`)
- Redirects to `/?share_import=1`

Quick local test:
1. Confirm frontend is reachable at `http://localhost:8010`.
2. Open a recipe URL and share into Recipe Clipper.
3. Verify app opens and automatically imports.
