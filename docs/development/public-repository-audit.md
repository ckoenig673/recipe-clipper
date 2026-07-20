# Public Repository Audit

Audit date: 2026-07-18

## Scope

This audit pass reviewed the repository for public-release blockers in the areas called out by story `#1043`:

- machine-specific paths
- local/private network references
- cookies, tokens, keys, and passwords committed to tracked files
- stale documentation paths
- temporary or debugging-only references worth removing or documenting

## Cleanup Applied

- Replaced stale `tools/...` documentation references with `scripts/...` to match the current repository layout.
- Replaced the standalone Facebook troubleshooting script example output path `C:\\temp\\...` with a portable relative path.
- Updated the review-package generation scripts to package `social-worker` and `whisper-worker`, derive the repository root relative to the script, exclude transient backup artifacts such as `*.bak` and `*.bak2`, and verify that every Docker Compose build context is present in the generated archive.

## Remaining Notes

- `docker compose config` succeeded on July 18, 2026, but the resolved output used the local untracked `.env` file and surfaced private LAN hostnames/IPs plus bootstrap credentials from that local environment. That is an environment-local release risk rather than a tracked-file leak, but it should be sanitized before any public-facing packaging or screenshots are produced.
- Tracked recipe HTML fixtures still contain third-party page source, including vendor JavaScript, cookie-banner markup, and public analytics tokens embedded by those sites. These appear to be fixture artifacts rather than application secrets, but they should continue to be reviewed case-by-case before any new fixture is committed.
- No `LICENSE` file exists in the repository yet, so prior review-package archives could not include one. The packaging scripts include `LICENSE` automatically if it is added later.
- The current worktree already contains broader in-progress repository-cleanup changes outside this audit pass, including deleted legacy worker paths and moved documentation. Those changes were not reverted or expanded here.

## Release Readiness

The tracked repository content reviewed in this audit is aligned for the `1.0.0` initial public release baseline. The repository includes the required public documentation currently present in the repository (`CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`) and all Docker Compose build contexts (`backend`, `frontend`, `ocr-worker`, `social-worker`, `whisper-worker`). Remaining cautions are environment-local or ongoing maintenance notes rather than tracked-file blockers.

## Validation

- `docker compose config`: passed
- `docker compose build`: passed
- `python -m pytest backend/tests/`: failed with 1 existing regression in `backend/tests/test_good_fixture_pipeline.py`
- `npm run test:e2e`: passed, 19 tests passed
- Backend regression observed on July 18, 2026:
  - `backend/tests/test_good_fixture_pipeline.py::test_good_fixture_pipeline_regression_cases`
  - Fixture mismatch in `plantbasedfolk_cherry_tomato_spaghetti_sauce`
  - Current parser output differs from expected fixture punctuation in the cherry tomato ingredient text (`quartered This recipe...` vs `quartered. This recipe...`)
