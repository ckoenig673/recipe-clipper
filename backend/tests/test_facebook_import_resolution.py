import json
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app import main
from backend.app.social_resolver import SocialResolutionResult
from backend.app.social_video_pipeline import TranscriptPipelineResult, YtDlpExtractError


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "facebook_watch_1736159050691633"


class _MockHtmlResponse:
    def __init__(self, html: str):
        self.text = html
        self.headers = {"Content-Type": "text/html; charset=utf-8"}

    def raise_for_status(self):
        return None


def _load_fixture_data() -> dict:
    input_url = (FIXTURE_DIR / "input_url.txt").read_text(encoding="utf-8").strip()
    resolved_url = (FIXTURE_DIR / "resolved_recipe_url.txt").read_text(encoding="utf-8").strip()
    resolver_expected = json.loads((FIXTURE_DIR / "resolver_expected.json").read_text(encoding="utf-8"))
    parser_expected = json.loads((FIXTURE_DIR / "parser_expected.json").read_text(encoding="utf-8"))
    final_expected = json.loads((FIXTURE_DIR / "final_expected.json").read_text(encoding="utf-8"))
    html = (FIXTURE_DIR / "page.html").read_text(encoding="utf-8")
    return {
        "input_url": input_url,
        "resolved_url": resolved_url,
        "resolver_expected": resolver_expected,
        "parser_expected": parser_expected,
        "final_expected": final_expected,
        "html": html,
    }


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


def test_facebook_watch_import_resolution_pipeline_uses_saved_fixture_and_no_live_network():
    fixture = _load_fixture_data()

    mocked_resolution = SocialResolutionResult(
        source="facebook",
        canonical_url="https://www.facebook.com/reel/1736159050691633",
        resolved_url=fixture["resolved_url"],
        method=fixture["resolver_expected"]["resolution_method"],
        post_id="1736159050691633",
        error=None,
        headless_attempted=False,
        headless_candidate_urls=[],
        fast_path_candidate_urls=[fixture["resolved_url"]],
    )

    with patch("backend.app.main.resolve_social_url", return_value=mocked_resolution) as mock_social_resolve, patch(
        "backend.app.main.resolve_url", side_effect=lambda value: value
    ) as mock_resolve_url, patch("backend.app.main.safe_get", return_value=_MockHtmlResponse(fixture["html"])) as mock_safe_get:
        resolution_actual = {
            "input_url": fixture["input_url"],
            "resolved_url": mocked_resolution.resolved_url,
            "resolution_method": mocked_resolution.method,
            "status": "resolved" if mocked_resolution.resolved_url else "unresolved",
        }
        assert resolution_actual == fixture["resolver_expected"]

        parser_actual = main.fetch_recipe_data_from_url(fixture["resolved_url"])
        _assert_parser_payload_matches_fixture(parser_actual, fixture["parser_expected"])

        final_actual = _build_final_payload(fixture["resolved_url"], parser_actual)
        assert final_actual == fixture["final_expected"]

        social_extract_payload = main.extract_metadata(url=fixture["input_url"], _={})
        mock_social_resolve.assert_called_once_with(fixture["input_url"])
        assert mock_resolve_url.called
        assert mock_safe_get.called
        assert social_extract_payload["url"] == fixture["resolved_url"]
        assert social_extract_payload["title"] == fixture["final_expected"]["title"]
        assert social_extract_payload["ingredients"] == fixture["final_expected"]["ingredients"]
        assert social_extract_payload["instructions"] == fixture["final_expected"]["instructions"]


def test_social_recovery_prefers_validated_recovered_recipe_url_over_caption_fallback():
    social_url = "https://www.facebook.com/share/v/1CpgHJDPep/"
    recovered_url = "https://sugargeekshow.com/braised-beef-short-ribs/"
    recovered_html = """
    <html>
      <head>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "Recipe",
          "name": "Braised Beef Short Ribs",
          "recipeIngredient": ["3 lb short ribs", "1 tsp salt"],
          "recipeInstructions": ["Season the ribs", "Braise until tender"]
        }
        </script>
      </head>
      <body><h1>Braised Beef Short Ribs</h1></body>
    </html>
    """
    mocked_resolution = SocialResolutionResult(
        source="facebook",
        canonical_url="https://www.facebook.com/reel/1234567890123456",
        resolved_url=None,
        method="none",
        post_id="1234567890123456",
        error="facebook_external_url_not_found",
        headless_attempted=False,
        headless_candidate_urls=[],
        fast_path_candidate_urls=[],
        ytdlp_title="Braised Beef Short Ribs",
        ytdlp_description="Short-rib reel text transcript",
    )

    with patch("backend.app.main.resolve_social_url", return_value=mocked_resolution), patch(
        "backend.app.main._recover_recipe_url_from_social_signals",
        return_value=(recovered_url, "direct_slug"),
    ) as mock_recovery, patch(
        "backend.app.main.run_social_video_transcript_pipeline"
    ) as mock_transcript_pipeline, patch("backend.app.main.safe_get", return_value=_MockHtmlResponse(recovered_html)):
        payload = main.extract_metadata(url=social_url, _={})

    mock_recovery.assert_called_once()
    mock_transcript_pipeline.assert_not_called()
    assert payload["url"] == recovered_url
    assert payload["original_source_url"] == social_url
    assert payload["resolved_recipe_url"] == recovered_url
    assert payload["content_source"] == "resolved_recipe_url"
    assert payload["title"] == "Braised Beef Short Ribs"
    assert len(payload["ingredients"]) == 2
    assert len(payload["instructions"]) == 2


def test_extract_metadata_passes_authenticated_user_facebook_cookie_to_transcript_pipeline():
    social_url = "https://www.facebook.com/share/v/1CpgHJDPep/"
    mocked_resolution = SocialResolutionResult(
        source="facebook",
        canonical_url="https://www.facebook.com/reel/1234567890123456",
        resolved_url=None,
        method="none",
        post_id="1234567890123456",
        error="facebook_external_url_not_found",
        headless_attempted=False,
        headless_candidate_urls=[],
        fast_path_candidate_urls=[],
        ytdlp_title="",
        ytdlp_description="",
    )
    transcript_result = TranscriptPipelineResult(
        transcript_text="",
        cleaned_transcript_text="",
        structured_recipe={"title": "Test", "ingredients": ["1 egg"], "instructions": ["Cook"]},
        mentioned_websites=[],
        title_inferred=False,
        measurements_partial=False,
        success=True,
        fallback_reason="",
    )

    with patch("backend.app.main.resolve_social_url", return_value=mocked_resolution), patch(
        "backend.app.main._recover_recipe_url_from_social_signals",
        return_value=("", ""),
    ), patch("backend.app.main._get_user_facebook_cookie", return_value="COOKIE_DB_VALUE") as mock_cookie_getter, patch(
        "backend.app.main.run_social_video_transcript_pipeline",
        return_value=transcript_result,
    ) as mock_pipeline:
        payload = main.extract_metadata(url=social_url, current_user={"id": 42}, _={})

    mock_cookie_getter.assert_called_once_with(42)
    assert mock_pipeline.call_args.kwargs["facebook_cookie"] == "COOKIE_DB_VALUE"
    assert payload["title"] == "Test"


def test_extract_metadata_falls_back_to_cookie_free_transcript_pipeline_when_cookie_is_unreadable():
    social_url = "https://www.facebook.com/share/v/1CpgHJDPep/"
    mocked_resolution = SocialResolutionResult(
        source="facebook",
        canonical_url="https://www.facebook.com/reel/1234567890123456",
        resolved_url=None,
        method="none",
        post_id="1234567890123456",
        error="facebook_external_url_not_found",
        headless_attempted=False,
        headless_candidate_urls=[],
        fast_path_candidate_urls=[],
        ytdlp_title="",
        ytdlp_description="",
    )
    transcript_result = TranscriptPipelineResult(
        transcript_text="",
        cleaned_transcript_text="",
        structured_recipe={"title": "Test", "ingredients": ["1 egg"], "instructions": ["Cook"]},
        mentioned_websites=[],
        title_inferred=False,
        measurements_partial=False,
        success=True,
        fallback_reason="",
    )

    with patch("backend.app.main.resolve_social_url", return_value=mocked_resolution), patch(
        "backend.app.main._recover_recipe_url_from_social_signals",
        return_value=("", ""),
    ), patch(
        "backend.app.main._get_user_facebook_cookie",
        side_effect=main.UserSettingDecryptionError("facebook_cookie", "Facebook cookie"),
    ) as mock_cookie_getter, patch(
        "backend.app.main.run_social_video_transcript_pipeline",
        return_value=transcript_result,
    ) as mock_pipeline:
        payload = main.extract_metadata(url=social_url, current_user={"id": 42}, _={})

    mock_cookie_getter.assert_called_once_with(42)
    assert mock_pipeline.call_args.kwargs["facebook_cookie"] is None
    assert payload["title"] == "Test"
    assert "Delete or replace it in Import Settings" in payload["social_metadata"]["facebook_cookie_warning"]


def test_social_recovery_invalid_candidate_falls_back_to_transcript_caption():
    social_url = "https://www.facebook.com/share/v/1CpgHJDPep/"
    mocked_resolution = SocialResolutionResult(
        source="facebook",
        canonical_url="https://www.facebook.com/reel/1234567890123456",
        resolved_url=None,
        method="none",
        post_id="1234567890123456",
        error="facebook_external_url_not_found",
        headless_attempted=False,
        headless_candidate_urls=[],
        fast_path_candidate_urls=[],
        ytdlp_title="Fallback Ribs",
        ytdlp_description="Transcript contains recipe style content",
    )

    with patch("backend.app.main.resolve_social_url", return_value=mocked_resolution), patch(
        "backend.app.main._recover_recipe_url_from_social_signals",
        return_value=("https://example.com/not-a-recipe/", "direct_slug"),
    ), patch(
        "backend.app.main._validate_recipe_page_and_parse",
        return_value=(False, {}),
    ), patch(
        "backend.app.main.looks_like_recipe_text",
        return_value=True,
    ), patch(
        "backend.app.main.parse_social_caption_recipe",
        return_value={
            "title": "Transcript fallback title",
            "ingredients": ["1 cup stock"],
            "instructions": ["Simmer for 30 minutes"],
            "ingredient_groups": [{"title": "", "items": ["1 cup stock"]}],
            "instruction_groups": [{"title": "", "steps": ["Simmer for 30 minutes"]}],
            "servings": "",
            "prep_time": "",
            "cook_time": "",
            "total_time": "",
            "prep_minutes": None,
            "cook_minutes": None,
            "total_minutes": None,
        },
    ):
        payload = main.extract_metadata(url=social_url, _={})

    assert payload["url"] == social_url
    assert payload["original_source_url"] == social_url
    assert payload["resolved_recipe_url"] == ""
    assert payload["content_source"] == "transcript_ai_fallback"
    assert payload["title"] == "Transcript fallback title"


def test_social_resolver_exception_still_runs_recovery_and_transcript_fallback():
    social_url = "https://www.facebook.com/share/v/1CpgHJDPep/"
    with patch(
        "backend.app.main.resolve_social_url",
        side_effect=RuntimeError("resolver exploded"),
    ), patch(
        "backend.app.main._recover_recipe_url_from_social_signals",
        return_value=("", ""),
    ) as mock_recovery, patch(
        "backend.app.main.looks_like_recipe_text",
        return_value=False,
    ):
        payload = main.extract_metadata(url=social_url, _={})

    mock_recovery.assert_called_once()
    assert payload["status"] == "partial"
    assert payload["url"] == social_url
    assert payload["reason"] == "We couldn’t extract the shared link directly, and recovery attempts did not find a recipe."


def test_social_transcript_pipeline_returns_recipe_when_caption_not_recipe_like():
    social_url = "https://www.facebook.com/reel/1234567890123456"
    mocked_resolution = SocialResolutionResult(
        source="facebook",
        canonical_url=social_url,
        resolved_url=None,
        method="none",
        post_id="1234567890123456",
        error="facebook_external_url_not_found",
        headless_attempted=False,
        headless_candidate_urls=[],
        fast_path_candidate_urls=[],
        ytdlp_title="One Pan Chicken Rice",
        ytdlp_description="short caption",
    )
    transcript_result = TranscriptPipelineResult(
        transcript_text="Make one pan chicken rice with broth and spices.",
        cleaned_transcript_text="Make one pan chicken rice with broth and spices.",
        structured_recipe={
            "title": "One Pan Chicken Rice",
            "ingredients": ["2 cups rice", "3 cups broth"],
            "instructions": ["Toast rice", "Simmer in broth"],
            "mentioned_websites": [],
        },
        mentioned_websites=[],
        title_inferred=False,
        measurements_partial=True,
    )
    with patch("backend.app.main.resolve_social_url", return_value=mocked_resolution), patch(
        "backend.app.main._recover_recipe_url_from_social_signals",
        return_value=("", ""),
    ), patch(
        "backend.app.main.looks_like_recipe_text",
        return_value=False,
    ), patch(
        "backend.app.main.run_social_video_transcript_pipeline",
        return_value=transcript_result,
    ):
        payload = main.extract_metadata(url=social_url, _={})

    assert payload["url"] == social_url
    assert payload["content_source"] == "transcript_ai_fallback"
    assert payload["title"] == "One Pan Chicken Rice"
    assert payload["ingredients"] == ["2 cups rice", "3 cups broth"]
    assert payload["social_metadata"]["recipe_type"] == "transcript"
    assert payload["social_metadata"]["measurements_partial"] is True


def test_social_transcript_pipeline_repairs_suspicious_biscuit_quantities_from_cleaned_transcript():
    social_url = "https://www.facebook.com/reel/1234567890123456"
    mocked_resolution = SocialResolutionResult(
        source="facebook",
        canonical_url=social_url,
        resolved_url=None,
        method="none",
        post_id="1234567890123456",
        error="facebook_external_url_not_found",
        headless_attempted=False,
        headless_candidate_urls=[],
        fast_path_candidate_urls=[],
        ytdlp_title="Butter Swim Biscuits",
        ytdlp_description="short caption",
    )
    transcript_result = TranscriptPipelineResult(
        transcript_text=(
            "Two and a fourth teaspoons baking powder. "
            "Half a teaspoon baking soda. "
            "Half a teaspoon just plain old table salt. "
            "One and a half sticks ice-cold butter."
        ),
        cleaned_transcript_text=(
            "Two and a fourth teaspoons baking powder. "
            "Half a teaspoon baking soda. "
            "Half a teaspoon just plain old table salt. "
            "One and a half sticks ice-cold butter."
        ),
        structured_recipe={
            "title": "Butter Swim Biscuits",
            "ingredients": [
                "0.025 teaspoons baking powder",
                "0.005 teaspoons baking soda",
                "0.005 teaspoons table salt",
                "1.5 sticks ice-cold butter",
            ],
            "instructions": ["Mix.", "Bake."],
            "mentioned_websites": [],
        },
        mentioned_websites=[],
        title_inferred=False,
        measurements_partial=True,
    )

    with patch("backend.app.main.resolve_social_url", return_value=mocked_resolution), patch(
        "backend.app.main._recover_recipe_url_from_social_signals",
        return_value=("", ""),
    ), patch(
        "backend.app.main.looks_like_recipe_text",
        return_value=False,
    ), patch(
        "backend.app.main.run_social_video_transcript_pipeline",
        return_value=transcript_result,
    ):
        payload = main.extract_metadata(url=social_url, _={})

    assert payload["content_source"] == "transcript_ai_fallback"
    assert payload["ingredients"] == [
        "2.25 teaspoons baking powder",
        "0.5 teaspoon baking soda",
        "0.5 teaspoon table salt",
        "1.5 sticks ice-cold butter",
    ]
    assert payload["ingredient_groups"] == [{"title": "", "items": payload["ingredients"]}]


def test_normalize_transcript_recipe_payload_formats_grouped_spoken_quantity_objects():
    payload = main._normalize_transcript_recipe_payload(
        {
            "title": "Biscuits",
            "ingredient_groups": [
                {
                    "title": "",
                    "ingredients": [
                        {"quantity": "two and a fourth", "unit": "teaspoons", "name": "baking powder"},
                        {"quantity": "half a", "unit": "teaspoon", "name": "baking soda"},
                        {"quantity": "half a", "unit": "teaspoon", "name": "table salt"},
                    ],
                }
            ],
            "instruction_groups": [
                {
                    "title": "",
                    "instructions": ["Mix dry ingredients.", "Bake until golden."],
                }
            ],
        },
        "https://www.facebook.com/reel/1234567890123456",
    )

    assert payload["ingredients"] == [
        "2.25 teaspoons baking powder",
        "0.5 teaspoon baking soda",
        "0.5 teaspoon table salt",
    ]
    assert payload["ingredient_groups"] == [{"title": "", "items": payload["ingredients"]}]
    assert payload["instructions"] == ["Mix dry ingredients.", "Bake until golden."]
    assert payload["instruction_groups"] == [
        {"title": "Instructions", "steps": ["Mix dry ingredients.", "Bake until golden."]}
    ]


def test_normalize_transcript_recipe_payload_repairs_suspicious_numeric_quantities_from_transcript():
    payload = main._normalize_transcript_recipe_payload(
        {
            "title": "Biscuits",
            "ingredients": [
                "0.025 teaspoons baking powder",
                "0.005 teaspoons baking soda",
                "0.005 teaspoons table salt",
                "0.25 cup sugar",
            ],
            "instructions": ["Mix dry ingredients.", "Bake until golden."],
        },
        "https://www.facebook.com/reel/1234567890123456",
        cleaned_transcript_text=(
            "Two and a fourth teaspoons baking powder. "
            "Half a teaspoon baking soda. "
            "Half a teaspoon just plain old table salt. "
            "Mix in sugar."
        ),
    )

    assert payload["ingredients"] == [
        "2.25 teaspoons baking powder",
        "0.5 teaspoon baking soda",
        "0.5 teaspoon table salt",
        "0.25 cup sugar",
    ]
    assert payload["ingredient_groups"] == [{"title": "", "items": payload["ingredients"]}]


def test_find_transcript_quantity_evidence_allows_short_descriptive_gap_before_ingredient_name():
    transcript = (
        "Half a teaspoon just plain old table salt. "
        "Half a teaspoon of plain table salt. "
        "Half a teaspoon regular table salt."
    )

    assert main._find_transcript_quantity_evidence(transcript, "table salt", "teaspoon") == pytest.approx(0.5)


def test_repair_saved_ingredient_lines_from_transcript_keeps_salt_repair_with_descriptive_gap():
    repaired_lines, flagged_lines = main._repair_saved_ingredient_lines_from_transcript(
        [
            "0.025 teaspoons baking powder",
            "0.005 teaspoons baking soda",
            "0.005 teaspoons table salt",
        ],
        (
            "Two and a fourth teaspoons baking powder. "
            "Half a teaspoon baking soda. "
            "Half a teaspoon just plain old table salt."
        ),
    )

    assert repaired_lines == [
        "2 1/4 teaspoons baking powder",
        "1/2 teaspoon baking soda",
        "1/2 teaspoon table salt",
    ]
    assert flagged_lines == []


def test_social_transcript_pipeline_uses_canonical_url_for_facebook_share_links():
    social_url = "https://www.facebook.com/share/v/1CpgHJDPep/"
    canonical_url = "https://www.facebook.com/reel/1234567890123456"
    mocked_resolution = SocialResolutionResult(
        source="facebook",
        canonical_url=canonical_url,
        resolved_url=None,
        method="none",
        post_id="1234567890123456",
        error="facebook_external_url_not_found",
        headless_attempted=False,
        headless_candidate_urls=[],
        fast_path_candidate_urls=[],
        ytdlp_title="One Pan Chicken Rice",
        ytdlp_description="short caption",
    )
    transcript_result = TranscriptPipelineResult(
        transcript_text="Make one pan chicken rice with broth and spices.",
        cleaned_transcript_text="Make one pan chicken rice with broth and spices.",
        structured_recipe={
            "title": "One Pan Chicken Rice",
            "ingredients": ["2 cups rice", "3 cups broth"],
            "instructions": ["Toast rice", "Simmer in broth"],
            "mentioned_websites": [],
        },
        mentioned_websites=[],
        title_inferred=False,
        measurements_partial=True,
    )
    with patch("backend.app.main.resolve_social_url", return_value=mocked_resolution), patch(
        "backend.app.main._recover_recipe_url_from_social_signals",
        return_value=("", ""),
    ), patch(
        "backend.app.main.looks_like_recipe_text",
        return_value=False,
    ), patch(
        "backend.app.main.run_social_video_transcript_pipeline",
        return_value=transcript_result,
    ) as mock_transcript_pipeline:
        payload = main.extract_metadata(url=social_url, _={})

    mock_transcript_pipeline.assert_called_once()
    assert mock_transcript_pipeline.call_args.args[0] == canonical_url
    assert payload["url"] == social_url
    assert payload["content_source"] == "transcript_ai_fallback"
    assert payload["social_metadata"]["recipe_type"] == "transcript"


def test_social_transcript_pipeline_returns_structured_payload_even_without_ingredients_or_instructions():
    social_url = "https://www.facebook.com/reel/1234567890123456"
    mocked_resolution = SocialResolutionResult(
        source="facebook",
        canonical_url=social_url,
        resolved_url=None,
        method="none",
        post_id="1234567890123456",
        error="facebook_external_url_not_found",
        headless_attempted=False,
        headless_candidate_urls=[],
        fast_path_candidate_urls=[],
        ytdlp_title="Quick Sauce",
        ytdlp_description="short caption",
    )
    transcript_result = TranscriptPipelineResult(
        transcript_text="This is a quick sauce base with pantry items.",
        cleaned_transcript_text="This is a quick sauce base with pantry items.",
        structured_recipe={
            "title": "Quick Sauce",
            "ingredients": [],
            "instructions": [],
            "mentioned_websites": [],
        },
        mentioned_websites=[],
        title_inferred=True,
        measurements_partial=True,
    )
    with patch("backend.app.main.resolve_social_url", return_value=mocked_resolution), patch(
        "backend.app.main._recover_recipe_url_from_social_signals",
        return_value=("", ""),
    ), patch(
        "backend.app.main.looks_like_recipe_text",
        return_value=False,
    ), patch(
        "backend.app.main.run_social_video_transcript_pipeline",
        return_value=transcript_result,
    ):
        payload = main.extract_metadata(url=social_url, _={})

    assert "status" not in payload
    assert payload["url"] == social_url
    assert payload["content_source"] == "transcript_ai_fallback"
    assert payload["recipe_type"] == "transcript"
    assert payload["title_inferred"] is True
    assert payload["measurements_partial"] is True
    assert payload["ingredients"] == []
    assert payload["instructions"] == []


def test_social_transcript_pipeline_prefers_recovered_recipe_url_when_mentioned_site_resolves():
    social_url = "https://www.facebook.com/reel/1234567890123456"
    recovered_url = "https://sugargeekshow.com/braised-beef-short-ribs/"
    mocked_resolution = SocialResolutionResult(
        source="facebook",
        canonical_url=social_url,
        resolved_url=None,
        method="none",
        post_id="1234567890123456",
        error="facebook_external_url_not_found",
        headless_attempted=False,
        headless_candidate_urls=[],
        fast_path_candidate_urls=[],
        ytdlp_title="Braised Beef Short Ribs",
        ytdlp_description="short caption",
    )
    transcript_result = TranscriptPipelineResult(
        transcript_text="Braised beef short ribs from Sugar Geek Show dot com.",
        cleaned_transcript_text="Braised beef short ribs from Sugar Geek Show dot com.",
        structured_recipe={
            "title": "Braised Beef Short Ribs",
            "ingredients": ["3 lb short ribs", "1 tsp salt"],
            "instructions": ["Season the ribs", "Braise until tender"],
            "mentioned_websites": ["sugargeekshow.com"],
        },
        mentioned_websites=["sugargeekshow.com"],
        title_inferred=False,
        measurements_partial=True,
    )
    recovered_html = """
    <html><head>
      <script type=\"application/ld+json\">
      {\"@context\": \"https://schema.org\", \"@type\": \"Recipe\", \"name\": \"Braised Beef Short Ribs\", \"recipeIngredient\": [\"3 lb short ribs\", \"1 tsp salt\"], \"recipeInstructions\": [\"Season the ribs\", \"Braise until tender\"]}
      </script>
    </head></html>
    """
    with patch("backend.app.main.resolve_social_url", return_value=mocked_resolution), patch(
        "backend.app.main._recover_recipe_url_from_social_signals",
        return_value=("", ""),
    ), patch(
        "backend.app.main.looks_like_recipe_text",
        return_value=False,
    ), patch(
        "backend.app.main.run_social_video_transcript_pipeline",
        return_value=transcript_result,
    ), patch(
        "backend.app.main._recover_recipe_url_from_transcript_mentions",
        return_value=(recovered_url, "transcript_direct_slug"),
    ), patch(
        "backend.app.main.requests.get",
        return_value=_MockHtmlResponse(recovered_html),
    ):
        payload = main.extract_metadata(url=social_url, _={})

    assert payload["url"] == recovered_url
    assert payload["resolved_recipe_url"] == recovered_url
    assert payload["content_source"] == "resolved_recipe_url"
    assert payload["title"] == "Braised Beef Short Ribs"


def test_transcript_recovery_search_uses_ingredient_fingerprint_when_no_domain():
    recorded_queries: list[str] = []

    def _fake_safe_get(url, **_kwargs):
        if "duckduckgo.com/html/" in url:
            recorded_queries.append(main.parse_qs(main.urlparse(url).query).get("q", [""])[0])
            return _MockHtmlResponse('<html><body><a href="https://example.com/nope">x</a></body></html>')
        raise RuntimeError("unexpected request")

    with patch("backend.app.main.safe_get", side_effect=_fake_safe_get), patch(
        "backend.app.main._validate_recipe_page_and_parse",
        return_value=(False, {}),
    ):
        recovered_url, method = main._recover_recipe_url_from_transcript_mentions(
            "https://www.facebook.com/reel/1234567890123456",
            "One Pan Chicken Rice",
            [],
            ["2 cups rice", "3 cups chicken broth", "1 tsp paprika"],
        )

    assert recovered_url == ""
    assert method == ""
    assert recorded_queries
    assert "one pan chicken rice recipe" in recorded_queries[0].lower()
    assert "chicken" in recorded_queries[0].lower()


def test_social_transcript_pipeline_failure_falls_back_to_partial_response():
    social_url = "https://www.facebook.com/reel/1234567890123456"
    mocked_resolution = SocialResolutionResult(
        source="facebook",
        canonical_url=social_url,
        resolved_url=None,
        method="none",
        post_id="1234567890123456",
        error="facebook_external_url_not_found",
        headless_attempted=False,
        headless_candidate_urls=[],
        fast_path_candidate_urls=[],
        ytdlp_title="Some Reel",
        ytdlp_description="short caption",
    )
    with patch("backend.app.main.resolve_social_url", return_value=mocked_resolution), patch(
        "backend.app.main._recover_recipe_url_from_social_signals",
        return_value=("", ""),
    ), patch(
        "backend.app.main.looks_like_recipe_text",
        return_value=False,
    ), patch(
        "backend.app.main.run_social_video_transcript_pipeline",
        side_effect=RuntimeError("pipeline failed"),
    ):
        payload = main.extract_metadata(url=social_url, _={})

    assert payload["status"] == "partial"
    assert payload["url"] == social_url
    assert payload["reason"] == "We couldn’t process the shared video transcript automatically. Please try again."
    assert payload["social_metadata"]["transcript_pipeline_stage"] == ""


def test_social_transcript_pipeline_ytdlp_extract_failure_returns_specific_partial_reason():
    social_url = "https://www.facebook.com/reel/1234567890123456"
    mocked_resolution = SocialResolutionResult(
        source="facebook",
        canonical_url=social_url,
        resolved_url=None,
        method="none",
        post_id="1234567890123456",
        error="facebook_external_url_not_found",
        headless_attempted=False,
        headless_candidate_urls=[],
        fast_path_candidate_urls=[],
        ytdlp_title="Some Reel",
        ytdlp_description="short caption",
    )
    with patch("backend.app.main.resolve_social_url", return_value=mocked_resolution), patch(
        "backend.app.main._recover_recipe_url_from_social_signals",
        return_value=("", ""),
    ), patch(
        "backend.app.main.looks_like_recipe_text",
        return_value=False,
    ), patch(
        "backend.app.main.run_social_video_transcript_pipeline",
        side_effect=YtDlpExtractError("Cannot parse data"),
    ):
        payload = main.extract_metadata(url=social_url, _={})

    assert payload["status"] == "partial"
    assert payload["url"] == social_url
    assert (
        payload["reason"]
        == "This Facebook video couldn’t be processed automatically. Try opening the original post or paste the recipe link."
    )
    assert payload["social_metadata"]["transcript_pipeline_stage"] == "ytdlp"


def test_social_transcript_pipeline_whisper_failure_returns_specific_partial_reason_and_stage():
    social_url = "https://www.facebook.com/reel/1234567890123456"
    mocked_resolution = SocialResolutionResult(
        source="facebook",
        canonical_url=social_url,
        resolved_url=None,
        method="none",
        post_id="1234567890123456",
        error="facebook_external_url_not_found",
        headless_attempted=False,
        headless_candidate_urls=[],
        fast_path_candidate_urls=[],
        ytdlp_title="Some Reel",
        ytdlp_description="short caption",
    )
    with patch("backend.app.main.resolve_social_url", return_value=mocked_resolution), patch(
        "backend.app.main._recover_recipe_url_from_social_signals",
        return_value=("", ""),
    ), patch(
        "backend.app.main.looks_like_recipe_text",
        return_value=False,
    ), patch(
        "backend.app.main.run_social_video_transcript_pipeline",
        side_effect=main.TranscriptPipelineStageError("whisper", RuntimeError("missing dependency")),
    ):
        payload = main.extract_metadata(url=social_url, _={})

    assert payload["status"] == "partial"
    assert payload["reason"] == "We extracted the audio, but Whisper transcription failed."
    assert payload["social_metadata"]["transcript_pipeline_stage"] == "whisper"


def test_social_recovery_cleans_noisy_social_title_hint():
    noisy_title = "89K views · 6.2K reactions | I’ve perfected my braised beef short ribs ... | Sugar Geek Show"
    assert main._clean_social_title_hint(noisy_title) == "Braised Beef Short Ribs"


def test_social_recovery_infers_host_when_no_description_urls():
    mocked_resolution = SocialResolutionResult(
        source="facebook",
        canonical_url="https://www.facebook.com/reel/1234567890123456",
        resolved_url=None,
        method="none",
        post_id="1234567890123456",
        error="facebook_external_url_not_found",
        ytdlp_title="89K views · 6.2K reactions | I’ve perfected my braised beef short ribs ... | Sugar Geek Show",
        ytdlp_description="No external links here",
    )

    assert main._extract_hosts_from_social_resolution(mocked_resolution) == ["sugargeekshow.com"]


def test_social_recovery_attempts_direct_slug_with_inferred_host():
    mocked_resolution = SocialResolutionResult(
        source="facebook",
        canonical_url="https://www.facebook.com/reel/1234567890123456",
        resolved_url=None,
        method="none",
        post_id="1234567890123456",
        error="facebook_external_url_not_found",
        ytdlp_title="89K views · 6.2K reactions | I’ve perfected my braised beef short ribs ... | Sugar Geek Show",
        ytdlp_description="No external links here",
    )
    debug_trace: dict = {}
    validated_urls: list[str] = []

    def _validate_stub(url: str):
        validated_urls.append(url)
        return False, {}

    with patch("backend.app.main._validate_recipe_page_and_parse", side_effect=_validate_stub), patch(
        "backend.app.main.safe_get", side_effect=RuntimeError("search unavailable in unit test")
    ):
        recovered_url, method = main._recover_recipe_url_from_social_signals(
            "https://www.facebook.com/share/v/1CpgHJDPep/",
            mocked_resolution,
            debug_trace=debug_trace,
        )

    assert recovered_url == ""
    assert method == ""
    assert debug_trace["hosts"] == ["sugargeekshow.com"]
    assert debug_trace["direct_slug_attempted"] is True
    assert "https://sugargeekshow.com/braised-beef-short-ribs/" in validated_urls


def test_social_hint_discovery_uses_safe_get_with_encoded_query():
    recorded_urls: list[str] = []

    def _fake_safe_get(url, **_kwargs):
        recorded_urls.append(url)
        return _MockHtmlResponse('<html><body><a class="result__a" href="https://example.com/recipe">Recipe</a></body></html>')

    with patch("backend.app.main.safe_get", side_effect=_fake_safe_get):
        result = main._discover_recipe_url_from_social_hints(
            "https://www.facebook.com/reel/1234567890123456",
            {"title": "One Pan Chicken Rice"},
        )

    assert result["query"]
    assert recorded_urls
    assert recorded_urls[0].startswith("https://html.duckduckgo.com/html/?q=")
