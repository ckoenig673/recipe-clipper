# CodeQL Polynomial ReDoS Inventory

Reviewed on 2026-07-21 against the open GitHub Code Scanning `py/polynomial-redos` alerts for `ckoenig673/recipe-clipper`.

The workspace did not contain the exported findings artifact referenced by story #1050, so this inventory was built from the live open alert set in GitHub. At review time there were 41 open polynomial ReDoS alerts, numbered `#21` through `#61`, and all of them resolved to `backend/app/main.py`.

## Grouped Findings

| Group | Alert numbers | Helper / root cause | Regex or pattern family | Input classification | Classification |
| --- | --- | --- | --- | --- | --- |
| G1 | 21, 22, 23 | `_split_instruction_sentences` sentence splitting on freeform recipe text | `;\s+`, `(?<=\.)\s+`, `^\d+[\.)]\s*` and adjacent cleanup passes | User input, OCR text, downloaded social caption text | Rewrite required |
| G2 | 24, 25 | `_extract_ingredient_candidates_from_text` quantity prefix detection | `^\s*(?:[-•*]\s*)?(?:\d+(?:[\.,]\d+)?(?:/\d+)?\s*)?(?:x\s*)?(?:g|grams?|kg|ml|l|tbsp|tsp|cups?|oz|lb|cloves?|pinch|handful)\b` and inline quantity checks | OCR text, downloaded social caption text | Rewrite required |
| G3 | 26 | `parse_social_caption_recipe` title/header rejection on the first line | `\b(?:ingredients?|method|instructions?)\b` | OCR text, downloaded social caption text | Input bound required |
| G4 | 27, 28, 29, 30 | Pasted recipe metadata line parsing in the `/parse-pasted-text` flow | `^servings?...`, `^prep(?:aration)?\s*time...`, `^cook(?:ing)?\s*time...`, `^total\s*time...` | User input | Input bound required |
| G5 | 31, 32 | `extract_json_ld_blocks` regex-based HTML script extraction | `<script...application/ld+json...>(.*?)</script>`, HTML comment and CDATA stripping | Downloaded HTML, test fixture HTML | Rewrite required |
| G6 | 33, 34 | `_parse_iso8601_minutes` duration parsing | `^P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$` | Downloaded HTML metadata | Input bound required |
| G7 | 35, 36, 55, 56 | Shared ingredient parenthetical-note extraction in `_parse_ingredient_struct` and `_normalize_ai_cleanup_prompt_ingredient_line` | `\(([^)]*)\)`, `\([^)]*\)`, `^([a-zA-Z]+)\b`, `^of\s+` | User input, OCR text, transcription text, AI-cleanup payloads | Rewrite required |
| G8 | 37, 38, 39, 40, 41, 42, 43 | Regex-based DOM recipe extraction in `_extract_bigoven_instruction_groups`, `_extract_recipe_scoped_html`, and `_extract_dom_recipe_data` | `<p...>(.*?)</p>`, scope extraction with `.*?`, grouped `<h...>...<(ul|ol)...>` scans, `<li...>(.*?)</li>` scans | Downloaded HTML, test fixture HTML | Rewrite required |
| G9 | 44 | `_parse_html_attributes` called from image extraction helpers | `([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*(['"])(.*?)\2` | Downloaded HTML, test fixture HTML | Rewrite required |
| G10 | 45, 46, 47, 48, 49, 50, 51, 52, 53 | `_extract_meta_image` repeated whole-document `<meta>` scans | `<meta[^>]+property=...[^>]+>`, `<meta[^>]+name=...[^>]+>`, `<meta[^>]+itemprop=...[^>]+>` | Downloaded HTML, test fixture HTML | Rewrite required |
| G11 | 54 | `_extract_dom_fallback_image` whole-document container extraction before `<img>` scanning | `<(?:article|main|section|div)...>.*?</...>` | Downloaded HTML, test fixture HTML | Rewrite required |
| G12 | 57 | `_normalize_component_ingredient_parts` via `_looks_like_ingredient_quantity` and `_parse_spoken_quantity_phrase` | Numeric quantity fullmatch plus spoken-number normalization regexes | Transcription text, OCR text, AI-cleanup payloads | Input bound required |
| G13 | 58 | `_normalize_plain_string_list` AI ingredient cleanup formatting | `\s+\.`, `([A-Za-z]{4,})\.(?=\s+\w)` | AI-cleanup payloads, user-edited ingredient lines | Input bound required |
| G14 | 59, 60, 61 | `_is_non_ingredient_header_line` and `_sanitize_ai_ingredient_group_title` header heuristics | `^(?:serves?|servings?|serving\s+size|yield|makes?)\b`, `^(?:for the|to serve|for serving|optional...)`, `\s*(?:;| \- |\|)\s*`, `\b(?:source|nutrition|notes?|ingredients?)\b`, `_AI_INGREDIENT_AMOUNT_PATTERN` | AI-cleanup payloads, user-edited ingredient groups | Input bound required |

## Detailed Notes By Group

### G1: Instruction sentence splitting on freeform text

- File: `backend/app/main.py`
- Main helper: `_split_instruction_sentences`
- Affected call paths:
  - `parse_social_caption_recipe(...)` for downloaded social captions and OCR fallback
  - pasted-text parsing flow when instructions are synthesized from a raw pasted blob
- Root cause:
  - multiple regex passes run over unconstrained freeform text, including whitespace-heavy splitting and numbered-step normalization
- Distinct alerts:
  - `#21`, `#22`, `#23`

### G2: Ingredient quantity detection in social/OCR parsing

- File: `backend/app/main.py`
- Main helper: `_extract_ingredient_candidates_from_text`
- Affected call path:
  - `parse_social_caption_recipe(...)`
- Root cause:
  - anchored measurement regex still runs on attacker-controlled or scraper-controlled lines without an explicit line-length cap
- Distinct alerts:
  - `#24`, `#25`

### G3: Title/header rejection for social/OCR text

- File: `backend/app/main.py`
- Main helper: `parse_social_caption_recipe`
- Affected call path:
  - social caption and OCR parsing
- Root cause:
  - low-complexity header regex is applied to unbounded first-line text
- Distinct alerts:
  - `#26`

### G4: Pasted recipe metadata extraction

- File: `backend/app/main.py`
- Main helper: pasted recipe parser loop around the `servings`, `prep`, `cook`, and `total` matches
- Affected call path:
  - user-pasted recipe text
- Root cause:
  - four nearly identical anchored regexes run on arbitrary pasted lines
- Distinct alerts:
  - `#27`, `#28`, `#29`, `#30`

### G5: JSON-LD extraction from downloaded HTML

- File: `backend/app/main.py`
- Main helper: `extract_json_ld_blocks`
- Affected call path:
  - HTML recipe scraping before JSON-LD parsing
- Root cause:
  - the code uses whole-document regexes to find `<script type="application/ld+json">` blocks and strip wrapper markup
- Distinct alerts:
  - `#31`, `#32`

### G6: ISO-8601 duration parsing

- File: `backend/app/main.py`
- Main helper: `_parse_iso8601_minutes`
- Affected call paths:
  - duration normalization for scraped recipe metadata
- Root cause:
  - optional-group-heavy duration regex runs on downloaded metadata fields without an explicit size guard
- Distinct alerts:
  - `#33`, `#34`

### G7: Parenthetical note extraction in ingredient normalization

- File: `backend/app/main.py`
- Main helpers:
  - `_parse_ingredient_struct`
  - `_normalize_ai_cleanup_prompt_ingredient_line`
- Affected call paths:
  - ingredient import normalization
  - AI cleanup payload preparation
- Root cause:
  - the same parenthetical extraction/removal regex pair is duplicated in two helpers and applied to user-derived ingredient strings
- Distinct alerts:
  - `#35`, `#36`, `#55`, `#56`

### G8: Regex-based DOM recipe extraction

- File: `backend/app/main.py`
- Main helpers:
  - `_extract_bigoven_instruction_groups`
  - `_extract_recipe_scoped_html`
  - `_extract_dom_recipe_data`
- Affected call path:
  - scraped recipe-page HTML fallback parser
- Root cause:
  - repeated nested `.*?` and repeated-tag HTML scans across whole pages for ingredient and instruction discovery
- Distinct alerts:
  - `#37`, `#38`, `#39`, `#40`, `#41`, `#42`, `#43`

### G9: HTML attribute parsing helper

- File: `backend/app/main.py`
- Main helper: `_parse_html_attributes`
- Affected call paths:
  - meta image extraction
  - DOM fallback image extraction
- Root cause:
  - generic regex attribute parser is fed raw HTML tag strings from downloaded pages
- Distinct alerts:
  - `#44`

### G10: Meta image extraction scans

- File: `backend/app/main.py`
- Main helper: `_extract_meta_image`
- Affected call path:
  - scraped recipe image selection
- Root cause:
  - repeated whole-document `<meta>` regex scans for OG and Twitter image tags
- Distinct alerts:
  - `#45`, `#46`, `#47`, `#48`, `#49`, `#50`, `#51`, `#52`, `#53`

### G11: DOM fallback image container extraction

- File: `backend/app/main.py`
- Main helper: `_extract_dom_fallback_image`
- Affected call path:
  - fallback image extraction from downloaded HTML
- Root cause:
  - recipe container extraction uses a whole-document regex with broad alternation and `.*?` before image-tag scanning
- Distinct alerts:
  - `#54`

### G12: Spoken quantity parsing for component ingredients

- File: `backend/app/main.py`
- Main helpers:
  - `_normalize_component_ingredient_parts`
  - `_looks_like_ingredient_quantity`
  - `_parse_spoken_quantity_phrase`
- Affected call paths:
  - AI cleanup payload normalization
  - ingredient normalization from OCR/transcription-like payload fragments
- Root cause:
  - quantity classification is regex-driven and runs on arbitrary fragments before the code narrows them into amount/unit/name parts
- Distinct alerts:
  - `#57`

### G13: AI ingredient line punctuation cleanup

- File: `backend/app/main.py`
- Main helper: `_normalize_plain_string_list`
- Affected call paths:
  - AI cleanup payload normalization
  - preview payload sanitization
- Root cause:
  - punctuation and whitespace cleanup regexes run on arbitrary AI-produced ingredient strings
- Distinct alerts:
  - `#58`

### G14: AI ingredient-group heading heuristics

- File: `backend/app/main.py`
- Main helpers:
  - `_is_non_ingredient_header_line`
  - `_sanitize_ai_ingredient_group_title`
- Affected call paths:
  - preview payload sanitization
  - AI cleanup merge/sanitize flows
- Root cause:
  - several heading-detection regexes are run repeatedly on arbitrary group titles and entries
- Distinct alerts:
  - `#59`, `#60`, `#61`

## Alert Coverage Summary

| Input type | Covered groups |
| --- | --- |
| User input | G1, G4, G7, G13, G14 |
| Downloaded HTML | G5, G6, G8, G9, G10, G11 |
| OCR text | G1, G2, G3, G7, G12 |
| Transcription text | G7, G12 |
| Downloaded social caption text | G1, G2, G3 |
| Test fixture HTML only | None of the open `py/polynomial-redos` alerts are fixture-only; fixture pages only reproduce the same downloaded-HTML parser paths. |
| Bounded internal data | None of the open alerts are limited to bounded internal-only inputs. |

## Implementation Checklist For The Rewrite Story

1. Replace regex-based JSON-LD extraction in `extract_json_ld_blocks` with an HTML parser walk over `<script>` tags and explicit `type` checks.
2. Replace DOM fallback extraction in `_extract_recipe_scoped_html`, `_extract_dom_recipe_data`, `_extract_meta_image`, `_extract_dom_fallback_image`, and `_parse_html_attributes` with parser-based element traversal instead of whole-document regex scans.
3. Deduplicate the parenthetical ingredient-note logic used by `_parse_ingredient_struct` and `_normalize_ai_cleanup_prompt_ingredient_line`, then replace it with a linear scan or parser that does not rely on repeated parenthetical regex passes.
4. Rework `_split_instruction_sentences` so sentence splitting and numbered-step recovery use bounded tokenization or direct string scanning instead of repeated regex rewrites over full text blobs.
5. Rework `_extract_ingredient_candidates_from_text` to tokenize the leading quantity/unit segment instead of using the long optional-group measurement regex on arbitrary lines.
6. Add explicit maximum-length guards before regex-based handling of pasted metadata lines, social/OCR title checks, ISO-8601 duration parsing, spoken quantity parsing, AI ingredient cleanup, and AI ingredient-group heading heuristics.
7. Add regression tests for each root-cause group rather than one test per alert number:
   - freeform instruction text with long whitespace runs
   - social/OCR ingredient lines with pathological spaces and tabs
   - oversized pasted metadata lines
   - oversized HTML with repeated `<script>`, `<div>`, `<p>`, `<li>`, and `<meta>` fragments
   - long parenthetical ingredient notes
   - long AI ingredient-group titles and AI-produced ingredient fragments
8. After rewrites land, rerun CodeQL and confirm the grouped alerts clear as root-cause fixes:
   - HTML parser rewrite should clear G5 and G8 through G11
   - ingredient-note rewrite should clear G7
   - freeform text/token rewrite should clear G1, G2, and likely G12 through G14
   - explicit input caps should clear the remaining low-complexity regex groups if they are still reported
