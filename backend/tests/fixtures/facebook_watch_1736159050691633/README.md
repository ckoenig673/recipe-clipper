# Facebook import-resolution fixture: `facebook_watch_1736159050691633`

This is a deterministic GOOD social import-resolution fixture for:

- Input URL: `https://www.facebook.com/watch/?ref=saved&v=1736159050691633`
- Resolved recipe URL: `https://simplehomeedit.com/recipe/homemade-chicken-stew/`

## What this fixture validates

1. A Facebook watch URL is resolved to an external recipe URL by social resolver logic.
2. The resolved recipe page is parsed through the normal parser pipeline.
3. The final payload is generated from the resolved recipe URL with `needs_review=false`.

## Files

- `input_url.txt`: Facebook watch URL used as input.
- `resolver_expected.json`: Expected social resolution result.
- `resolved_recipe_url.txt`: Resolved recipe URL used by parser/import path.
- `page.html`: Saved HTML snapshot of the resolved recipe URL (not Facebook HTML).
- `parser_expected.json`: Full parser output expected from `page.html`.
- `final_expected.json`: Final payload expected after social resolution + parsing.

## Notes

- This fixture is network-independent during pytest: both social resolution and page fetch are mocked.
- `page.html` is the resolved recipe page HTML snapshot and intentionally does not contain Facebook HTML.
