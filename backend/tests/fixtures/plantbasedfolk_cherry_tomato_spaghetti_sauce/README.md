# plantbasedfolk_cherry_tomato_spaghetti_sauce fixture status

Source URL:
`https://plantbasedfolk.com/cherry-tomato-spaghetti-sauce/`

Intended classification: **GOOD fixture** for parser regression coverage.

## Fixture capture note

This fixture is currently a **network-restricted stub capture**, not a direct full live-page HTML download.

In this execution environment, direct HTTPS fetches to `plantbasedfolk.com` failed through the configured proxy tunnel with `403 Forbidden`, so a representative HTML capture was created from the recipe card content and structured JSON-LD visible in page retrieval.

## Parser source selection

The parser selected `jsonld` (`_selected_source: "jsonld"`).

## Normalization behavior

- Parser output preserves grouped fields as single unnamed groups for both ingredients and instructions.
- Final output keeps the same flattened `ingredients`/`instructions` arrays and carries through time + servings fields.
- No AI cleanup path is used (`needs_review: false` in `final_expected.json`).

## Regeneration command (when live network access is available)

```bash
python scripts/build_good_fixture_from_url.py \
  --url "https://plantbasedfolk.com/cherry-tomato-spaghetti-sauce/" \
  --fixture-name "plantbasedfolk_cherry_tomato_spaghetti_sauce"
```
