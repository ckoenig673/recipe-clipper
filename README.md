# Recipe Clipper

Recipe Clipper is a self-hosted recipe capture app for collecting recipes from links, pasted text, images, and social videos into one library. It keeps the V1 stack simple: a frontend SPA, a backend API, isolated workers for OCR and media processing, SQLite storage, and optional Ollama support for AI cleanup.

## Release Baseline

Version `1.0.0` is the initial public release baseline for the repository. This documentation reflects the public Docker Compose deployment and the stabilized V1 service layout.

## What It Does

- Import recipes from normal recipe URLs.
- Paste recipe text directly when a site is not parser-friendly.
- Extract recipe text from photos, screenshots, and scanned cookbook pages with OCR.
- Pull social-video content through a download plus transcript pipeline.
- Optionally run AI Cleanup and AI review enhancement through Ollama.
- Organize saved recipes into cookbooks.
- Build grocery lists from recipes.
- Support meal-planning workflows.
- Support Android sharing through the included Android companion project.

## Runtime Services

Docker Compose starts these runtime containers:

- `recipe-clipper-frontend`
- `recipe-clipper-backend`
- `recipe-clipper-ocr`
- `recipe-clipper-social`
- `recipe-clipper-whisper`

Compose service names are used for container-to-container communication:

- `frontend`
- `backend`
- `ocr`
- `social`
- `whisper`

The backend talks to workers by Compose service name:

- OCR: `http://ocr:8787/ocr/image`
- Social video download: `http://social:8790/download/social-video` via `SOCIAL_DOWNLOADER_URL` (legacy-compatible variable name)
- Whisper transcription: `http://whisper:8791/transcribe` via `WHISPER_PROCESSOR_URL` (legacy-compatible variable name)

SQLite data is stored under `./data` and mounted into the backend container at `/app/data`.

## Prerequisites

- Docker Engine with Docker Compose support
- Enough local disk space for the SQLite database and downloaded media artifacts
- A free set of local ports for the app:
  - `8010` frontend
  - `8015` backend
  - `8787` OCR worker
  - `8790` social worker
  - `8791` Whisper worker

Ollama is optional. Recipe capture must still work when Ollama is not configured.

## Quick Start

1. From the repository root, copy the example environment file:

   ```bash
   cp .env.example .env
   ```

   PowerShell:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Edit the root `.env` file and set the required values:
   - `AUTH_BOOTSTRAP_ADMIN_EMAIL`
   - `AUTH_BOOTSTRAP_ADMIN_PASSWORD`

3. Review the default ports in `.env` and update them only if they conflict with your machine.
   - If you change `FRONTEND_PORT`, also update `CORS_ALLOW_ORIGINS` to match the new frontend origin.
   - `SOCIAL_DOWNLOADER_PORT` and `WHISPER_PROCESSOR_PORT` are legacy-compatible variable names for the current `social` and `whisper` services.
   - Leave the worker URL variables on their Compose defaults unless you are intentionally changing service routing.

4. Optional: configure Ollama for AI Cleanup and AI review enhancement:
   - `OLLAMA_BASE_URL`
   - `OLLAMA_MODEL`
   - Leave `OLLAMA_BASE_URL` blank to keep Ollama disabled.

5. From the repository root, start the stack with the tracked `docker-compose.yml`:

   ```bash
   docker compose up -d --build
   ```

6. Open the frontend in your browser:
   - `http://localhost:8010` by default
   - or the host port you configured with `FRONTEND_PORT`

7. Sign in with the bootstrap admin account from `.env`.

8. In the app, verify service reachability from the import status area in Settings before testing OCR or social-video imports.

## Configuration Notes

- `.env.example` is the tracked template. Keep real secrets in `.env`, not in version control.
- `RECIPES_DB_PATH` defaults to `/app/data/recipes.db` inside the backend container and persists to `./data/recipes.db` on the host through Compose volume mounts.
- `AI_REVIEW_ENABLED=true` keeps the review flow available even if Ollama is not configured.
- When `OLLAMA_BASE_URL` is empty or Ollama is unreachable, imports still work and AI review actions fail gracefully instead of blocking recipe capture.
- The worker variables `SOCIAL_DOWNLOADER_URL`, `WHISPER_PROCESSOR_URL`, `SOCIAL_DOWNLOADER_PORT`, and `WHISPER_PROCESSOR_PORT` are retained for backward compatibility with existing runtime configuration and tests. They still target the current `social-worker/` and `whisper-worker/` services.
- The standard import path uses dedicated worker services:
  - `ocr` for image OCR
  - `social` for media download
  - `whisper` for transcription
- Downloaded social media artifacts are stored in `./data/social-downloads` and shared between the backend, social worker, and whisper worker.
- `.env.example` also includes backend-only fallback transcript settings so the documented environment surface matches the runtime code, even though the normal Compose path uses the dedicated workers above.
- Frontend cache-busting is controlled by `CACHE_BUST_VERSION` during frontend image builds.

## Repository Layout

- `frontend/` SPA served by nginx
- `backend/` primary API, auth, recipe CRUD, orchestration, and SQLite access
- `ocr-worker/` OCR-only worker
- `social-worker/` media download worker
- `whisper-worker/` transcription worker
- `android-share-companion/` Android share target project
- `docs/architecture/` system documentation
- `docs/development/` contributor and workflow documentation

## Validation

Useful local validation commands:

```bash
docker compose config
pytest backend/tests/
npm run test:e2e
```

`npm run test:e2e:headed` is also available for interactive Playwright debugging.

## Additional Documentation

- [Architecture overview](docs/architecture/README.md)
- [Good fixture guidelines](docs/development/good-fixture-guidelines.md)
- [Manual smoke checklist](docs/development/manual-smoke-checklist.md)
- [Contributing guide](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
