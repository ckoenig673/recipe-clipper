from backend.app.main import (
    _build_shopping_list_items,
    _finalize_recipe_candidate,
    _group_ingredients_with_totals,
    _group_ingredients_by_name,
    _normalize_ingredient_name,
    _parse_ingredient_struct,
    _scale_ingredient,
    _scale_ingredients_list,
    _sum_quantities_for_same_unit,
)
import time


def test_parse_ingredient_struct_fraction():
    parsed = _parse_ingredient_struct("1/2 cup sour cream")
    assert parsed["raw"] == "1/2 cup sour cream"
    assert parsed["quantity"] == 0.5
    assert parsed["unit"] == "cup"
    assert parsed["name"] == "sour cream"
    assert parsed["note"] is None
    assert parsed["display_quantity"] == "1/2"
    assert parsed["display_unit"] == "cup"
    assert parsed["display_name"] == "sour cream"
    assert parsed["display_text"] == "1/2 cup sour cream"


def test_parse_ingredient_struct_mixed_fraction():
    parsed = _parse_ingredient_struct("1 1/2 cups milk")
    assert parsed["quantity"] == 1.5
    assert parsed["unit"] == "cup"
    assert parsed["name"] == "milk"


def test_parse_ingredient_struct_unicode_fraction():
    parsed = _parse_ingredient_struct("½ cup sour cream")
    assert parsed["quantity"] == 0.5
    assert parsed["unit"] == "cup"
    assert parsed["name"] == "sour cream"


def test_parse_ingredient_struct_unicode_mixed_fraction_attached():
    parsed = _parse_ingredient_struct("1½ cups milk")
    assert parsed["quantity"] == 1.5
    assert parsed["unit"] == "cup"
    assert parsed["name"] == "milk"


def test_parse_ingredient_struct_unicode_mixed_fraction_spaced():
    parsed = _parse_ingredient_struct("1 ½ cups milk")
    assert parsed["quantity"] == 1.5
    assert parsed["unit"] == "cup"
    assert parsed["name"] == "milk"


def test_parse_ingredient_struct_unicode_mixed_fraction_quarter():
    parsed = _parse_ingredient_struct("1¼ cups sugar")
    assert parsed["quantity"] == 1.25
    assert parsed["unit"] == "cup"
    assert parsed["name"] == "sugar"
    assert parsed["display_text"] == "1 1/4 cups sugar"


def test_parse_ingredient_struct_unicode_quarter():
    parsed = _parse_ingredient_struct("¼ teaspoon cinnamon")
    assert parsed["quantity"] == 0.25
    assert parsed["unit"] == "teaspoon"
    assert parsed["name"] == "cinnamon"


def test_parse_ingredient_struct_tablespoon():
    parsed = _parse_ingredient_struct("2 tablespoons butter")
    assert parsed["quantity"] == 2.0
    assert parsed["unit"] == "tablespoon"
    assert parsed["name"] == "butter"
    assert parsed["display_quantity"] == "2"
    assert parsed["display_unit"] == "tablespoons"
    assert parsed["display_text"] == "2 tablespoons butter"


def test_parse_ingredient_struct_package_with_note():
    parsed = _parse_ingredient_struct("1 package (9 ounces) yellow cake mix without pudding in the mix")
    assert parsed["quantity"] == 1.0
    assert parsed["unit"] == "package"
    assert parsed["name"] == "yellow cake mix without pudding in the mix"
    assert parsed["note"] == "9 ounces"
    assert parsed["display_quantity"] == "1"
    assert parsed["display_unit"] == "package"
    assert parsed["display_text"] == "1 package yellow cake mix without pudding in the mix (9 ounces)"


def test_parse_ingredient_struct_fallback_for_non_numeric():
    parsed = _parse_ingredient_struct("salt to taste")
    assert parsed["quantity"] is None
    assert parsed["unit"] is None
    assert parsed["name"] == "salt to taste"
    assert parsed["display_quantity"] is None
    assert parsed["display_unit"] is None
    assert parsed["display_text"] == "salt to taste"


def test_parse_ingredient_struct_one_and_half_cups_display():
    parsed = _parse_ingredient_struct("1 1/2 cups milk")
    assert parsed["display_quantity"] == "1 1/2"
    assert parsed["display_unit"] == "cups"
    assert parsed["display_text"] == "1 1/2 cups milk"


def test_parse_ingredient_struct_ocr_quantity_correction():
    parsed = _parse_ingredient_struct("14 cups sugar")
    assert parsed["quantity"] == 1.25
    assert parsed["display_text"] == "1 1/4 cups sugar"


def test_parse_ingredient_struct_preserves_optional_ingredient_without_quantity():
    parsed = _parse_ingredient_struct("Melted chocolate (optional, see Tip)")
    assert parsed["quantity"] is None
    assert parsed["unit"] is None
    assert parsed["name"] == "Melted chocolate"
    assert parsed["note"] == "optional, see Tip"
    assert parsed["display_text"] == "Melted chocolate (optional, see Tip)"


def test_parse_ingredient_struct_prefers_parenthetical_stick_for_suspicious_cup_quantity():
    parsed = _parse_ingredient_struct("1/3 cup (1 stick) butter")
    assert parsed["quantity"] == 0.5
    assert parsed["unit"] == "cup"
    assert parsed["name"] == "butter"
    assert parsed["note"] == "1 stick"
    assert parsed["display_text"] == "1/2 cup butter (1 stick)"


def test_parse_ingredient_struct_does_not_override_package_with_ounces_note():
    parsed = _parse_ingredient_struct("1 package (8 ounces) cream cheese")
    assert parsed["quantity"] == 1.0
    assert parsed["unit"] == "package"
    assert parsed["name"] == "cream cheese"
    assert parsed["note"] == "8 ounces"
    assert parsed["display_text"] == "1 package cream cheese (8 ounces)"


def test_parse_ingredient_struct_does_not_override_optional_note():
    parsed = _parse_ingredient_struct("1 cup sugar (optional)")
    assert parsed["quantity"] == 1.0
    assert parsed["unit"] == "cup"
    assert parsed["name"] == "sugar"
    assert parsed["note"] == "optional"
    assert parsed["display_text"] == "1 cup sugar (optional)"


def test_parse_ingredient_struct_keeps_main_quantity_when_parenthetical_tablespoons_are_not_high_confidence_override():
    parsed = _parse_ingredient_struct("1/4 cup (2 tablespoons) butter")
    assert parsed["quantity"] == 0.25
    assert parsed["unit"] == "cup"
    assert parsed["name"] == "butter"
    assert parsed["note"] == "2 tablespoons"
    assert parsed["display_text"] == "1/4 cup butter (2 tablespoons)"


def test_parse_ingredient_struct_handles_long_parenthetical_note_quickly():
    raw = "1 cup sugar (" + ("optional " * 2000) + ")"

    started = time.perf_counter()
    parsed = _parse_ingredient_struct(raw)
    elapsed = time.perf_counter() - started

    assert elapsed < 1.0
    assert parsed["quantity"] == 1.0
    assert parsed["unit"] == "cup"
    assert parsed["name"] == "sugar"
    assert parsed["note"].startswith("optional")


def test_normalize_ingredient_name_removes_leading_descriptors():
    assert _normalize_ingredient_name("chopped pecans") == "pecans"
    assert _normalize_ingredient_name("fresh basil") == "basil"
    assert _normalize_ingredient_name("minced garlic") == "garlic"
    assert _normalize_ingredient_name("softened butter") == "butter"
    assert _normalize_ingredient_name("packed brown sugar") == "brown sugar"
    assert _normalize_ingredient_name("diced tomatoes") == "tomato"
    assert _normalize_ingredient_name("sliced mushrooms") == "mushrooms"


def test_normalize_ingredient_name_removes_trailing_descriptors():
    assert _normalize_ingredient_name("fresh basil leaves") == "basil"
    assert _normalize_ingredient_name("minced garlic cloves") == "garlic"
    assert _normalize_ingredient_name("chopped pecan pieces") == "pecans"


def test_group_ingredients_by_name_merges_descriptor_and_plain_forms():
    ingredients_structured = [
        {"name": "chopped pecans", "quantity": 1.0, "unit": "cup"},
        {"name": "pecans", "quantity": 0.5, "unit": "cup"},
        {"name": "butter", "quantity": 2.0, "unit": "tablespoon"},
    ]

    grouped = _group_ingredients_by_name(ingredients_structured)

    assert set(grouped.keys()) == {"pecans", "butter"}
    assert len(grouped["pecans"]) == 2
    assert len(grouped["butter"]) == 1


def test_sum_quantities_for_same_unit_returns_total_for_matching_units():
    group = [
        {"name": "butter", "quantity": 1.0, "unit": "cup"},
        {"name": "butter", "quantity": 0.5, "unit": "cup"},
        {"name": "butter", "quantity": None, "unit": "cup"},
    ]

    total = _sum_quantities_for_same_unit(group)

    assert total == 1.5


def test_sum_quantities_for_same_unit_returns_none_when_units_differ():
    group = [
        {"name": "sugar", "quantity": 1.0, "unit": "cup"},
        {"name": "sugar", "quantity": 2.0, "unit": "tablespoon"},
    ]

    total = _sum_quantities_for_same_unit(group)

    assert total is None


def test_group_ingredients_with_totals_groups_by_normalized_name_and_sums_matching_units():
    ingredients_structured = [
        {"name": "butter", "quantity": 1, "unit": "tbsp"},
        {"name": "butter", "quantity": 2, "unit": "tbsp"},
        {"name": "sugar", "quantity": 1, "unit": "cup"},
    ]

    grouped = _group_ingredients_with_totals(ingredients_structured)

    assert grouped == {
        "butter": {
            "total": 3.0,
            "unit": "tbsp",
            "items": [
                {"name": "butter", "quantity": 1, "unit": "tbsp"},
                {"name": "butter", "quantity": 2, "unit": "tbsp"},
            ],
        },
        "sugar": {
            "total": 1.0,
            "unit": "cup",
            "items": [
                {"name": "sugar", "quantity": 1, "unit": "cup"},
            ],
        },
    }


def test_group_ingredients_with_totals_uses_normalized_names():
    ingredients_structured = [
        {"name": "chopped pecans", "quantity": 1, "unit": "cup"},
        {"name": "pecans", "quantity": 0.5, "unit": "cup"},
    ]

    grouped = _group_ingredients_with_totals(ingredients_structured)

    assert set(grouped.keys()) == {"pecans"}
    assert grouped["pecans"]["total"] == 1.5
    assert grouped["pecans"]["unit"] == "cup"
    assert grouped["pecans"]["items"] == ingredients_structured


def test_group_ingredients_with_totals_sets_none_total_when_units_differ():
    ingredients_structured = [
        {"name": "sugar", "quantity": 1, "unit": "cup"},
        {"name": "sugar", "quantity": 2, "unit": "tablespoon"},
    ]

    grouped = _group_ingredients_with_totals(ingredients_structured)

    assert grouped["sugar"]["total"] is None
    assert grouped["sugar"]["unit"] is None
    assert grouped["sugar"]["items"] == ingredients_structured


def test_group_ingredients_with_totals_ignores_none_quantities_when_summing():
    ingredients_structured = [
        {"name": "butter", "quantity": None, "unit": "tbsp"},
        {"name": "butter", "quantity": 2, "unit": "tbsp"},
    ]

    grouped = _group_ingredients_with_totals(ingredients_structured)

    assert grouped["butter"]["total"] == 2.0
    assert grouped["butter"]["unit"] == "tbsp"


def test_build_shopping_list_items_combines_same_normalized_ingredient_and_unit():
    ingredients_structured = [
        {"name": "pecans", "quantity": 1, "unit": "cup", "display_text": "1 cup pecans"},
        {"name": "pecans", "quantity": 0.5, "unit": "cup", "display_text": "1/2 cup pecans"},
    ]

    shopping_items = _build_shopping_list_items(ingredients_structured)

    assert shopping_items == [
        {
            "name": "pecans",
            "quantity": 1.5,
            "unit": "cup",
            "display_text": "1 1/2 cups pecans",
            "items": ingredients_structured,
        }
    ]


def test_build_shopping_list_items_groups_descriptor_forms_together():
    ingredients_structured = [
        {"name": "chopped pecans", "quantity": 1, "unit": "cup", "display_text": "1 cup chopped pecans"},
        {"name": "pecans", "quantity": 0.5, "unit": "cup", "display_text": "1/2 cup pecans"},
    ]

    shopping_items = _build_shopping_list_items(ingredients_structured)

    assert len(shopping_items) == 1
    assert shopping_items[0]["name"] == "pecans"
    assert shopping_items[0]["quantity"] == 1.5
    assert shopping_items[0]["unit"] == "cup"
    assert shopping_items[0]["items"] == ingredients_structured


def test_build_shopping_list_items_mixed_units_do_not_combine():
    ingredients_structured = [
        {"name": "sugar", "quantity": 1, "unit": "cup", "display_text": "1 cup sugar"},
        {"name": "sugar", "quantity": 2, "unit": "tablespoon", "display_text": "2 tablespoons sugar"},
    ]

    shopping_items = _build_shopping_list_items(ingredients_structured)

    assert shopping_items == [
        {
            "name": "sugar",
            "quantity": None,
            "unit": None,
            "display_text": "sugar",
            "items": ingredients_structured,
        }
    ]


def test_build_shopping_list_items_preserves_quantity_none_item():
    ingredients_structured = [
        {"name": "salt to taste", "quantity": None, "unit": None, "display_text": "salt to taste"},
    ]

    shopping_items = _build_shopping_list_items(ingredients_structured)

    assert shopping_items == [
        {
            "name": "salt to taste",
            "quantity": None,
            "unit": None,
            "display_text": "salt to taste",
            "items": ingredients_structured,
        }
    ]


def test_build_shopping_list_items_builds_display_text_from_summed_fields():
    ingredients_structured = [
        {"name": "milk", "quantity": 1, "unit": "cup", "display_text": "1 cup milk"},
        {"name": "milk", "quantity": 0.25, "unit": "cup", "display_text": "1/4 cup milk"},
    ]

    shopping_items = _build_shopping_list_items(ingredients_structured)

    assert shopping_items[0]["display_text"] == "1 1/4 cups milk"


def test_finalize_recipe_candidate_preserves_string_ingredients_and_adds_structured():
    finalized = _finalize_recipe_candidate(
        {"ingredients": ["1/2 cup sour cream", "salt to taste"], "instructions": ["mix"]},
        "https://example.com/recipe",
        "unit-test",
    )
    assert finalized["ingredients"] == ["1/2 cup sour cream", "salt to taste"]
    assert finalized["ingredients_structured"] == [
        {
            "raw": "1/2 cup sour cream",
            "quantity": 0.5,
            "unit": "cup",
            "name": "sour cream",
            "note": None,
            "display_quantity": "1/2",
            "display_unit": "cup",
            "display_name": "sour cream",
            "display_text": "1/2 cup sour cream",
        },
        {
            "raw": "salt to taste",
            "quantity": None,
            "unit": None,
            "name": "salt to taste",
            "note": None,
            "display_quantity": None,
            "display_unit": None,
            "display_name": "salt to taste",
            "display_text": "salt to taste",
        },
    ]


def test_scale_ingredient_doubles_half_cup_to_one_cup():
    parsed = _parse_ingredient_struct("1/2 cup sour cream")
    scaled = _scale_ingredient(parsed, 2)

    assert scaled["quantity"] == 1.0
    assert scaled["unit"] == "cup"
    assert scaled["name"] == "sour cream"
    assert scaled["display_quantity"] == "1"
    assert scaled["display_unit"] == "cup"
    assert scaled["display_text"] == "1 cup sour cream"


def test_scale_ingredient_halves_one_cup_to_half_cup():
    parsed = _parse_ingredient_struct("1 cup sugar")
    scaled = _scale_ingredient(parsed, 0.5)

    assert scaled["quantity"] == 0.5
    assert scaled["unit"] == "cup"
    assert scaled["name"] == "sugar"
    assert scaled["display_quantity"] == "1/2"
    assert scaled["display_unit"] == "cup"
    assert scaled["display_text"] == "1/2 cup sugar"


def test_scale_ingredient_keeps_none_quantity_unchanged():
    parsed = _parse_ingredient_struct("salt to taste")
    scaled = _scale_ingredient(parsed, 3)

    assert scaled["quantity"] is None
    assert scaled["unit"] is None
    assert scaled["name"] == "salt to taste"
    assert scaled["display_text"] == "salt to taste"


def test_scale_ingredients_list_scales_each_entry_and_updates_display_text():
    ingredients_structured = [
        _parse_ingredient_struct("1/2 cup sour cream"),
        _parse_ingredient_struct("salt to taste"),
    ]

    scaled = _scale_ingredients_list(ingredients_structured, 2)

    assert len(scaled) == 2
    assert scaled[0]["quantity"] == 1.0
    assert scaled[0]["display_text"] == "1 cup sour cream"
    assert scaled[1]["quantity"] is None
    assert scaled[1]["display_text"] == "salt to taste"
