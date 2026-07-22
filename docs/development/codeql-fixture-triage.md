# CodeQL Fixture Triage Notes

Date reviewed: July 22, 2026

## Fixture-only DOM findings

Alerts `#67`, `#68`, and `#69` are `js/xss-through-dom` findings reported from:

- `backend/tests/fixtures/sugarspunrun_best_cheesecake/page.html`
- `backend/tests/fixtures/thecountrycook_crock_pot_beef_stroganoff/page.html`

These files are inert regression fixtures:

- Pytest loads them with `Path(...).read_text()` in `backend/tests/test_good_fixture_pipeline.py` and `backend/tests/test_facebook_import_resolution.py`.
- The fixture builder writes them under `backend/tests/fixtures/` in `scripts/build_good_fixture_from_url.py`.
- The backend container copies only `backend/app`, so `backend/tests/fixtures/` is not present in the runtime image.
- The frontend container copies only `frontend/`, so backend fixtures are not bundled or served by nginx.
- Repository searches found no static-file route, test server, package script, or frontend bundling path that exposes `backend/tests/fixtures/page.html` as application content.

Treatment:

- Keep GitHub CodeQL default setup as the repository authority; do not add a repository-managed advanced CodeQL workflow just to exclude fixtures.
- Triage alerts `#67`, `#68`, and `#69` in GitHub as inert test or generated content with this note as the supporting justification.
- Do not edit captured third-party HTML just to silence CodeQL.
- Keep production and source findings in scope, including `frontend/app.js` alert `#66`.
