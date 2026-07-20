
Recipe Clipper Backend

Social resolver runtime:
- Facebook fallback resolution now uses Playwright first and Selenium second.
- Selenium requires a real Chrome/Chromium driver runtime (this repo's backend Dockerfile installs `chromium` + `chromium-driver`).

Auth update (pre-beta, invite-only):
- Adds `users` and `sessions` tables with automatic startup migration.
- Adds nullable `display_name` on `users`.
- Cookie session auth for app routes (`/recipes`, `/extract-metadata`).
- New auth routes: `/auth/login`, `/auth/logout`, `/auth/me`.
- New admin-only routes:
  - `GET /admin/users`
  - `POST /admin/users`
  - `PUT /admin/users/{id}`
  - `POST /admin/users/{id}/reset-password`
  - `POST /admin/users/{id}/deactivate`
  - `POST /admin/users/{id}/activate`
  - `DELETE /admin/users/{id}`

Pre-beta access rules:
- No public signup or self-enrollment flow.
- Only admins create users (via admin UI or admin API).
- Bootstrap admin env vars are one-time setup only.

Important env vars:
- Core setup:
  - `RECIPES_DB_PATH`
- `AUTH_BOOTSTRAP_ADMIN_EMAIL`
- `AUTH_BOOTSTRAP_ADMIN_PASSWORD`
- `AUTH_COOKIE_SECURE`
- `AUTH_COOKIE_DOMAIN`
- `AUTH_COOKIE_NAME`
- `AUTH_SESSION_TTL_HOURS`
- `CORS_ALLOW_ORIGINS`
- Worker routing:
  - `OCR_WORKER_URL`
  - `OCR_WORKER_TIMEOUT_SECONDS`
  - `SOCIAL_DOWNLOADER_URL` (legacy-compatible name for the social worker endpoint)
  - `WHISPER_PROCESSOR_URL` (legacy-compatible name for the whisper worker endpoint)
- `OLLAMA_BASE_URL` (default blank; optional)
- `OLLAMA_MODEL` (default `llama3:latest`)
- `OLLAMA_TIMEOUT_SECONDS` (default `600`)
- `AI_REVIEW_ENABLED` (default `true`)
- `AI_REVIEW_POLL_SECONDS` (default `12`)
- Social transcript import fallback:
  - `SOCIAL_VIDEO_TMP_DIR` (default `/app/data/social-downloads` in Compose; `/tmp/recipe-clipper-social` if unset elsewhere)
  - `SOCIAL_VIDEO_FFMPEG_BIN` (default `ffmpeg`)
  - `SOCIAL_VIDEO_WHISPER_MODEL` (default `small`)
  - `SOCIAL_VIDEO_WHISPER_DEVICE` (default `cpu`)
  - `SOCIAL_VIDEO_WHISPER_COMPUTE_TYPE` (default `int8`)
  - `SOCIAL_VIDEO_MAX_TRANSCRIPT_CHARS` (default `12000`)
  - `SOCIAL_VIDEO_TRANSCRIPT_DEBUG_DIR` (optional, stores latest transcript text for debugging)
- Worker-specific settings:
  - `SOCIAL_DOWNLOADER_OUTPUT_DIR` for `social-worker`
  - `WHISPER_MODEL`, `WHISPER_DEVICE`, and `WHISPER_COMPUTE_TYPE` for `whisper-worker`
- Compose also retains `SOCIAL_DOWNLOADER_PORT` and `WHISPER_PROCESSOR_PORT` as legacy-compatible published port variable names for those current worker services.
- For Docker deployments, set these in compose/env and point `OLLAMA_BASE_URL` to a reachable Ollama HTTP endpoint (for example `http://ollama:11434` when Ollama runs as a compose service on the same network).

Transcript pipeline runtime dependencies:
- Standard Compose path:
  - `yt-dlp` runs in `social-worker`
  - `faster-whisper` runs in `whisper-worker`
- Backend fallback path:
  - `ffmpeg` binary installed and available in PATH (or configure `SOCIAL_VIDEO_FFMPEG_BIN`)
  - `faster-whisper` Python package for local backend transcription

Image OCR import dependencies (MVP):
- Python packages: `pillow`, `pytesseract`.
- System dependency: `tesseract-ocr` binary available on PATH.
- If Tesseract is unavailable, `/import/image` returns a clear OCR unavailable error response.
- Backend Docker image now installs `tesseract-ocr` during build, so OCR works after rebuild/deploy without extra manual package installs.
- Quick verification after deploy: `docker exec -it recipe-clipper-backend tesseract --version`

Bootstrap admin note:
- Bootstrap admin creation runs only when the configured bootstrap user does not already exist.
- Remove `AUTH_BOOTSTRAP_ADMIN_*` env vars after first successful login.

AI review queue (v1, backend-only):
- New recipe review statuses: `none`, `needs_review`, `queued`, `processing`, `review_ready`, `failed`.
- New queue endpoints:
  - `POST /recipes/{id}/queue-review`
  - `GET /recipes/{id}/review-status`
  - `GET /recipes/{id}/review-result`
  - `POST /recipes/{id}/retry-review`
- A lightweight in-process background worker scans for queued reviews and calls Ollama asynchronously.
