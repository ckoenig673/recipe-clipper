# Deployment Guide

This guide covers self-hosted Docker Compose installation, upgrades, backup and restore, and routine rebuild or restart procedures for Recipe Clipper.

## Runtime Summary

Recipe Clipper ships as a multi-container Docker Compose stack:

- `frontend` - nginx-hosted SPA on host port `8010` by default
- `backend` - FastAPI API and SQLite access on host port `8015`
- `ocr` - Tesseract OCR worker on host port `8787`
- `social` - yt-dlp download worker on host port `8790`
- `whisper` - faster-whisper transcription worker on host port `8791`

Persistent application data lives on the host under:

- `./data/recipes.db`
- `./data/social-downloads/`

## Install

1. Clone the repository onto the target host.
2. Copy the tracked environment template:

   ```powershell
   Copy-Item .env.example .env
   ```

   POSIX shell:

   ```bash
   cp .env.example .env
   ```

3. Edit `.env` and set the required bootstrap administrator credentials:

   ```dotenv
   AUTH_BOOTSTRAP_ADMIN_EMAIL=admin@example.local
   AUTH_BOOTSTRAP_ADMIN_PASSWORD=replace-this-password
   ```

4. Review any host-specific overrides you need:

   - `FRONTEND_PORT`
   - `BACKEND_PORT`
   - `OCR_WORKER_PORT`
   - `SOCIAL_DOWNLOADER_PORT`
   - `WHISPER_PROCESSOR_PORT`
   - `AUTH_COOKIE_SECURE`
   - `AUTH_COOKIE_DOMAIN`
   - `CORS_ALLOW_ORIGINS`
   - `OLLAMA_BASE_URL` and `OLLAMA_MODEL` if AI Cleanup should be enabled

5. Validate the Compose file:

   ```bash
   docker compose config
   ```

6. Build and start the stack:

   ```bash
   docker compose up -d --build
   ```

7. Open `http://localhost:8010` or the configured `FRONTEND_PORT` on your host and sign in.
8. After the first successful administrator login, remove `AUTH_BOOTSTRAP_ADMIN_EMAIL` and `AUTH_BOOTSTRAP_ADMIN_PASSWORD` from `.env`, then redeploy so those one-time bootstrap credentials are no longer present in the running environment.

## Upgrade

Use this flow for application updates that change code, images, or startup behavior.

1. Back up the deployment before changing anything.
2. Pull or copy the updated repository contents onto the host.
3. Review `.env.example` in the new release and merge any newly introduced variables into your local `.env`.
4. Validate the updated Compose file:

   ```bash
   docker compose config
   ```

5. Rebuild and restart the stack:

   ```bash
   docker compose up -d --build
   ```

6. Confirm the containers are healthy:

   ```bash
   docker compose ps
   ```

7. Open the app and verify login plus at least one import path.

Notes:

- The backend performs automatic startup migrations for the current SQLite auth schema.
- The `data/` directory is mounted from the host, so rebuilds do not remove the existing database or shared media.
- If the frontend serves stale assets after an upgrade, rebuild again with an updated `CACHE_BUST_VERSION` in `.env`.

## Database Backup

Back up the entire `data/` directory if you want both the SQLite database and shared import media.

PowerShell:

```powershell
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
New-Item -ItemType Directory -Force -Path .\backups | Out-Null
Copy-Item .\data ".\backups\data-$timestamp" -Recurse
```

POSIX shell:

```bash
timestamp="$(date +%Y%m%d-%H%M%S)"
mkdir -p backups
cp -R data "backups/data-$timestamp"
```

If you only need the primary database file, back up `./data/recipes.db`.

For the most conservative backup, stop the stack first:

```bash
docker compose down
```

Then perform the copy and start the stack again:

```bash
docker compose up -d
```

## Database Restore

Restore only from a backup captured from a compatible Recipe Clipper deployment.

1. Stop the stack:

   ```bash
   docker compose down
   ```

2. Replace the current persisted data with the backup copy.

   PowerShell:

   ```powershell
   Copy-Item .\backups\data-YYYYMMDD-HHMMSS\* .\data\ -Recurse -Force
   ```

   POSIX shell:

   ```bash
   cp -R backups/data-YYYYMMDD-HHMMSS/* data/
   ```

3. Start the stack again:

   ```bash
   docker compose up -d
   ```

4. Confirm the app opens and expected recipes are present.

If you are restoring only `recipes.db`, replace `./data/recipes.db` while the stack is stopped, then start the stack again.

## Rebuild and Restart Procedures

Use these commands for routine local deployment maintenance.

Rebuild images and restart containers:

```bash
docker compose up -d --build
```

Restart without rebuilding:

```bash
docker compose up -d
```

Inspect running containers:

```bash
docker compose ps
```

Inspect recent logs:

```bash
docker compose logs --tail=200
```

Stop the stack:

```bash
docker compose down
```

## Post-Deploy Checks

- Confirm `docker compose ps` shows all five services running.
- Open `http://localhost:8010`.
- Verify login works.
- Open **Settings** and confirm import services report healthy status.
- Test one basic recipe import path before declaring the upgrade complete.
