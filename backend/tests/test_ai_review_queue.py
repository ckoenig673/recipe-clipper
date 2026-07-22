import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app import main


def _insert_test_user() -> int:
    conn = main.get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (email, password_hash, is_admin, is_active, created_at) VALUES (?, ?, 1, 1, ?)",
        ("reviewer@example.com", "x", main.utcnow_iso()),
    )
    conn.commit()
    user_id = int(cur.lastrowid)
    conn.close()
    return user_id


def _insert_queued_recipe(user_id: int) -> int:
    conn = main.get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO recipes (
            user_id, title, url, source_app, source_type, needs_review, review_status, review_requested_at,
            ingredients, instructions, ingredient_groups, instruction_groups
        ) VALUES (?, ?, ?, ?, ?, 1, 'queued', ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            "Old title",
            "https://example.com/recipe",
            "Web",
            "Web",
            main.utcnow_iso(),
            json.dumps(["old ingredient"]),
            json.dumps(["old step"]),
            json.dumps([{"title": "Old", "items": ["old ingredient"]}]),
            json.dumps([{"title": "Old", "steps": ["old step"]}]),
        ),
    )
    conn.commit()
    recipe_id = int(cur.lastrowid)
    conn.close()
    return recipe_id


def test_review_status_coerce_maps_legacy_values_to_completed():
    assert main._coerce_review_status("review_ready") == "completed"
    assert main._coerce_review_status("reviewed") == "completed"


def test_worker_overwrites_groups_and_marks_completed():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "recipes.db"
        original_db = main.DB
        try:
            main.DB = str(db_path)
            main.init_db()
            user_id = _insert_test_user()
            recipe_id = _insert_queued_recipe(user_id)

            ollama_result = {
                "title": "Clean title",
                "ingredient_groups": [{"title": "", "items": ["2 cups flour"]}],
                "instruction_groups": [{"title": "", "steps": ["Mix", "Bake"]}],
            }
            with patch("backend.app.main.call_ollama_review", return_value=ollama_result), patch(
                "backend.app.main._recipe_ai_source_payload",
                return_value={"source": "test"},
            ):
                processed = main._run_review_worker_pass()

            assert processed is True
            conn = main.get_conn()
            row = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
            conn.close()

            assert row is not None
            assert row["review_status"] == "completed"
            assert json.loads(row["ingredient_groups"]) == [{"title": "", "items": ["2 cups flour"]}]
            assert json.loads(row["instruction_groups"]) == [{"title": "Instructions", "steps": ["Mix", "Bake"]}]
            assert json.loads(row["ingredients"]) == ["2 cups flour"]
            assert json.loads(row["instructions"]) == ["Mix", "Bake"]
        finally:
            main.DB = original_db


def _insert_saved_recipe(
    user_id: int,
    *,
    url: str = "https://example.com/messy",
    notes: str = "Use a hot skillet",
    ai_review_source_payload: dict | None = None,
) -> int:
    conn = main.get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO recipes (
            user_id, title, url, source_app, source_type, needs_review, review_status,
            notes, ingredients, instructions, ingredient_groups, instruction_groups, servings, prep_time, cook_time, total_time,
            ai_review_source_payload
        ) VALUES (?, ?, ?, ?, ?, 0, 'none', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            "Messy recipe",
            url,
            "Web",
            "Web",
            notes,
            json.dumps(["1 lb beef", "1 tbsp oil"]),
            json.dumps(["Cook beef", "Serve"]),
            json.dumps([{"title": "", "items": ["1 lb beef", "1 tbsp oil"]}]),
            json.dumps([{"title": "", "steps": ["Cook beef", "Serve"]}]),
            "4",
            "10 mins",
            "15 mins",
            "25 mins",
            json.dumps(ai_review_source_payload, ensure_ascii=False) if ai_review_source_payload else None,
        ),
    )
    conn.commit()
    recipe_id = int(cur.lastrowid)
    conn.close()
    return recipe_id


def test_manual_cleanup_payload_is_compact():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "recipes.db"
        original_db = main.DB
        try:
            main.DB = str(db_path)
            main.init_db()
            user_id = _insert_test_user()
            recipe_id = _insert_saved_recipe(user_id)
            conn = main.get_conn()
            row = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
            conn.close()

            payload = main._manual_ai_cleanup_payload_from_row(row)

            assert payload["title"] == "Messy recipe"
            assert payload["notes"] == "Use a hot skillet"
            assert payload["ingredient_groups"] == [{"title": "", "items": ["1 lb beef", "1 tbsp oil"]}]
            assert payload["instruction_groups"] == [{"title": "Instructions", "steps": ["Cook beef", "Serve"]}]
            assert payload["url"] == "https://example.com/messy"
        finally:
            main.DB = original_db


def test_manual_cleanup_payload_includes_saved_transcript_context():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "recipes.db"
        original_db = main.DB
        try:
            main.DB = str(db_path)
            main.init_db()
            user_id = _insert_test_user()
            recipe_id = _insert_saved_recipe(
                user_id,
                ai_review_source_payload={
                    "saved_cleanup_context": {
                        "cleaned_transcript_text": "Two and a fourth teaspoons of baking powder. Half a teaspoon baking soda.",
                    }
                },
            )
            conn = main.get_conn()
            row = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
            conn.close()

            payload = main._manual_ai_cleanup_payload_from_row(row)

            assert payload["_ai_cleanup_context"]["cleaned_transcript_text"].startswith("Two and a fourth teaspoons")
        finally:
            main.DB = original_db


def test_manual_cleanup_rejects_empty_result():
    normalized_result = {
        "ingredient_groups": [{"title": "", "items": []}],
        "instruction_groups": [{"title": "Instructions", "steps": ["Step 1"]}],
    }
    assert main._is_useful_ai_cleanup_result(normalized_result) is False


def test_ai_cleanup_prompt_explicitly_allows_no_change_result():
    prompt = main._build_transcript_cleanup_prompt(
        {
            "title": "Weeknight Tacos",
            "ingredient_groups": [{"title": "", "items": ["1 lb ground beef", "8 tortillas"]}],
            "instruction_groups": [{"title": "Instructions", "steps": ["Brown beef.", "Warm tortillas."]}],
        }
    )

    assert "Do NOT rewrite content for style alone." in prompt
    assert "Minor wording preferences, synonym swaps, and unnecessary rephrasing are not meaningful improvements." in prompt
    assert '"no_changes": false' in prompt
    assert "return the same recipe content unchanged and set no_changes to true" in prompt


def test_ai_cleanup_meaningful_change_detection_distinguishes_no_change_from_structural_improvement():
    well_structured = {
        "title": "Weeknight Tacos",
        "servings": "4",
        "ingredient_groups": [{"title": "Ingredients", "items": ["1 lb ground beef", "8 tortillas"]}],
        "instruction_groups": [{"title": "Instructions", "steps": ["Brown beef.", "Warm tortillas."]}],
    }
    structurally_improved = {
        "title": "Weeknight Tacos",
        "servings": "4",
        "ingredient_groups": [
            {"title": "Ingredients", "items": ["1 lb ground beef", "8 tortillas"]},
            {"title": "For serving", "items": ["lime wedges"]},
        ],
        "instruction_groups": [{"title": "Instructions", "steps": ["Brown beef.", "Warm tortillas.", "Serve with lime wedges."]}],
    }

    assert main._ai_cleanup_has_meaningful_changes(well_structured, well_structured) is False
    assert main._ai_cleanup_has_meaningful_changes(well_structured, structurally_improved) is True


def test_manual_ai_cleanup_returns_preview_for_saved_recipe_with_source_url_without_saving():
    client = TestClient(main.app)

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "recipes.db"
        original_db = main.DB
        main.app.dependency_overrides[main.require_user] = lambda: {"id": 1}
        try:
            main.DB = str(db_path)
            main.init_db()
            user_id = _insert_test_user()
            recipe_id = _insert_saved_recipe(user_id)
            conn = main.get_conn()
            before = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
            conn.close()

            parsed_json = {
                "title": "Cleaned recipe",
                "servings": "4",
                "prep_time": "12 mins",
                "cook_time": "15 mins",
                "total_time": "27 mins",
                "ingredient_groups": [{"title": "Ingredients", "items": ["1 lb lean beef", "1 tbsp oil"]}],
                "instruction_groups": [{"title": "Instructions", "steps": ["Brown beef.", "Season lightly.", "Serve warm."]}],
                "review_notes": "Tightened ingredient wording.",
            }
            normalized_result = main.normalize_ai_review_response(parsed_json)

            with patch(
                "backend.app.main._run_ai_cleanup_pipeline",
                return_value=(
                    parsed_json,
                    normalized_result,
                    "{}",
                    "input",
                    main._manual_ai_cleanup_payload_from_row(before),
                ),
            ) as mocked_pipeline:
                response = client.post(f"/recipes/{recipe_id}/ai-cleanup")

            assert response.status_code == 200
            payload = response.json()
            assert payload["payload_source"] == "ai_cleanup"
            assert payload["preview"]["title"] == "Cleaned recipe"
            assert payload["preview"]["ingredient_groups"] == [{"title": "Ingredients", "items": ["1 lb lean beef", "1 tbsp oil"]}]
            mocked_pipeline.assert_called_once()
            assert mocked_pipeline.call_args.kwargs["parsed_recipe"]["notes"] == "Use a hot skillet"
            assert mocked_pipeline.call_args.args[0] == "https://example.com/messy"

            conn = main.get_conn()
            after = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
            conn.close()
            assert dict(after) == dict(before)
        finally:
            main.app.dependency_overrides.pop(main.require_user, None)
            main.DB = original_db


def test_manual_ai_cleanup_returns_no_change_result_for_well_structured_recipe_without_saving():
    client = TestClient(main.app)

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "recipes.db"
        original_db = main.DB
        main.app.dependency_overrides[main.require_user] = lambda: {"id": 1}
        try:
            main.DB = str(db_path)
            main.init_db()
            user_id = _insert_test_user()
            recipe_id = _insert_saved_recipe(
                user_id,
                url="https://example.com/well-structured",
                notes="",
            )
            conn = main.get_conn()
            before = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
            conn.close()

            unchanged_payload = main._manual_ai_cleanup_payload_from_row(before)
            parsed_json = {
                "title": unchanged_payload["title"],
                "servings": unchanged_payload["servings"],
                "prep_time": unchanged_payload["prep_time"],
                "cook_time": unchanged_payload["cook_time"],
                "total_time": unchanged_payload["total_time"],
                "ingredient_groups": unchanged_payload["ingredient_groups"],
                "instruction_groups": unchanged_payload["instruction_groups"],
                "no_changes": True,
                "review_notes": "No meaningful improvements recommended.",
            }
            normalized_result = main.normalize_ai_review_response(parsed_json)

            with patch(
                "backend.app.main._run_ai_cleanup_pipeline",
                return_value=(
                    parsed_json,
                    normalized_result,
                    "{}",
                    "input",
                    unchanged_payload,
                ),
            ):
                response = client.post(f"/recipes/{recipe_id}/ai-cleanup")

            assert response.status_code == 200
            payload = response.json()
            assert payload["payload_source"] == "ai_cleanup"
            assert payload["no_changes"] is True
            assert payload["message"] == "No meaningful improvements recommended."
            assert payload["preview"]["title"] == before["title"]

            conn = main.get_conn()
            after = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
            conn.close()
            assert dict(after) == dict(before)
        finally:
            main.app.dependency_overrides.pop(main.require_user, None)
            main.DB = original_db


def test_manual_ai_cleanup_returns_preview_without_source_url_without_saving():
    client = TestClient(main.app)

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "recipes.db"
        original_db = main.DB
        main.app.dependency_overrides[main.require_user] = lambda: {"id": 1}
        try:
            main.DB = str(db_path)
            main.init_db()
            user_id = _insert_test_user()
            recipe_id = _insert_saved_recipe(user_id, url="")
            conn = main.get_conn()
            before = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
            conn.close()

            parsed_json = {
                "title": "Cleaned recipe",
                "servings": "4",
                "ingredient_groups": [{"title": "Ingredients", "items": ["1 lb beef", "1 tbsp oil"]}],
                "instruction_groups": [{"title": "Instructions", "steps": ["Cook beef.", "Serve."]}],
            }
            normalized_result = main.normalize_ai_review_response(parsed_json)

            with patch(
                "backend.app.main._run_ai_cleanup_pipeline",
                return_value=(
                    parsed_json,
                    normalized_result,
                    "{}",
                    "input",
                    main._manual_ai_cleanup_payload_from_row(before),
                ),
            ) as mocked_pipeline:
                response = client.post(f"/recipes/{recipe_id}/ai-cleanup")

            assert response.status_code == 200
            payload = response.json()
            assert payload["payload_source"] == "ai_cleanup"
            assert payload["preview"]["title"] == "Cleaned recipe"
            mocked_pipeline.assert_called_once()
            assert mocked_pipeline.call_args.args[0] is None
            assert mocked_pipeline.call_args.kwargs["parsed_recipe"]["notes"] == "Use a hot skillet"
            assert "url" not in mocked_pipeline.call_args.kwargs["parsed_recipe"]

            conn = main.get_conn()
            after = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
            conn.close()
            assert dict(after) == dict(before)
        finally:
            main.app.dependency_overrides.pop(main.require_user, None)
            main.DB = original_db


def test_normalize_ai_review_response_formats_component_array_ingredients():
    normalized = main.normalize_ai_review_response(
        {
            "ingredients": [
                ["white lily all-purpose flour", 2.25, "cups"],
                "'kosher salt', 1, 'teaspoon'",
            ],
            "instructions": ["Mix ingredients."],
        }
    )

    assert normalized["ingredient_groups"] == [
        {
            "title": "",
            "items": [
                "2.25 cups white lily all-purpose flour",
                "1 teaspoon kosher salt",
            ],
        }
    ]


def test_normalize_ai_review_response_formats_component_object_ingredients():
    normalized = main.normalize_ai_review_response(
        {
            "ingredient_groups": [
                {
                    "title": "",
                    "items": [
                        {
                            "name": "white lily all-purpose flour",
                            "amount": "2.25",
                            "unit": "cups",
                        }
                    ],
                }
            ],
            "instruction_groups": [{"title": "Instructions", "steps": ["Mix ingredients."]}],
        }
    )

    assert normalized["ingredient_groups"] == [
        {
            "title": "",
            "items": ["2.25 cups white lily all-purpose flour"],
        }
    ]


def test_normalize_ai_review_response_repairs_single_letter_unit_fragments_inside_ingredient_words():
    normalized = main.normalize_ai_review_response(
        {
            "ingredient_groups": [
                {
                    "title": "Vegetables",
                    "items": [
                        {"quantity": 1, "unit": "l", "name": "arge yellow onion, diced"},
                        {"quantity": 1, "unit": "g", "name": "reen bell pepper, diced"},
                        {"quantity": 3, "unit": "g", "name": "arlic cloves, minced"},
                        {"quantity": 2, "name": "green onions, thinly sliced"},
                    ],
                }
            ],
            "instruction_groups": [{"title": "Instructions", "steps": ["Cook gently."]}],
        }
    )

    assert normalized["ingredient_groups"] == [
        {
            "title": "Vegetables",
            "items": [
                "1 large yellow onion, diced",
                "1 green bell pepper, diced",
                "3 garlic cloves, minced",
                "2 green onions, thinly sliced",
            ],
        }
    ]


def test_normalize_ai_review_response_keeps_valid_single_letter_metric_unit_tokens():
    normalized = main.normalize_ai_review_response(
        {
            "ingredient_groups": [
                {
                    "title": "",
                    "items": [
                        {"quantity": 800, "unit": "g", "name": "boneless, skinless chicken thighs"},
                        {"quantity": 1, "unit": "l", "name": "chicken stock"},
                    ],
                }
            ],
            "instruction_groups": [{"title": "Instructions", "steps": ["Cook gently."]}],
        }
    )

    assert normalized["ingredient_groups"] == [
        {
            "title": "",
            "items": [
                "800 g boneless, skinless chicken thighs",
                "1 l chicken stock",
            ],
        }
    ]


def test_build_transcript_cleanup_prompt_formats_safe_fractions_and_preserves_suspicious_quantities():
    prompt = main._build_transcript_cleanup_prompt(
        {
            "title": "Biscuits",
            "ingredient_groups": [
                {
                    "title": "",
                    "items": [
                        "2.25 cups white lily all-purpose flour",
                        "1.5 sticks ice-cold butter",
                        "0.025 teaspoons baking powder",
                    ],
                }
            ],
            "instruction_groups": [{"title": "Instructions", "steps": ["Mix gently."]}],
        }
    )

    assert "2 1/4 cups White Lily all-purpose flour" in prompt
    assert "1 1/2 sticks ice-cold butter" in prompt
    assert "0.025 teaspoons baking powder" in prompt


def test_build_transcript_cleanup_prompt_repairs_spoken_fraction_quantities_from_saved_transcript():
    prompt = main._build_transcript_cleanup_prompt(
        {
            "title": "Biscuits",
            "ingredient_groups": [
                {
                    "title": "",
                    "items": [
                        "2.25 cups white lily all-purpose flour",
                        "0.025 teaspoons baking powder",
                        "0.005 teaspoons baking soda",
                        "1.5 sticks ice-cold butter",
                    ],
                }
            ],
            "instruction_groups": [{"title": "Instructions", "steps": ["Mix gently."]}],
            "_ai_cleanup_context": {
                "cleaned_transcript_text": (
                    "Use 2.25 cups white lily all-purpose flour. "
                    "Two and a fourth teaspoons of baking powder. "
                    "Half a teaspoon baking soda. "
                    "One and a half sticks ice-cold butter."
                )
            },
        }
    )

    assert "2 1/4 cups White Lily all-purpose flour" in prompt
    assert "2 1/4 teaspoons baking powder" in prompt
    assert "1/2 teaspoon baking soda" in prompt
    assert "1 1/2 sticks ice-cold butter" in prompt
    assert '"saved_transcript_text": "Use 2.25 cups white lily all-purpose flour.' in prompt


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("half a teaspoon", 0.5),
        ("a quarter cup", 0.25),
        ("one third cup", pytest.approx(1.0 / 3.0)),
        ("two thirds cup", pytest.approx(2.0 / 3.0)),
        ("three quarters cup", 0.75),
        ("one and a half sticks", 1.5),
        ("two and a quarter teaspoons", 2.25),
        ("two and a fourth teaspoons", 2.25),
    ],
)
def test_normalize_plain_string_list_converts_supported_spoken_quantities(phrase, expected):
    normalized = main._normalize_plain_string_list([f"{phrase} test ingredient"])
    parsed = main._parse_ingredient_struct(normalized[0])

    assert parsed["quantity"] == expected


def test_build_transcript_cleanup_prompt_preserves_suspicious_values_without_evidence_and_flags_them():
    prompt = main._build_transcript_cleanup_prompt(
        {
            "title": "Biscuits",
            "ingredient_groups": [
                {
                    "title": "",
                    "items": [
                        "0.025 teaspoons baking powder",
                        "0.005 teaspoons baking soda",
                    ],
                }
            ],
            "instruction_groups": [{"title": "Instructions", "steps": ["Mix gently."]}],
            "_ai_cleanup_context": {
                "cleaned_transcript_text": "Stir the dry ingredients together.",
            },
        }
    )

    assert "0.025 teaspoons baking powder" in prompt
    assert "0.005 teaspoons baking soda" in prompt
    assert '"suspicious_saved_ingredients": "0.025 teaspoons baking powder\\n0.005 teaspoons baking soda"' in prompt


def test_prepare_saved_recipe_for_ai_cleanup_repairs_current_biscuit_transcript_lines():
    prepared = main._prepare_saved_recipe_for_ai_cleanup(
        {
            "title": "Biscuits",
            "ingredient_groups": [
                {
                    "title": "",
                    "items": [
                        "0.025 teaspoons baking powder",
                        "0.005 teaspoons baking soda",
                        "0.005 teaspoons table salt",
                    ],
                }
            ],
            "_ai_cleanup_context": {
                "cleaned_transcript_text": (
                    "Two and a fourth teaspoons of baking powder. "
                    "Half a teaspoon baking soda. "
                    "Half a teaspoon table salt."
                )
            },
        }
    )

    assert prepared["ingredients"] == [
        "2 1/4 teaspoons baking powder",
        "1/2 teaspoon baking soda",
        "1/2 teaspoon table salt",
    ]


def test_normalize_ai_cleanup_prompt_payload_preserves_unmatched_parenthetical_ingredient_text():
    normalized = main._normalize_ai_cleanup_prompt_payload(
        {
            "title": "Bench Bread",
            "ingredient_groups": [
                {
                    "title": "",
                    "items": [
                        "1 cup flour (plus more for dusting",
                        "1 cup flour ) for the counter",
                        "1 cup flour (sifted) (plus more for dusting)",
                    ],
                }
            ],
            "instruction_groups": [{"title": "Instructions", "steps": ["Mix."]}],
        }
    )

    assert normalized["ingredient_groups"] == [
        {
            "title": "",
            "items": [
                "1 cup flour (plus more for dusting",
                "1 cup flour ) for the counter",
                "1 cup flour (sifted ; plus more for dusting)",
            ],
        }
    ]


def test_build_transcript_cleanup_prompt_includes_conservative_editor_rules():
    prompt = main._build_transcript_cleanup_prompt(
        {
            "title": "Biscuits",
            "ingredient_groups": [{"title": "", "items": ["2.25 cups flour"]}],
            "instruction_groups": [{"title": "Instructions", "steps": ["Bake."]}],
        },
        source_url="https://www.facebook.com/reel/1234567890123456",
        source_text="Optional source context",
    )

    assert "You are a conservative cookbook editor" in prompt
    assert "Capitalize proper nouns such as White Lily" in prompt
    assert "Do NOT silently fix suspicious values." in prompt
    assert "Source URL content is optional supporting context only." in prompt
    assert '"source_url": "https://www.facebook.com/reel/1234567890123456"' in prompt


def test_ai_cleanup_has_meaningful_changes_ignores_capitalization_only_differences():
    current = {
        "title": "weeknight biscuits",
        "ingredient_groups": [{"title": "", "items": ["2.25 cups white lily all-purpose flour"]}],
        "instruction_groups": [{"title": "Instructions", "steps": ["Mix ingredients gently."]}],
    }
    proposed = {
        "title": "Weeknight Biscuits",
        "ingredient_groups": [{"title": "", "items": ["2.25 cups White Lily all-purpose flour"]}],
        "instruction_groups": [{"title": "instructions", "steps": ["Mix ingredients gently."]}],
    }

    assert main._ai_cleanup_has_meaningful_changes(current, proposed) is False


def test_manual_ai_cleanup_uses_saved_recipe_when_facebook_fetch_fails(caplog):
    client = TestClient(main.app)

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "recipes.db"
        original_db = main.DB
        original_ollama = main.OLLAMA_BASE_URL
        main.app.dependency_overrides[main.require_user] = lambda: {"id": 1}
        try:
            main.DB = str(db_path)
            main.OLLAMA_BASE_URL = "http://ollama:11434"
            main.init_db()
            user_id = _insert_test_user()
            recipe_id = _insert_saved_recipe(
                user_id,
                url="https://www.facebook.com/reel/1234567890123456",
                ai_review_source_payload={
                    "saved_cleanup_context": {
                        "cleaned_transcript_text": "Two and a fourth teaspoons of baking powder.",
                    }
                },
            )

            ollama_payload = {
                "response": json.dumps(
                    {
                        "title": "Messy recipe",
                        "servings": "4",
                        "ingredient_groups": [{"title": "", "items": ["2.25 cups white lily all-purpose flour", "1 tbsp oil"]}],
                        "instruction_groups": [{"title": "Instructions", "steps": ["Cook beef.", "Serve."]}],
                        "review_notes": "Normalized transcript ingredient formatting.",
                    }
                )
            }

            captured_request: dict = {}

            class _Response:
                def raise_for_status(self):
                    return None

                def json(self):
                    return ollama_payload

            def _fake_post(url, json, timeout):
                captured_request["url"] = url
                captured_request["json"] = json
                captured_request["timeout"] = timeout
                return _Response()

            with patch("backend.app.main._fetch_html_for_ai_cleanup", side_effect=RuntimeError("facebook returned 403")), patch(
                "backend.app.main.requests.post",
                side_effect=_fake_post,
            ):
                response = client.post(f"/recipes/{recipe_id}/ai-cleanup")

            assert response.status_code == 200
            payload = response.json()
            assert payload["payload_source"] == "ai_cleanup"
            assert payload["preview"]["ingredient_groups"] == [
                {
                    "title": "",
                    "items": ["2.25 cups white lily all-purpose flour", "1 tbsp oil"],
                }
            ]
            assert "ai_cleanup_source_fetch_failed url=https://www.facebook.com/reel/1234567890123456" in caplog.text
            assert "facebook returned 403" in caplog.text
            prompt = captured_request["json"]["prompt"]
            assert "structured_recipe:\n" in prompt
            assert "1 pound beef" in prompt
            assert "Do NOT silently fix suspicious values." in prompt
            assert '"source_url": "https://www.facebook.com/reel/1234567890123456"' in prompt
            assert '"saved_transcript_text": "Two and a fourth teaspoons of baking powder."' in prompt
            assert '"source_text"' not in prompt
        finally:
            main.app.dependency_overrides.pop(main.require_user, None)
            main.DB = original_db
            main.OLLAMA_BASE_URL = original_ollama


def test_manual_ai_cleanup_returns_no_change_for_capitalization_only_preview():
    client = TestClient(main.app)

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "recipes.db"
        original_db = main.DB
        main.app.dependency_overrides[main.require_user] = lambda: {"id": 1}
        try:
            main.DB = str(db_path)
            main.init_db()
            user_id = _insert_test_user()
            recipe_id = _insert_saved_recipe(user_id)
            conn = main.get_conn()
            before = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
            conn.close()

            parsed_json = {
                "title": "Messy Recipe",
                "servings": "4",
                "ingredient_groups": [{"title": "", "items": ["1 lb Beef", "1 tbsp Oil"]}],
                "instruction_groups": [{"title": "", "steps": ["Cook Beef", "Serve"]}],
                "review_notes": "Capitalized a few words.",
            }
            normalized_result = main.normalize_ai_review_response(parsed_json)

            with patch(
                "backend.app.main._run_ai_cleanup_pipeline",
                return_value=(
                    parsed_json,
                    normalized_result,
                    "{}",
                    "input",
                    main._manual_ai_cleanup_payload_from_row(before),
                ),
            ):
                response = client.post(f"/recipes/{recipe_id}/ai-cleanup")

            assert response.status_code == 200
            payload = response.json()
            assert payload["no_changes"] is True
            assert payload["message"] == "No meaningful improvements recommended."
        finally:
            main.app.dependency_overrides.pop(main.require_user, None)
            main.DB = original_db


def test_extract_recipe_text_for_ai_scopes_and_trims():
    html = """
    <html><body>
      <article>
        <div class="wprm-recipe-container">
          <h2>Ingredients</h2>
          <p>1 lb beef</p>
          <h3>Big Mac Sauce</h3>
          <p>1/2 cup mayo</p>
          <h2>Instructions</h2>
          <p>Cook beef.</p>
          <p>Assemble bowls.</p>
          <h3>Notes</h3>
          <p>this should be trimmed</p>
        </div>
      </article>
    </body></html>
    """
    text = main.extract_recipe_text_for_ai(html)
    assert "Ingredients" in text
    assert "Assemble bowls." in text
    assert "this should be trimmed" not in text


def test_build_ai_input_from_parsed_recipe_preserves_group_boundaries():
    parsed_recipe = {
        "title": "Big Mac Recipe",
        "ingredient_groups": [
            {"title": "", "items": ["1 lb. lean ground beef 96/4", "1/2 cup onion chopped"]},
            {"title": "Big Mac Sauce", "items": ["1/3 cup ketchup 100g"]},
            {"title": "For Your Bowls", "items": ["8 cups shredded iceberg lettuce"]},
        ],
        "instruction_groups": [
            {"title": "", "steps": ["Cook beef and onion."]},
            {"title": "Bowl Assembly", "steps": ["Fill each bowl with lettuce."]},
        ],
    }

    shaped = main._build_ai_input_from_parsed_recipe(parsed_recipe)

    assert "Title:\nBig Mac Recipe" in shaped
    assert "Ingredients\n1 lb. lean ground beef 96/4\n1/2 cup onion chopped" in shaped
    assert "Big Mac Sauce\n1/3 cup ketchup 100g" in shaped
    assert "For Your Bowls\n8 cups shredded iceberg lettuce" in shaped
    assert "Instructions\nCook beef and onion." in shaped
    assert "Bowl Assembly\nFill each bowl with lettuce." in shaped


def test_run_ai_cleanup_pipeline_uses_cleaned_recipe_text_when_fetch_succeeds():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "recipes.db"
        original_db = main.DB
        try:
            main.DB = str(db_path)
            main.init_db()
            html = "<html><body><article><h2>Ingredients</h2><p>1/2 cup mayo</p><h2>Instructions</h2><p>Whisk sauce</p></article></body></html>"
            ollama_payload = {"response": '{"title":"Messy recipe","servings":"","ingredient_groups":[{"title":"Ingredients","items":["1/2 cup mayo"]}],"instruction_groups":[{"title":"Instructions","steps":["Whisk sauce"]}]}'}

            class _Response:
                def raise_for_status(self):
                    return None

                def json(self):
                    return ollama_payload

            parsed_recipe = {
                "title": "Messy recipe",
                "ingredient_groups": [{"title": "Ingredients", "items": ["1/2 cup mayo"]}],
                "instruction_groups": [{"title": "Instructions", "steps": ["Whisk sauce"]}],
            }

            with patch("backend.app.main.OLLAMA_BASE_URL", "http://ollama:11434"), patch("backend.app.main._fetch_html_for_ai_cleanup", return_value=html), patch(
                "backend.app.main.requests.post", return_value=_Response()
            ):
                parsed, normalized, raw, source_text, returned_parsed_recipe = main._run_ai_cleanup_pipeline(
                    "https://example.com/recipe",
                    parsed_recipe=parsed_recipe,
                )

            assert parsed == json.loads(ollama_payload["response"])
            assert "Title:\nMessy recipe" in source_text
            assert "Ingredients" in source_text
            assert "Whisk sauce" in source_text
            assert raw == ollama_payload["response"]
            assert returned_parsed_recipe["title"] == parsed_recipe["title"]
            assert returned_parsed_recipe["ingredient_groups"] == parsed_recipe["ingredient_groups"]
            assert returned_parsed_recipe["instruction_groups"] == parsed_recipe["instruction_groups"]
            assert normalized["ingredient_groups"] == [{"title": "Ingredients", "items": ["1/2 cup mayo"]}]
            assert normalized["instruction_groups"] == [{"title": "Instructions", "steps": ["Whisk sauce"]}]
        finally:
            main.DB = original_db


def test_run_ai_cleanup_pipeline_rejects_invalid_json_response():
    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"response": "not valid json"}

    html = "<html><body><article><h2>Ingredients</h2><p>1/2 cup mayo</p><h2>Instructions</h2><p>Whisk sauce</p></article></body></html>"
    with patch("backend.app.main.OLLAMA_BASE_URL", "http://ollama:11434"), patch("backend.app.main._fetch_html_for_ai_cleanup", return_value=html), patch(
        "backend.app.main.requests.post", return_value=_Response()
    ):
        try:
            main._run_ai_cleanup_pipeline("https://example.com/recipe")
            assert False, "Expected HTTPException for invalid JSON response"
        except main.HTTPException as exc:
            assert exc.status_code == 422


def test_normalize_ai_review_response_keeps_ingredient_items_as_plain_strings():
    payload = {
        "ingredient_groups": [
            {
                "title": "Ingredients",
                "items": [
                    " 1 lb. lean ground beef 96/4 ",
                    "1/3 cup light mayonnaise 90g",
                    "1/3 cup ketchup 100g",
                    "1/2 cup shredded cheddar cheese 56g",
                ],
            }
        ],
        "instruction_groups": [{"title": "Instructions", "steps": ["Mix ingredients."]}],
    }

    normalized = main.normalize_ai_review_response(payload)

    assert normalized["ingredient_groups"] == [
        {
            "title": "Ingredients",
            "items": [
                "1 lb. lean ground beef 96/4",
                "1/3 cup light mayonnaise 90g",
                "1/3 cup ketchup 100g",
                "1/2 cup shredded cheddar cheese 56g",
            ],
        }
    ]


def test_normalize_ai_review_response_filters_header_like_ingredient_rows_but_keeps_quantity_free_ingredients():
    payload = {
        "ingredient_groups": [
            {
                "title": "Ingredients",
                "items": [
                    "Big Mac Salad; 1 LEANER",
                    "For the Bowls:",
                    "2 Tablespoons onion, diced",
                    "Dill Pickle spears",
                    "salt and black pepper to taste",
                    "Healthy Fat",
                ],
            }
        ],
        "instruction_groups": [{"title": "Instructions", "steps": ["Mix ingredients."]}],
    }

    normalized = main.normalize_ai_review_response(payload)

    assert normalized["ingredient_groups"] == [
        {
            "title": "Ingredients",
            "items": [
                "2 Tablespoons onion, diced",
                "Dill Pickle spears",
                "salt and black pepper to taste",
            ],
        }
    ]


def test_modal_ai_cleanup_uses_parsed_ai_json_groups_for_preview():
    parsed_json = {
        "title": "Big Mac Bowls",
        "servings": "4",
        "ingredient_groups": [
            {"title": "Ingredients", "items": ["1 lb beef"]},
            {"title": "Big Mac Sauce", "items": ["1/3 cup mayo"]},
            {"title": "For Your Bowls", "items": ["8 cups lettuce"]},
        ],
        "instruction_groups": [
            {"title": "Instructions", "steps": ["Cook beef."]},
            {"title": "Bowl Assembly", "steps": ["Build bowls."]},
            {"title": "Meal Prep Assembly", "steps": ["Store bowls."]},
        ],
    }
    normalized_result = {
        "ingredient_groups": [{"title": "Ingredients", "items": ["1 lb beef", "1/3 cup mayo", "8 cups lettuce"]}],
        "instruction_groups": [{"title": "Instructions", "steps": ["Cook beef.", "Build bowls.", "Store bowls."]}],
    }
    payload = main.ModalAiCleanupRequest(
        url="https://example.com/big-mac-bowls",
        preview={},
    )

    with patch(
        "backend.app.main._run_ai_cleanup_pipeline",
        return_value=(parsed_json, normalized_result, "{}", "input", {}),
    ):
        response = main.run_modal_ai_cleanup(payload, _={"id": 1})

    assert response["payload_source"] == "ai_cleanup"
    assert response["preview"]["ingredient_groups"] == parsed_json["ingredient_groups"]
    assert response["preview"]["instruction_groups"] == parsed_json["instruction_groups"]
    assert response["preview"]["ingredients"] == ["1 lb beef", "1/3 cup mayo", "8 cups lettuce"]
    assert response["preview"]["instructions"] == ["Cook beef.", "Build bowls.", "Store bowls."]


def test_modal_preview_payload_from_parsed_ai_json_is_direct_passthrough():
    parsed_json = {
        "title": "Big Mac Bowls",
        "servings": "4",
        "ingredient_groups": [{"title": "Ingredients", "items": ["1 lb beef", "1/3 cup mayo", "8 cups lettuce"]}],
        "instruction_groups": [{"title": "Instructions", "steps": ["Cook beef.", "Build bowls.", "Store bowls."]}],
    }
    parsed_recipe = {"ingredient_groups": [{"title": "Unused", "items": ["a"]}]}

    preview = main._modal_preview_payload_from_parsed_ai_json(parsed_json, parsed_recipe)

    assert preview["title"] == "Big Mac Bowls"
    assert preview["servings"] == "4"
    assert preview["ingredient_groups"] == parsed_json["ingredient_groups"]
    assert preview["instruction_groups"] == parsed_json["instruction_groups"]
    assert preview["ingredients"] == ["1 lb beef", "1/3 cup mayo", "8 cups lettuce"]
    assert preview["instructions"] == ["Cook beef.", "Build bowls.", "Store bowls."]


def test_modal_preview_payload_from_parsed_ai_json_uses_flat_ingredients_and_instructions():
    parsed_json = {
        "title": "OPTAVIA Mini Mac In A Bowl",
        "ingredients": [
            {"name": "onion", "quantity": "2 Tablespoons", "description": "diced"},
            {"name": "ground beef", "quantity": "5 ounces", "description": "95-97% Lean"},
        ],
        "instructions": ["Heat skillet.", "Cook beef."],
    }

    preview = main._modal_preview_payload_from_parsed_ai_json(parsed_json, parsed_recipe={})

    assert preview["title"] == "OPTAVIA Mini Mac In A Bowl"
    assert preview["ingredients"]
    assert preview["ingredient_groups"]
    assert preview["instructions"] == ["Heat skillet.", "Cook beef."]
    assert preview["instruction_groups"]


def test_modal_preview_payload_from_parsed_ai_json_filters_header_like_flat_ingredient_rows():
    parsed_json = {
        "title": "OPTAVIA Mini Mac In A Bowl",
        "ingredients": [
            "Big Mac Salad; 1 LEANER",
            "5 ounces 95-97% lean ground beef",
            "Dill Pickle spears",
            "For the Sauce:",
        ],
        "instructions": ["Heat skillet.", "Cook beef."],
    }

    preview = main._modal_preview_payload_from_parsed_ai_json(parsed_json, parsed_recipe={})

    assert preview["ingredients"] == [
        "5 ounces 95-97% lean ground beef",
        "Dill Pickle spears",
    ]
    assert preview["ingredient_groups"] == [
        {
            "title": "",
            "items": [
                "5 ounces 95-97% lean ground beef",
                "Dill Pickle spears",
            ],
        }
    ]


def test_modal_preview_payload_from_parsed_ai_json_strips_contaminated_group_title():
    parsed_json = {
        "title": "OPTAVIA Mini Mac In A Bowl",
        "ingredient_groups": [
            {
                "title": "Big Mac Salad; 1 LEANER, 3 GREENS, 1 HEALTHY FAT, 3 CONDIMENTS, 1/2 SNACK Source: Pinterest",
                "items": [
                    "5 ounces 95-97% Lean Ground Beef",
                    "1 ounce Dill Pickle Slices",
                ],
            }
        ],
        "instruction_groups": [{"title": "Instructions", "steps": ["Cook beef."]}],
    }

    preview = main._modal_preview_payload_from_parsed_ai_json(parsed_json, parsed_recipe={})

    assert preview["ingredient_groups"] == [
        {
            "title": "",
            "items": [
                "5 ounces 95-97% Lean Ground Beef",
                "1 ounce Dill Pickle Slices",
            ],
        }
    ]
    assert preview["ingredients"] == [
        "5 ounces 95-97% Lean Ground Beef",
        "1 ounce Dill Pickle Slices",
    ]


def test_modal_preview_payload_from_parsed_ai_json_supports_amount_and_weight_ingredient_objects():
    parsed_json = {
        "title": "Big Mac Bowls",
        "ingredients": [
            {
                "name": "light mayonnaise",
                "amount": "1/3 cup",
                "weight": "90g",
            }
        ],
        "instructions": ["Mix ingredients."],
    }

    preview = main._modal_preview_payload_from_parsed_ai_json(parsed_json, parsed_recipe={})

    assert preview["ingredients"] == ["1/3 cup light mayonnaise 90g"]


def test_modal_preview_payload_from_parsed_ai_json_normalizes_spoken_quantities():
    parsed_json = {
        "title": "Biscuits",
        "ingredient_groups": [
            {
                "title": "",
                "items": [
                    {"quantity": "two and a fourth", "unit": "teaspoons", "name": "baking powder"},
                    {"quantity": "half a", "unit": "teaspoon", "name": "baking soda"},
                    {"quantity": "a quarter", "unit": "cup", "name": "buttermilk"},
                    {"quantity": "one and a half", "unit": "sticks", "name": "butter"},
                ],
            }
        ],
        "instruction_groups": [{"title": "Instructions", "steps": ["Mix ingredients."]}],
    }

    preview = main._modal_preview_payload_from_parsed_ai_json(parsed_json, parsed_recipe={})

    assert preview["ingredient_groups"] == [
        {
            "title": "",
            "items": [
                "2.25 teaspoons baking powder",
                "0.5 teaspoon baking soda",
                "0.25 cup buttermilk",
                "1.5 sticks butter",
            ],
        }
    ]
    assert preview["ingredients"] == [
        "2.25 teaspoons baking powder",
        "0.5 teaspoon baking soda",
        "0.25 cup buttermilk",
        "1.5 sticks butter",
    ]


def test_modal_preview_payload_normalizes_numbered_steps_within_groups():
    parsed_json = {
        "instruction_groups": [
            {
                "title": "Instructions",
                "steps": ["1. Cook beef. 2. Mix sauce."],
            }
        ]
    }

    preview = main._modal_preview_payload_from_parsed_ai_json(parsed_json, parsed_recipe={})

    assert preview["instruction_groups"] == [
        {
            "title": "Instructions",
            "steps": ["1. Cook beef.", "2. Mix sauce."],
        }
    ]
    assert preview["instructions"] == ["1. Cook beef.", "2. Mix sauce."]


def test_modal_preview_payload_keeps_group_sections_separate_while_splitting_numbered_blobs():
    parsed_json = {
        "instruction_groups": [
            {"title": "Instructions", "steps": ["1. Cook beef. 2. Mix sauce."]},
            {"title": "Bowl Assembly", "steps": ["1. Add lettuce. 2. Add beef."]},
            {"title": "Meal Prep Assembly", "steps": ["1. Portion bowls. 2. Refrigerate."]},
        ]
    }

    preview = main._modal_preview_payload_from_parsed_ai_json(parsed_json, parsed_recipe={})

    assert preview["instruction_groups"] == [
        {"title": "Instructions", "steps": ["1. Cook beef.", "2. Mix sauce."]},
        {"title": "Bowl Assembly", "steps": ["1. Add lettuce.", "2. Add beef."]},
        {"title": "Meal Prep Assembly", "steps": ["1. Portion bowls.", "2. Refrigerate."]},
    ]


def test_modal_preview_payload_does_not_split_non_numbered_instruction_sentence():
    parsed_json = {
        "instruction_groups": [
            {"title": "Instructions", "steps": ["Cook beef until browned."]},
        ]
    }

    preview = main._modal_preview_payload_from_parsed_ai_json(parsed_json, parsed_recipe={})

    assert preview["instruction_groups"] == [
        {"title": "Instructions", "steps": ["Cook beef until browned."]},
    ]


def test_modal_ai_cleanup_prefers_preview_instructions_when_ai_downgrades_steps():
    parsed_json = {
        "title": "Big Mac Bowls",
        "servings": "4",
        "ingredient_groups": [{"title": "Ingredients", "items": ["1 lb beef", "1/3 cup mayo"]}],
        "instruction_groups": [{"title": "Instructions", "steps": ["Assemble each bowl.", "Reheat meat or enjoy cold."]}],
    }
    normalized_result = {
        "ingredient_groups": [{"title": "Ingredients", "items": ["1 lb beef", "1/3 cup mayo"]}],
        "instruction_groups": [{"title": "Instructions", "steps": ["Assemble each bowl.", "Reheat meat or enjoy cold."]}],
    }
    payload = main.ModalAiCleanupRequest(
        url="https://example.com/big-mac-bowls",
        preview={
            "title": "Big Mac Bowls",
            "instruction_groups": [
                {
                    "title": "Instructions",
                    "steps": [
                        "Spray skillet and cook beef.",
                        "Add seasoning and stir.",
                        "Mix sauce.",
                        "Assemble bowls.",
                    ],
                }
            ],
        },
    )

    with patch(
        "backend.app.main._run_ai_cleanup_pipeline",
        return_value=(parsed_json, normalized_result, "{}", "input", {}),
    ):
        response = main.run_modal_ai_cleanup(payload, _={"id": 1})

    assert response["payload_source"] == "ai_cleanup"
    assert response["preview"]["instructions"] == [
        "Spray skillet and cook beef.",
        "Add seasoning and stir.",
        "Mix sauce.",
        "Assemble bowls.",
    ]


def test_modal_ai_cleanup_sanitizes_preview_ingredient_group_titles_when_preview_is_preferred():
    parsed_json = {
        "title": "OPTAVIA Mini Mac In A Bowl",
        "servings": "1",
        "ingredient_groups": [{"title": "", "items": ["5 ounces 95-97% Lean Ground Beef"]}],
        "instruction_groups": [{"title": "Instructions", "steps": ["Cook beef."]}],
    }
    normalized_result = {
        "ingredient_groups": [{"title": "", "items": ["5 ounces 95-97% Lean Ground Beef"]}],
        "instruction_groups": [{"title": "Instructions", "steps": ["Cook beef."]}],
    }
    payload = main.ModalAiCleanupRequest(
        url="https://example.com/optavia-mini-mac",
        preview={
            "title": "OPTAVIA Mini Mac In A Bowl",
            "ingredient_groups": [
                {
                    "title": "Big Mac Salad; 1 LEANER, 3 GREENS, 1 HEALTHY FAT, 3 CONDIMENTS, 1/2 SNACK Source: Pinterest",
                    "items": [
                        "2 Tablespoons yellow or white onion ; diced",
                        "5 ounces 95-97% Lean Ground Beef",
                    ],
                }
            ],
        },
    )

    with patch(
        "backend.app.main._run_ai_cleanup_pipeline",
        return_value=(parsed_json, normalized_result, "{}", "input", {}),
    ):
        response = main.run_modal_ai_cleanup(payload, _={"id": 1})

    assert response["preview"]["ingredient_groups"] == [
        {
            "title": "",
            "items": [
                "2 Tablespoons yellow or white onion ; diced",
                "5 ounces 95-97% Lean Ground Beef",
            ],
        }
    ]
    assert response["preview"]["ingredients"] == [
        "2 Tablespoons yellow or white onion ; diced",
        "5 ounces 95-97% Lean Ground Beef",
    ]


def test_prefer_richer_preview_payload_compares_sanitized_ingredient_coverage():
    preview_payload = {
        "title": "OPTAVIA Mini Mac In A Bowl",
        "ingredient_groups": [
            {
                "title": "Big Mac Salad; 1 LEANER, 3 GREENS, 1 HEALTHY FAT, 3 CONDIMENTS",
                "items": [
                    "Big Mac Salad; 1 LEANER",
                    "5 ounces 95-97% lean ground beef",
                    "lettuce",
                    "cheddar cheese",
                    "Dill Pickle spears",
                ],
            }
        ],
        "instruction_groups": [{"title": "Instructions", "steps": ["Cook beef.", "Assemble bowl."]}],
    }
    ai_preview_payload = {
        "title": "OPTAVIA Mini Mac In A Bowl",
        "ingredient_groups": [
            {
                "title": "Ingredients",
                "items": [
                    "5 ounces 95-97% lean ground beef",
                    "lettuce",
                    "cheddar cheese",
                    "Dill Pickle spears",
                ],
            }
        ],
        "instruction_groups": [{"title": "Instructions", "steps": ["Cook beef.", "Assemble bowl."]}],
    }

    merged = main._prefer_richer_preview_payload(preview_payload, ai_preview_payload)

    assert merged["ingredient_groups"] == [
        {
            "title": "Ingredients",
            "items": [
                "5 ounces 95-97% lean ground beef",
                "lettuce",
                "cheddar cheese",
                "Dill Pickle spears",
            ],
        }
    ]
    assert merged["ingredients"] == [
        "5 ounces 95-97% lean ground beef",
        "lettuce",
        "cheddar cheese",
        "Dill Pickle spears",
    ]


def test_prefer_richer_preview_payload_keeps_sanitized_preview_when_it_has_more_legitimate_ingredients():
    preview_payload = {
        "title": "OPTAVIA Mini Mac In A Bowl",
        "ingredient_groups": [
            {
                "title": "For the Bowls:",
                "items": [
                    "Big Mac Salad; 1 LEANER",
                    "5 ounces 95-97% lean ground beef",
                    "lettuce",
                    "cheddar cheese",
                    "Dill Pickle spears",
                    "salt",
                    "pepper",
                ],
            }
        ],
        "instruction_groups": [{"title": "Instructions", "steps": ["Cook beef.", "Assemble bowl."]}],
    }
    ai_preview_payload = {
        "title": "OPTAVIA Mini Mac In A Bowl",
        "ingredient_groups": [
            {
                "title": "Ingredients",
                "items": [
                    "5 ounces 95-97% lean ground beef",
                    "lettuce",
                    "cheddar cheese",
                    "Dill Pickle spears",
                ],
            }
        ],
        "instruction_groups": [{"title": "Instructions", "steps": ["Cook beef.", "Assemble bowl."]}],
    }

    merged = main._prefer_richer_preview_payload(preview_payload, ai_preview_payload)

    assert merged["ingredient_groups"] == [
        {
            "title": "For the Bowls",
            "items": [
                "5 ounces 95-97% lean ground beef",
                "lettuce",
                "cheddar cheese",
                "Dill Pickle spears",
                "salt",
                "pepper",
            ],
        }
    ]
    assert "Big Mac Salad; 1 LEANER" not in merged["ingredients"]


def test_modal_ai_cleanup_does_not_restore_contaminated_preview_headers_when_ai_result_is_shorter():
    parsed_json = {
        "title": "OPTAVIA Mini Mac In A Bowl",
        "servings": "1",
        "ingredient_groups": [
            {
                "title": "Ingredients",
                "items": [
                    "2 Tablespoons yellow or white onion ; diced",
                    "5 ounces 95-97% Lean Ground Beef",
                    "3 cups Romaine Lettuce ; shredded",
                    "2 Tablespooons Reduced-Fat Cheddar Cheese ; shredded",
                    "1 ounce Dill Pickle Slices",
                    "1 teaspoon sesame seeds",
                    "Cooking Spray",
                ],
            }
        ],
        "instruction_groups": [{"title": "Instructions", "steps": ["Cook beef.", "Assemble bowls."]}],
    }
    normalized_result = {
        "ingredient_groups": parsed_json["ingredient_groups"],
        "instruction_groups": parsed_json["instruction_groups"],
    }
    payload = main.ModalAiCleanupRequest(
        url="https://example.com/optavia-mini-mac",
        preview={
            "title": "OPTAVIA Mini Mac In A Bowl",
            "ingredient_groups": [
                {
                    "title": "Big Mac Salad; 1 LEANER, 3 GREENS, 1 HEALTHY FAT, 3 CONDIMENTS, 1/2 SNACK Source: Pinterest/OPTAVIA30 Recipe Text Photos Nutr Nutrition Notes INGREDIENTS",
                    "items": [
                        "Big Mac Salad; 1 LEANER",
                        "2 Tablespoons yellow or white onion ; diced",
                        "5 ounces 95-97% Lean Ground Beef",
                        "2 Tablespoons Wish-Bone Light Thousand Island Dressing",
                        "1/8 teaspoon White Vinegar",
                        "1/8 teaspoon Onion Powder",
                        "3 cups Romaine Lettuce ; shredded",
                        "2 Tablespooons Reduced-Fat Cheddar Cheese ; shredded",
                        "1 ounce Dill Pickle Slices",
                        "1 teaspoon sesame seeds",
                        "Cooking Spray",
                    ],
                }
            ],
            "instruction_groups": [{"title": "Instructions", "steps": ["Cook beef.", "Assemble bowls."]}],
        },
    )

    with patch(
        "backend.app.main._run_ai_cleanup_pipeline",
        return_value=(parsed_json, normalized_result, "{}", "input", {}),
    ):
        response = main.run_modal_ai_cleanup(payload, _={"id": 1})

    assert response["payload_source"] == "ai_cleanup"
    assert response["preview"]["ingredient_groups"] == [
        {
            "title": "",
            "items": [
                "2 Tablespoons yellow or white onion ; diced",
                "5 ounces 95-97% Lean Ground Beef",
                "2 Tablespoons Wish-Bone Light Thousand Island Dressing",
                "1/8 teaspoon White Vinegar",
                "1/8 teaspoon Onion Powder",
                "3 cups Romaine Lettuce ; shredded",
                "2 Tablespooons Reduced-Fat Cheddar Cheese ; shredded",
                "1 ounce Dill Pickle Slices",
                "1 teaspoon sesame seeds",
                "Cooking Spray",
            ],
        }
    ]
    assert response["preview"]["ingredients"] == response["preview"]["ingredient_groups"][0]["items"]
    assert all("Big Mac Salad; 1 LEANER" not in item for item in response["preview"]["ingredients"])


def test_modal_ai_cleanup_endpoint_sanitizes_preview_payload_when_ai_cleanup_falls_back():
    client = TestClient(main.app)
    main.app.dependency_overrides[main.require_user] = lambda: {"id": 1}

    try:
        with patch(
            "backend.app.main._run_ai_cleanup_pipeline",
            side_effect=main.HTTPException(status_code=422, detail="AI cleanup returned empty recipe structure"),
        ):
            response = client.post(
                "/recipes/modal-ai-cleanup",
                json={
                    "url": "https://example.com/optavia-mini-mac",
                    "preview": {
                        "title": "OPTAVIA Mini Mac In A Bowl",
                        "ingredient_groups": [
                            {
                                "title": "Big Mac Salad; 1 LEANER, 3 GREENS, 1 HEALTHY FAT, 3 CONDIMENTS",
                                "items": [
                                    "Big Mac Salad; 1 LEANER",
                                    "5 ounces 95-97% Lean Ground Beef",
                                    "Dill Pickle spears",
                                    "salt and black pepper to taste",
                                ],
                            }
                        ],
                        "instruction_groups": [{"title": "Instructions", "steps": ["Cook beef.", "Assemble bowl."]}],
                    },
                },
            )
    finally:
        main.app.dependency_overrides.pop(main.require_user, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["payload_source"] == "recipe_container"
    assert payload["preview"]["ingredient_groups"] == [
        {
            "title": "",
            "items": [
                "5 ounces 95-97% Lean Ground Beef",
                "Dill Pickle spears",
                "salt and black pepper to taste",
            ],
        }
    ]
    assert payload["preview"]["ingredients"] == [
        "5 ounces 95-97% Lean Ground Beef",
        "Dill Pickle spears",
        "salt and black pepper to taste",
    ]
