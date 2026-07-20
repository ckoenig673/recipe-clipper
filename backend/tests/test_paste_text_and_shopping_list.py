import os
import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import main


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "paste_text_house_jambalaya"


def _load_paste_text_fixture() -> tuple[str, dict]:
    raw_text = (FIXTURE_ROOT / "raw.txt").read_text(encoding="utf-8")
    expected = json.loads((FIXTURE_ROOT / "parsed_expected.json").read_text(encoding="utf-8"))
    return raw_text, expected


def test_parse_pasted_recipe_text_builds_reviewable_recipe():
    raw_text = """
    Pecan Milk
    Servings: 2
    Prep time: 5 min

    Ingredients
    1 cup pecans
    1/2 cup milk

    Instructions
    Add pecans to blender.
    Blend until smooth.
    """

    parsed = main._parse_pasted_recipe_text(raw_text)

    assert parsed["title"] == "Pecan Milk"
    assert parsed["servings"] == "2"
    assert parsed["prep_time"] == "5 minutes"
    assert parsed["ingredients"] == ["1 cup pecans", "1/2 cup milk"]
    assert parsed["instructions"] == ["Add pecans to blender.", "Blend until smooth."]
    assert parsed["ingredient_groups"] == [{"title": "", "items": ["1 cup pecans", "1/2 cup milk"]}]
    assert parsed["instruction_groups"] == [
        {"title": "Instructions", "steps": ["Add pecans to blender.", "Blend until smooth."]}
    ]
    assert parsed["ingredients_structured"][0]["display_text"] == "1 cup pecans"


def test_parse_pasted_recipe_text_normalizes_markdown_bullets_and_numbered_steps():
    raw_text = """
    # Skillet Eggs
    Servings: 2

    ## Ingredients
    - 2 eggs
    * 1 tbsp butter

    ## Instructions
    1. Heat butter in a skillet.
    2) Add eggs and cook to preference.
    3 - Serve warm.
    """

    parsed = main._parse_pasted_recipe_text(raw_text)

    assert parsed["title"] == "Skillet Eggs"
    assert parsed["ingredients"] == ["2 eggs", "1 tbsp butter"]
    assert parsed["instructions"] == [
        "Heat butter in a skillet.",
        "Add eggs and cook to preference.",
        "Serve warm.",
    ]
    assert parsed["ingredient_groups"] == [{"title": "", "items": ["2 eggs", "1 tbsp butter"]}]
    assert parsed["instruction_groups"] == [
        {
            "title": "Instructions",
            "steps": [
                "Heat butter in a skillet.",
                "Add eggs and cook to preference.",
                "Serve warm.",
            ],
        }
    ]


def test_parse_pasted_recipe_text_preserves_description_and_moves_terminal_notes_out_of_instructions():
    raw_text = """
    Creamy Tomato Pasta
    A quick weeknight pasta with a silky tomato cream sauce.
    Great with extra basil on top.

    Ingredients
    8 oz pasta
    1 cup tomato sauce

    Instructions
    1. Boil the pasta.
    2. Stir in the sauce.

    Notes
    Reserve some pasta water if the sauce gets too thick.
    """

    parsed = main._parse_pasted_recipe_text(raw_text)

    assert parsed["notes"] == (
        "A quick weeknight pasta with a silky tomato cream sauce.\n"
        "Great with extra basil on top.\n\n"
        "Notes:\n"
        "Reserve some pasta water if the sauce gets too thick."
    )
    assert parsed["instructions"] == ["Boil the pasta.", "Stir in the sauce."]


def test_parse_pasted_recipe_text_preserves_tip_sections_as_notes():
    raw_text = """
    Herb Rice

    Ingredients
    1 cup rice
    2 cups water

    Instructions
    Cook until tender.

    Tips
    Fluff with a fork before serving.
    """

    parsed = main._parse_pasted_recipe_text(raw_text)

    assert parsed["notes"] == "Tips:\nFluff with a fork before serving."
    assert parsed["instructions"] == ["Cook until tender."]


def test_parse_pasted_recipe_text_detects_ingredient_section_headings_for_jambalaya():
    raw_text, expected = _load_paste_text_fixture()

    parsed = main._parse_pasted_recipe_text(raw_text)

    assert parsed["title"] == expected["title"]
    assert parsed["servings"] == expected["servings"]
    assert parsed["prep_time"] == expected["prep_time"]
    assert parsed["cook_time"] == expected["cook_time"]
    assert parsed["notes"] == expected["notes"]
    assert parsed["ingredient_groups"] == expected["ingredient_groups"]
    assert parsed["ingredients"] == expected["ingredients"]
    assert parsed["instruction_groups"] == expected["instruction_groups"]
    assert parsed["instructions"] == expected["instructions"]
    assert parsed["title"].startswith("House ")
    assert "Chef's Notes:" in parsed["notes"]
    assert parsed["instructions"][0] == "Brown the sausage in a Dutch oven; transfer to a bowl."
    assert all(not ingredient.endswith(":") for ingredient in parsed["ingredients"])
    assert [group["title"] for group in parsed["ingredient_groups"]] == [
        "Meat",
        "For the Chicken",
        "Vegetables",
        "Pantry",
        "Seasonings",
        "For the Pot",
        "Optional Finishers",
    ]
    assert "Seasonings" not in parsed["ingredients"]
    assert "For the Chicken" not in parsed["ingredients"]
    assert "For the Pot" not in parsed["ingredients"]


def test_parse_pasted_recipe_text_does_not_treat_legitimate_short_ingredients_as_section_headings():
    raw_text = """
    Seasoned Rice

    Ingredients
    Kosher Salt
    Black Pepper
    1 cup rice

    Instructions
    Stir everything together.
    """

    parsed = main._parse_pasted_recipe_text(raw_text)

    assert parsed["ingredient_groups"] == [
        {"title": "", "items": ["Kosher Salt", "Black Pepper", "1 cup rice"]},
    ]
    assert parsed["ingredients"] == ["Kosher Salt", "Black Pepper", "1 cup rice"]


def test_import_text_endpoint_returns_parsed_payload():
    client = TestClient(main.app)
    main.app.dependency_overrides[main.require_user] = lambda: {"id": 1}
    try:
        response = client.post(
            "/import/text",
            json={
                "text": "Toast\nIngredients\n1 cup pecans\nInstructions\nToast pecans until fragrant."
            },
        )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Toast"
    assert payload["content_source"] == "pasted_text"
    assert payload["source_type"] == "Paste Text"
    assert payload["ingredients"] == ["1 cup pecans"]
    assert payload["instructions"] == ["Toast pecans until fragrant."]


def test_import_text_endpoint_returns_notes_payload():
    client = TestClient(main.app)
    main.app.dependency_overrides[main.require_user] = lambda: {"id": 1}
    try:
        response = client.post(
            "/import/text",
            json={
                "text": (
                    "Simple Soup\n"
                    "A warm starter for cold nights.\n\n"
                    "Ingredients\n"
                    "1 cup broth\n\n"
                    "Instructions\n"
                    "Heat and serve.\n\n"
                    "Notes\n"
                    "Add parsley before serving."
                )
            },
        )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["notes"] == (
        "A warm starter for cold nights.\n\n"
        "Notes:\n"
        "Add parsley before serving."
    )


def test_pasted_recipe_notes_persist_through_recipe_save_and_reload(monkeypatch):
    db_path = "pytest-cache-files-codex-temp/paste-notes-persistence-test.db"
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    if os.path.exists(db_path):
        os.remove(db_path)
    monkeypatch.setattr(main, "DB", db_path)
    main.init_db()
    conn = main.get_conn()
    conn.execute(
        "INSERT INTO users (id, email, password_hash, is_admin, is_active, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (1, "cook@example.com", "hash", 0, 1, main.utcnow_iso()),
    )
    conn.commit()
    conn.close()

    raw_text, expected = _load_paste_text_fixture()
    parsed = main._parse_pasted_recipe_text(raw_text)

    client = TestClient(main.app)
    main.app.dependency_overrides[main.require_user] = lambda: {"id": 1}
    try:
        create_response = client.post(
            "/recipes",
            json={
                "title": parsed["title"],
                "url": "",
                "original_source_url": None,
                "resolved_recipe_url": None,
                "content_source": "pasted_text",
                "image_url": "",
                "source_app": "Paste",
                "source_type": "Paste Text",
                "notes": parsed["notes"],
                "tags": "",
                "needs_review": False,
                "review_status": "none",
                "servings": parsed["servings"],
                "prep_time": parsed["prep_time"],
                "cook_time": parsed["cook_time"],
                "total_time": parsed.get("total_time", ""),
                "prep_minutes": parsed.get("prep_minutes"),
                "cook_minutes": parsed.get("cook_minutes"),
                "total_minutes": parsed.get("total_minutes"),
                "ingredients": parsed["ingredients"],
                "instructions": parsed["instructions"],
                "ingredient_groups": parsed["ingredient_groups"],
                "instruction_groups": parsed["instruction_groups"],
            },
        )
        list_response = client.get("/recipes")
    finally:
        main.app.dependency_overrides.clear()

    assert create_response.status_code == 200
    assert list_response.status_code == 200
    recipes = list_response.json()
    assert len(recipes) == 1
    assert recipes[0]["title"] == expected["title"]
    assert recipes[0]["notes"] == expected["notes"]
    assert recipes[0]["ingredient_groups"] == expected["ingredient_groups"]
    assert recipes[0]["ingredients"] == expected["ingredients"]
    assert recipes[0]["instructions"] == expected["instructions"]


def test_shopping_list_endpoint_combines_selected_recipe_ingredients(monkeypatch):
    db_path = "pytest-cache-files-codex-temp/shopping-list-test.db"
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    if os.path.exists(db_path):
        os.remove(db_path)
    monkeypatch.setattr(main, "DB", db_path)
    main.init_db()
    conn = main.get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (id, email, password_hash, is_admin, is_active, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (1, "cook@example.com", "hash", 0, 1, main.utcnow_iso()),
    )
    for title, ingredients in (
        ("Cake", ["1 cup chopped pecans", "salt to taste"]),
        ("Topping", ["1/2 cup pecans", "2 tbsp butter"]),
    ):
        cur.execute(
            """
            INSERT INTO recipes (
                user_id, title, url, ingredients, instructions, ingredient_groups, instruction_groups
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                title,
                "",
                main._json_array_to_text(ingredients),
                main._json_array_to_text(["Mix."]),
                main._json_groups_to_text([{"title": "", "items": ingredients}], "items"),
                main._json_groups_to_text([{"title": "", "steps": ["Mix."]}], "steps"),
            ),
        )
    conn.commit()
    conn.close()

    client = TestClient(main.app)
    main.app.dependency_overrides[main.require_user] = lambda: {"id": 1}
    try:
        response = client.post("/shopping-list", json={"recipe_ids": [1, 2]})
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 200
    items = response.json()["items"]
    pecans = next(item for item in items if item["name"] == "pecans")
    salt = next(item for item in items if item["name"] == "salt to taste")
    assert pecans["quantity"] == 1.5
    assert pecans["unit"] == "cup"
    assert pecans["display_text"] == "1 1/2 cups pecans"
    assert len(pecans["items"]) == 2
    assert salt["quantity"] is None
    assert salt["display_text"] == "salt to taste"


def test_grocery_list_persists_items_and_checked_state(monkeypatch):
    db_path = "pytest-cache-files-codex-temp/grocery-list-test.db"
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    if os.path.exists(db_path):
        os.remove(db_path)
    monkeypatch.setattr(main, "DB", db_path)
    main.init_db()
    conn = main.get_conn()
    conn.execute(
        "INSERT INTO users (id, email, password_hash, is_admin, is_active, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (1, "cook@example.com", "hash", 0, 1, main.utcnow_iso()),
    )
    conn.execute(
        """
        INSERT INTO recipes (id, user_id, title, url, ingredients, instructions)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (10, 1, "Cake", "", main._json_array_to_text(["1 cup pecans"]), main._json_array_to_text(["Mix."])),
    )
    conn.commit()
    conn.close()

    client = TestClient(main.app)
    main.app.dependency_overrides[main.require_user] = lambda: {"id": 1}
    try:
        add_response = client.post(
            "/grocery-list/items",
            json={
                "items": [
                    {
                        "name": "pecans",
                        "quantity": 1,
                        "unit": "cup",
                        "display_text": "1 cup pecans",
                        "source_recipe_id": 10,
                        "source_recipe_title": "Cake",
                    }
                ]
            },
        )
        list_response = client.get("/grocery-list")
        item_id = list_response.json()["active_items"][0]["id"]
        patch_response = client.patch(f"/grocery-list/items/{item_id}", json={"checked": True})
        checked_response = client.get("/grocery-list")
    finally:
        main.app.dependency_overrides.clear()

    assert add_response.status_code == 200
    assert patch_response.status_code == 200
    assert checked_response.status_code == 200
    payload = checked_response.json()
    assert payload["active_items"] == []
    assert payload["checked_items"][0]["display_text"] == "1 cup pecans"
    assert payload["checked_items"][0]["checked"] is True
    assert payload["sources"] == [{"id": 10, "title": "Cake"}]


def test_grocery_list_can_clear_checked_and_remove_source(monkeypatch):
    db_path = "pytest-cache-files-codex-temp/grocery-list-source-test.db"
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    if os.path.exists(db_path):
        os.remove(db_path)
    monkeypatch.setattr(main, "DB", db_path)
    main.init_db()
    conn = main.get_conn()
    conn.execute(
        "INSERT INTO users (id, email, password_hash, is_admin, is_active, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (1, "cook@example.com", "hash", 0, 1, main.utcnow_iso()),
    )
    conn.commit()
    conn.close()

    client = TestClient(main.app)
    main.app.dependency_overrides[main.require_user] = lambda: {"id": 1}
    try:
        client.post(
            "/grocery-list/items",
            json={
                "items": [
                    {"name": "pecans", "display_text": "pecans", "source_recipe_id": 1, "source_recipe_title": "Cake"},
                    {"name": "milk", "display_text": "milk", "source_recipe_id": 2, "source_recipe_title": "Milk"},
                ]
            },
        )
        items = client.get("/grocery-list").json()["active_items"]
        client.patch(f"/grocery-list/items/{items[0]['id']}", json={"checked": True})
        clear_response = client.delete("/grocery-list/checked")
        remove_response = client.delete("/grocery-list/source/2")
        final_response = client.get("/grocery-list")
    finally:
        main.app.dependency_overrides.clear()

    assert clear_response.status_code == 200
    assert remove_response.status_code == 200
    final_payload = final_response.json()
    assert final_payload["active_items"] == []
    assert final_payload["checked_items"] == []
