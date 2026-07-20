# Good Fixture Guidelines

## Purpose

This document defines the standard process for creating fixture-based tests for recipe import cases that should parse cleanly using the existing parser and normalization pipeline without AI cleanup.

These fixtures act as regression coverage to ensure common recipe sites continue to work through the normal non-AI path.

## Good Case Definition

A good fixture case should have these characteristics:

- The source page is primarily recipe-focused.
- Structured data and/or normal DOM extraction works.
- Ingredients and instructions extract cleanly.
- Ingredient or instruction grouping is preserved when present.
- Junk content is excluded.
- No AI cleanup is required.
- Final output comes from the parser plus the standard non-AI pipeline.

## Expected Inputs

Contributors may start from:

- A recipe URL
- A screenshot of a successful Recipe Clipper import
- An optional fixture name

If no fixture name is provided, derive a clean name from the domain and recipe title, for example `sugarspunrun_best_cheesecake`.

## Required Outputs

Each fixture should produce:

```text
backend/tests/fixtures/<fixture_name>/
  page.html
  parser_expected.json
  final_expected.json
```

Also add or update pytest coverage for the fixture.

## Required Process

1. Fetch the recipe URL and save the raw HTML to `backend/tests/fixtures/<fixture_name>/page.html`.
2. Run the real parser or extraction pipeline against the saved HTML.
3. Use the real parser output as the source of truth for `parser_expected.json`.
4. Run the normal non-AI pipeline to produce the final recipe output.
5. Use that output as the basis for `final_expected.json`.
6. Treat screenshots only as supporting references for UI-facing structure and formatting, not as parser truth.

## Network-Restricted Fallback

Prefer real live-page HTML whenever possible.

If the environment cannot fetch the live recipe URL:

- A stub fixture may be created temporarily.
- The stub must be clearly labeled as a stub in `page.html`.
- Add a `README.md` in the fixture folder explaining why a stub was used.
- Do not present a stub fixture as a real live-page regression capture.

Regenerate the fixture from the live URL once network access is available.

## Code Modification Restrictions

Fixture work should not change production behavior.

Do not:

- Change parser logic
- Modify extraction behavior
- Alter normalization behavior
- Change AI routing behavior
- Add site-specific parsing hacks
- Refactor production services to make tests pass
- Modify files under `backend/app/` for fixture-only work
- Add new production helper functions just for fixture creation

If parser behavior appears incorrect, capture the real output, allow the test to expose the mismatch if needed, and report the issue separately.

## Allowed Changes

Allowed changes include:

- Creating fixture files
- Creating or updating test files
- Adding non-invasive test helpers or utilities
- Creating standalone fixture-building scripts

## Test Integrity Rules

- Do not fabricate parser output.
- Do not adjust expected results to match assumptions.
- Prefer real parser output over guessed data.
- Use tests to expose issues rather than hide them.

## Good Case Test Requirements

Each good fixture should validate:

1. The parser loads the saved HTML fixture correctly.
2. The expected extraction source is selected.
3. The title is extracted correctly.
4. Ingredients are extracted correctly.
5. Instructions are extracted correctly.
6. Grouping is preserved when applicable.
7. Junk content is excluded.
8. The recipe stays on the standard non-AI path.
9. Final pipeline output matches `final_expected.json`.
10. AI or Ollama is not called.

## Reusable Automation

Prefer using `scripts/build_good_fixture_from_url.py`:

```bash
python scripts/build_good_fixture_from_url.py \
  --url "<recipe_url>" \
  --fixture-name "<fixture_name>"
```

The script should fetch HTML, save `page.html`, run the parser, write `parser_expected.json`, run the non-AI pipeline, and write `final_expected.json`.

## Expected Outcome

A completed good fixture should:

- Require little or no manual data entry
- Be fully reproducible
- Reflect real parser behavior
- Provide deterministic regression coverage
- Avoid dependence on live sites or AI services after capture
