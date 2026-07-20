import json
from pathlib import Path
from unittest.mock import patch

from backend.app import main


FIXTURE_ROOT = Path(__file__).parent / "fixtures"
GOOD_FIXTURES = [
    "sugarspunrun_best_cheesecake",
    "allrecipes_lemon_pepper_chicken",
    "thecountrycook_crock_pot_beef_stroganoff",
    "plantbasedfolk_cherry_tomato_spaghetti_sauce",
    "thecookierookie_cucumber_sandwiches",
]


def _load_fixture(fixture_name: str) -> tuple[str, dict, dict]:
    fixture_dir = FIXTURE_ROOT / fixture_name
    html = (fixture_dir / "page.html").read_text(encoding="utf-8")
    parser_expected = json.loads((fixture_dir / "parser_expected.json").read_text(encoding="utf-8"))
    final_expected = json.loads((fixture_dir / "final_expected.json").read_text(encoding="utf-8"))
    return html, parser_expected, final_expected


def _build_final_payload(url: str, parser_result: dict) -> dict:
    source_app, source_type = main.infer_source(url)
    return {
        "url": url,
        "title": parser_result.get("title", ""),
        "source_app": source_app,
        "source_type": source_type,
        "image_url": parser_result.get("image_url", ""),
        "ingredients": parser_result.get("ingredients", []),
        "instructions": parser_result.get("instructions", []),
        "ingredient_groups": parser_result.get("ingredient_groups", []),
        "instruction_groups": parser_result.get("instruction_groups", []),
        "servings": parser_result.get("servings", ""),
        "prep_time": parser_result.get("prep_time", ""),
        "cook_time": parser_result.get("cook_time", ""),
        "total_time": parser_result.get("total_time", ""),
        "prep_minutes": parser_result.get("prep_minutes"),
        "cook_minutes": parser_result.get("cook_minutes"),
        "total_minutes": parser_result.get("total_minutes"),
        "needs_review": False,
    }


def _assert_parser_payload_matches_fixture(actual: dict, expected: dict) -> None:
    for key, value in expected.items():
        assert actual.get(key) == value

    assert isinstance(actual.get("ingredients_structured"), list)
    assert len(actual.get("ingredients_structured") or []) == len(expected.get("ingredients") or [])


class _MockHtmlResponse:
    def __init__(self, html: str):
        self.text = html
        self.headers = {"Content-Type": "text/html; charset=utf-8"}

    def raise_for_status(self):
        return None


def test_good_fixture_pipeline_regression_cases():
    for fixture_name in GOOD_FIXTURES:
        html, parser_expected, final_expected = _load_fixture(fixture_name)
        url = final_expected["url"]

        with patch("backend.app.main.call_ollama_review") as ollama_mock, patch(
            "backend.app.main.requests.get", return_value=_MockHtmlResponse(html)
        ):
            parser_result = main.fetch_recipe_data_from_url(url)
            _assert_parser_payload_matches_fixture(parser_result, parser_expected)
            assert parser_result.get("_selected_source") == "jsonld"
            assert parser_result.get("title") == final_expected.get("title")

            ingredients = parser_result.get("ingredients") or []
            instructions = parser_result.get("instructions") or []
            expected_ingredients = final_expected.get("ingredients") or []
            expected_instructions = final_expected.get("instructions") or []
            assert ingredients
            assert instructions
            assert len(ingredients) == len(expected_ingredients)
            assert len(instructions) == len(expected_instructions)

            junk_snippets = [
                "newsletter",
                "sign up",
                "share",
                "recipe index",
                "affiliate",
                "comments",
            ]
            combined_text = "\n".join([*ingredients, *instructions]).lower()
            for snippet in junk_snippets:
                assert snippet not in combined_text

            assert final_expected.get("needs_review") is False

            final_payload = _build_final_payload(url, parser_result)
            assert final_payload == final_expected
            ollama_mock.assert_not_called()
