# thecookierookie_cucumber_sandwiches fixture status

Source URL:
`https://www.thecookierookie.com/cucumber-sandwiches-recipe/`

Intended classification: **GOOD fixture** for parser regression coverage.

## Fixture capture note

This fixture is currently a **network-restricted stub capture**, not a direct full live-page HTML download.

In this execution environment, direct HTTPS fetches to `www.thecookierookie.com` failed through the configured proxy tunnel with `403 Forbidden`, so a representative HTML capture was created from the recipe card content and structured JSON-LD from the canonical page.

## Parser source selection

The parser selected `jsonld` (`_selected_source: "jsonld"`).

## Normalization behavior

- Parser output preserves grouped fields as single unnamed groups for both ingredients and instructions.
- Final output keeps the same flattened `ingredients`/`instructions` arrays and carries through servings + time fields.
- No AI cleanup path is used (`needs_review: false` in `final_expected.json`).

## Regeneration command (when live network access is available)

```bash
python scripts/build_good_fixture_from_url.py \
  --url "https://www.thecookierookie.com/cucumber-sandwiches-recipe/" \
  --fixture-name "thecookierookie_cucumber_sandwiches"
```
