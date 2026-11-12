# Recipe Clipper Frontend

The frontend is a vanilla JavaScript single-page application served by nginx.

## Responsibilities

- Authentication
- Cookbook and recipe browsing
- Recipe detail and editing
- URL, image, pasted-text, and shared-recipe imports
- AI Cleanup review
- Bulk recipe actions
- Meal planning and grocery lists
- Admin and import settings
- Import-service status

## Android share flow

The Android companion opens the existing SPA route directly:

```text
/?share_import=1&url=...&title=...&text=...
```

The SPA captures the shared payload from the query string, stores it in `localStorage` early so auth redirects do not lose it, and then opens the Add Recipe workflow after login.

Supported entry routes:

```text
/?share_import=1
/?share_target=1
```

When a shared recipe contains a URL, the app opens URL import mode and pre-fills the import URL. When the share only contains recipe text, the app opens pasted-text mode and pre-fills the pasted recipe field.

## Frontend validation

```bash
node --test frontend/tests/url-hostname-helpers.test.mjs
npm run test:e2e
npm run test:e2e:headed
```
