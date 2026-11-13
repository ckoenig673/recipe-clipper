# Recipe Clipper — V2 Backlog

## Purpose

This document tracks future ideas, enhancements, and architectural directions for Recipe Clipper after the V1 stabilization/pre-beta phase.

V1 priorities were:
- stable imports
- practical editing
- cookbook organization
- mobile usability
- PWA support
- worker separation
- self-host portability

V2 should focus on:
- workflow refinement
- smarter organization
- practical cooking improvements
- quality-of-life features

This is intentionally a backlog, not a strict roadmap.

---

# Priority Legend

| Priority | Meaning |
|---|---|
| P0 | High impact / likely early V2 |
| P1 | Strong feature candidate |
| P2 | Nice enhancement |
| P3 | Experimental / future |

---

# P0 — Core Workflow Improvements

## Recipe Image Management

### Problem
Many imported/manual recipes lack images.

### Goals
- upload custom recipe image
- paste image URL
- choose frame from imported video
- improve cookbook visual browsing

### Future Ideas
- auto-thumbnail extraction from reels/videos
- AI image selection
- multiple images per recipe

### Notes
This is likely the single biggest visual UX improvement remaining after V1.

---

## Ingredient Normalization Layer

### Problem
Ingredients are currently stored mostly as freeform text.

### Goals
Parse ingredients into structured fields:
- quantity
- unit
- ingredient name
- optional notes/preparation

### Unlocks
- smarter grocery lists
- ingredient scaling
- duplicate merging
- pantry logic
- recipe analytics

### Notes
This is a foundational V2 feature.
Should be introduced carefully to avoid breaking existing imports.

---

## Grocery Intelligence

### Problem
Current grocery generation is functional but basic.

### Goals
- merge duplicate ingredients
- normalize units where possible
- checkbox persistence
- aisle/category grouping
- meal-plan aggregation

### Future Ideas
- pantry exclusions
- shopping mode
- grocery history
- recurring staples

### Notes
Very high real-world value.

---

## Meal Planning Expansion

### Problem
Meal planning foundation exists but is lightweight.

### Goals
- improved weekly planning UI
- drag/drop scheduling
- grocery auto-generation
- leftovers support
- meal categories/tags

### Future Ideas
- prep-day workflows
- batch cooking support
- recurring meal schedules

---

## Import Confidence / Quality Scoring

### Problem
Some imports are extremely clean while others need heavy editing.

### Goals
Provide import quality indicators such as:
- High confidence
- Medium confidence
- Needs review

### Potential Signals
- ingredient count
- instruction count
- parser confidence
- OCR quality
- AI cleanup results

### Notes
Should guide users without becoming intrusive.

---

# P1 — Recipe Workflow Enhancements

## Recipe Revision History

### Goals
Track recipe changes over time.

### Example
- v1 original import
- v2 added more garlic
- v3 reduced salt

### Notes
Useful for home cooks refining recipes repeatedly.

---

## Expanded Notes / Cooking Journal

### Goals
Support practical cooking notes:
- family feedback
- spice adjustments
- freezer notes
- timing tweaks
- substitutions

### Notes
Multiline notes added in V1 create a good foundation.

---

## Better Mobile Cooking Mode

### Goals
Improve in-kitchen usability.

### Ideas
- larger instruction text
- keep screen awake
- step-by-step focus mode
- timer shortcuts
- voice interaction later

### Notes
Should prioritize practical cooking flow over flashy UI.

---

## Better Recipe Search & Filtering

### Goals
- ingredient search
- tag filtering
- cookbook filters
- prep/cook time filters
- favorites filtering

### Future Ideas
- fuzzy search
- pantry-aware search
- semantic search later

---

# P1 — Import Improvements

## Better Social Import Recovery

### Goals
Improve handling for:
- Facebook reels
- Instagram reels
- TikTok recipes
- recipes hidden in comments/descriptions

### Notes
Current architecture is intentionally rules-first.
AI should remain fallback/enhancement only.

---

## AI-Assisted Structured Cleanup

### Goals
Allow AI cleanup to:
- improve ingredient grouping
- normalize instruction flow
- improve title quality
- clean OCR noise

### Important
AI should never silently overwrite user content.

---

## Bulk Import Queue

### Goals
Support importing multiple URLs/images in sequence.

### Notes
Keep architecture lightweight.
Avoid overengineering.

---

# P2 — Organization Features

## Tags System Expansion

### Goals
- custom tags
- dietary tags
- difficulty tags
- cuisine tags

### Notes
Should remain lightweight and user-driven.

---

## Favorites / Ratings Expansion

### Goals
Improve recipe prioritization.

### Ideas
- quick favorites
- star filtering
- frequently cooked sorting

---

## Cookbook Enhancements

### Goals
- cookbook covers
- reorder cookbooks
- cookbook descriptions
- cookbook statistics

---

# P2 — Admin / Config Enhancements

## Settings UI Expansion

### Goals
Move more env/config concepts into admin UI where appropriate.

### Candidates
- Ollama model selection
- AI review settings
- import worker visibility
- cache/version info

### Important
Sensitive secrets should remain env-only.

---

## Worker Status Dashboard

### Goals
Improve import services visibility.

### Ideas
- uptime
- last successful job
- queue depth
- OCR/AI timing

---

# P3 — Long-Term Ideas

## Pantry Tracking

### Goals
Track ingredients users already have.

### Notes
Could integrate with grocery generation later.

---

## Nutrition Support

### Goals
Optional nutritional estimates.

### Important
Should remain optional and lightweight.
Avoid turning app into calorie-tracker complexity.

---

## Recipe Sharing / Export

### Goals
- printable recipe cards
- shareable links
- markdown export
- PDF export

### Notes
Keep self-hosting/privacy focus intact.

---

## Multi-User Collaboration

### Goals
- shared cookbooks
- family meal planning
- collaborative grocery lists

### Notes
Large scope increase.
Should remain post-V2.

---

# Explicit Non-Goals (For Now)

Avoid turning Recipe Clipper into:
- social media platform
- influencer network
- Pinterest clone
- calorie obsession app
- enterprise SaaS complexity

The strength of Recipe Clipper is:
- practical cooking
- recipe organization
- import cleanup
- home-cook workflow
- self-host friendliness

---

# Architectural Direction

## Continue Principles From V1

- rules-first imports
- AI optional/enhancement only
- lightweight architecture
- portable Docker deployment
- worker isolation for heavy dependencies
- mobile-first practical UX

---

# Potential Future Technical Improvements

## Possible V2/V3 Candidates

- lightweight job queue
- async import orchestration
- image processing pipeline
- structured ingredient parser service
- AI-assisted search
- recipe deduplication

### Important
Do NOT prematurely overengineer.

---

# Overall Direction

Recipe Clipper should continue evolving toward:

```text
A practical self-hosted recipe workflow tool for real home cooks.
```

Not:

```text
A social recipe content platform.
```
