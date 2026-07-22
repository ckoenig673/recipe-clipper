import asyncio
import time
from io import BytesIO
from unittest.mock import patch

import pytest
import requests
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.datastructures import Headers, UploadFile

from backend.app import main


def _upload_file(content_type: str, filename: str = "recipe.png", payload: bytes = b"fake-image-bytes") -> UploadFile:
    return UploadFile(
        file=BytesIO(payload),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


def test_import_image_rejects_missing_file():
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(main._import_image_recipe_from_upload(image=None))

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "Image file is required"


def test_import_image_rejects_unsupported_file_type():
    upload = _upload_file("text/plain", filename="recipe.txt")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(main._import_image_recipe_from_upload(image=upload))

    assert exc_info.value.status_code == 415
    assert "Unsupported file type" in str(exc_info.value.detail)


def test_import_image_passes_ocr_text_to_recipe_parser():
    upload = _upload_file("image/png", filename="dinner.png")
    parsed_payload = {
        "title": "OCR Recipe",
        "notes": "Keep chilled.",
        "ingredient_groups": [{"title": "Ingredients", "items": ["1 cup rice"]}],
        "instruction_groups": [{"title": "Instructions", "steps": ["Cook rice"]}],
        "ingredients": [],
        "instructions": [],
        "servings": "4",
        "prep_time": "10 min",
        "cook_time": "20 min",
        "total_time": "30 min",
    }

    ocr_result = {
        "text": "raw ocr text",
        "confidence": 91.5,
        "engine": "external_easyocr",
        "rotation": 0,
        "keyword_score": 8,
        "fraction_score": 2,
    }
    with patch("backend.app.main._extract_text_from_image_upload", return_value=ocr_result) as mock_extract, patch(
        "backend.app.main._parse_recipe_text_from_ocr", return_value=(parsed_payload, "ai_cleanup")
    ) as mock_parse:
        payload = asyncio.run(main._import_image_recipe_from_upload(image=upload))

    mock_extract.assert_called_once()
    mock_parse.assert_called_once_with("raw ocr text", source_url="image://upload/dinner.png", ocr_confidence=91.5)
    assert payload["title"] == "OCR Recipe"
    assert payload["notes"] == "Keep chilled."
    assert payload["content_source"] == "image_ocr"
    assert payload["source_type"] == "Image"
    assert payload["ocr_confidence"] == 91.5
    assert payload["ocr_engine"] == "external_easyocr"
    assert payload["ocr_rotation"] == 0
    assert payload["ocr_keyword_score"] == 8
    assert payload["ocr_fraction_score"] == 2
    assert "ocr_warning" not in payload


def test_extract_text_from_ocr_worker_success():
    worker_response = {
        "text": "Ingredients 1/2 cup sugar mix bake",
        "confidence": 83.4,
        "rotation": 0,
        "engine": "pc-ocr-worker",
        "keyword_score": 6,
        "fraction_score": 1,
    }

    with patch.dict("os.environ", {"OCR_WORKER_URL": "http://ocr:8787/ocr/image"}, clear=False), patch(
        "backend.app.main.requests.post"
    ) as mock_post:
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = worker_response

        result = main._extract_text_from_ocr_worker(b"image-bytes", filename="remote.png", content_type="image/png")

    assert result["text"] == "Ingredients 1/2 cup sugar mix bake"
    assert result["confidence"] == pytest.approx(83.4)
    assert result["engine"] == "pc-ocr-worker"
    assert result["rotation"] == 0
    assert result["keyword_score"] == 6
    assert result["fraction_score"] == 1
    assert result["text_length"] == len("Ingredients 1/2 cup sugar mix bake")


def test_extract_text_from_ocr_worker_defaults_engine_when_missing():
    worker_response = {
        "text": "Ingredients 1/2 cup sugar mix bake",
        "confidence": 83.4,
        "rotation": 0,
        "keyword_score": 6,
        "fraction_score": 1,
    }

    with patch.dict("os.environ", {"OCR_WORKER_URL": "http://ocr:8787/ocr/image"}, clear=False), patch(
        "backend.app.main.requests.post"
    ) as mock_post:
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = worker_response
        result = main._extract_text_from_ocr_worker(b"image-bytes")

    assert result["engine"] == "external_easyocr"


def test_extract_text_from_ocr_worker_defaults_content_type_to_image_jpeg_when_missing():
    upload = _upload_file("image/png", filename="remote.png")
    upload.headers = Headers({})
    worker_response = {
        "text": "Ingredients 1/2 cup sugar mix bake",
        "confidence": 83.4,
        "rotation": 0,
        "engine": "pc-ocr-worker",
        "keyword_score": 6,
        "fraction_score": 1,
    }

    with patch.dict("os.environ", {"OCR_WORKER_URL": "http://ocr:8787/ocr/image"}, clear=False), patch(
        "backend.app.main.requests.post"
    ) as mock_post:
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = worker_response
        asyncio.run(main._extract_text_from_image_upload(upload))

    files = mock_post.call_args.kwargs["files"]
    assert files["image"][2] == "image/jpeg"


def test_extract_text_from_image_upload_raises_when_worker_text_empty():
    upload = _upload_file("image/png", filename="fallback.png")

    with patch.dict("os.environ", {"OCR_WORKER_URL": "http://ocr:8787/ocr/image"}, clear=False), patch(
        "backend.app.main.requests.post"
    ) as mock_post:
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {"text": " \n \n\t"}
        with pytest.raises(ValueError, match="empty_ocr_worker_text"):
            asyncio.run(main._extract_text_from_image_upload(upload))


def test_import_image_maps_missing_worker_url_to_503():
    upload = _upload_file("image/png", filename="remote.png")

    with patch.dict("os.environ", {"OCR_WORKER_URL": ""}, clear=False):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(main._import_image_recipe_from_upload(upload))

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Image OCR worker is not configured."


def test_import_image_maps_worker_timeout_to_504():
    upload = _upload_file("image/png", filename="remote.png")

    with patch.dict("os.environ", {"OCR_WORKER_URL": "http://ocr:8787/ocr/image"}, clear=False), patch(
        "backend.app.main.requests.post",
        side_effect=requests.Timeout("timeout"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(main._import_image_recipe_from_upload(upload))

    assert exc_info.value.status_code == 504
    assert exc_info.value.detail == "Image OCR worker timed out. Make sure the OCR worker is running on the PC."


def test_import_image_maps_invalid_worker_payload_to_502():
    upload = _upload_file("image/png", filename="remote.png")

    with patch.dict("os.environ", {"OCR_WORKER_URL": "http://ocr:8787/ocr/image"}, clear=False), patch(
        "backend.app.main.requests.post"
    ) as mock_post:
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = ["invalid"]
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(main._import_image_recipe_from_upload(upload))

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Image OCR worker failed while processing this upload."


def test_import_image_maps_worker_empty_text_to_422():
    upload = _upload_file("image/png", filename="remote.png")

    with patch.dict("os.environ", {"OCR_WORKER_URL": "http://ocr:8787/ocr/image"}, clear=False), patch(
        "backend.app.main.requests.post"
    ) as mock_post:
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {"text": "   "}
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(main._import_image_recipe_from_upload(upload))

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "Couldn't read recipe text from this image. Try a clearer photo."


def test_import_image_returns_strong_warning_for_very_low_confidence():
    upload = _upload_file("image/png", filename="dinner.png")
    parsed_payload = {
        "title": "OCR Recipe",
        "ingredient_groups": [{"title": "Ingredients", "items": ["1 cup rice"]}],
        "instruction_groups": [{"title": "Instructions", "steps": ["Cook rice"]}],
        "ingredients": [],
        "instructions": [],
        "servings": "4",
        "prep_time": "10 min",
        "cook_time": "20 min",
        "total_time": "30 min",
    }
    with patch(
        "backend.app.main._extract_text_from_image_upload",
        return_value={
            "text": "raw ocr text",
            "confidence": 44.9,
            "engine": "external_easyocr",
            "rotation": 0,
            "keyword_score": 2,
            "fraction_score": 0,
        },
    ), patch("backend.app.main._parse_recipe_text_from_ocr", return_value=(parsed_payload, "ai_cleanup")):
        payload = asyncio.run(main._import_image_recipe_from_upload(image=upload))

    assert payload["ocr_confidence"] == 44.9
    assert payload["low_confidence_quantities"] is True
    assert payload["ocr_warning"] == "OCR confidence is low. Please review ingredients and measurements carefully."
    assert payload["ocr_warning_level"] == "strong"


def test_import_image_allows_low_confidence_when_text_is_meaningful():
    upload = _upload_file("image/png", filename="dinner.png")
    parsed_payload = {
        "title": "OCR Recipe",
        "ingredient_groups": [{"title": "Ingredients", "items": ["1 cup rice"]}],
        "instruction_groups": [{"title": "Instructions", "steps": ["Cook rice"]}],
        "ingredients": [],
        "instructions": [],
        "servings": "4",
        "prep_time": "10 min",
        "cook_time": "20 min",
        "total_time": "30 min",
    }

    with patch(
        "backend.app.main._extract_text_from_image_upload",
        return_value={
            "text": "ingredients 1/2 cup rice mix and bake",
            "confidence": 65.0,
            "engine": "external_easyocr",
            "rotation": 90,
            "keyword_score": 4,
            "fraction_score": 1,
        },
    ), patch("backend.app.main._parse_recipe_text_from_ocr", return_value=(parsed_payload, "ai_cleanup")):
        payload = asyncio.run(main._import_image_recipe_from_upload(image=upload))

    assert payload["ocr_confidence"] == 65.0
    assert payload["low_confidence_quantities"] is True
    assert payload["ocr_warning"] == "OCR confidence is low. Please review ingredients and measurements carefully."
    assert payload["ocr_warning_level"] == "mild"


def test_merge_ocr_ai_cleanup_result_preserves_deterministic_fields_when_ai_fields_are_blank():
    ai_recipe = {
        "title": "",
        "servings": "",
        "prep_time": "",
        "cook_time": "",
        "total_time": "",
        "ingredient_groups": [],
        "instruction_groups": [],
    }
    fallback_recipe = {
        "title": "Banana Crunch Cake",
        "servings": "8",
        "prep_time": "15 min",
        "cook_time": "30 min",
        "total_time": "45 min",
        "prep_minutes": 15,
        "cook_minutes": 30,
        "total_minutes": 45,
        "ingredient_groups": [{"title": "", "items": ["2 cups flour", "3 bananas"]}],
        "instruction_groups": [{"title": "", "steps": ["Mix batter", "Bake until done"]}],
    }

    merged = main._merge_ocr_ai_cleanup_result(ai_recipe, fallback_recipe)

    assert merged["title"] == "Banana Crunch Cake"
    assert merged["servings"] == "8"
    assert merged["prep_time"] == "15 minutes"
    assert merged["cook_time"] == "30 minutes"
    assert merged["total_time"] == "45 minutes"
    assert merged["prep_minutes"] == 15
    assert merged["cook_minutes"] == 30
    assert merged["total_minutes"] == 45
    assert merged["ingredient_groups"] == [{"title": "", "items": ["2 cups flour", "3 bananas"]}]
    assert merged["instruction_groups"] == [{"title": "Instructions", "steps": ["Mix batter", "Bake until done"]}]
    assert merged["ingredients"] == ["2 cups flour", "3 bananas"]
    assert merged["instructions"] == ["Mix batter", "Bake until done"]


def test_merge_ocr_ai_cleanup_result_prefers_non_empty_structurally_valid_ai_fields():
    ai_recipe = {
        "title": "Cleaned Cake",
        "servings": "10",
        "prep_time": "20 min",
        "cook_time": "",
        "total_time": "",
        "ingredient_groups": [{"title": "Cake", "items": ["2 cups flour", "1 cup sugar"]}],
        "instruction_groups": [{"title": "", "steps": ["Whisk dry ingredients", "Bake"]}],
    }
    fallback_recipe = {
        "title": "Noisy OCR Title",
        "servings": "8",
        "prep_time": "15 min",
        "cook_time": "30 min",
        "total_time": "45 min",
        "prep_minutes": 15,
        "cook_minutes": 30,
        "total_minutes": 45,
        "ingredient_groups": [{"title": "", "items": ["bad OCR item"]}],
        "instruction_groups": [{"title": "", "steps": ["bad OCR step"]}],
    }

    merged = main._merge_ocr_ai_cleanup_result(ai_recipe, fallback_recipe)

    assert merged["title"] == "Cleaned Cake"
    assert merged["servings"] == "10"
    assert merged["prep_time"] == "20 minutes"
    assert merged["prep_minutes"] == 20
    assert merged["cook_time"] == "30 minutes"
    assert merged["cook_minutes"] == 30
    assert merged["ingredient_groups"] == [{"title": "Cake", "items": ["2 cups flour", "1 cup sugar"]}]
    assert merged["instruction_groups"] == [{"title": "Instructions", "steps": ["Whisk dry ingredients", "Bake"]}]
    assert merged["ingredients"] == ["2 cups flour", "1 cup sugar"]
    assert merged["instructions"] == ["Whisk dry ingredients", "Bake"]


def test_merge_ocr_ai_cleanup_result_preserves_fallback_title_when_ai_title_is_invalid():
    ai_recipe = {
        "title": "Ingredients",
        "servings": "10",
        "ingredient_groups": [{"title": "", "items": ["2 cups flour"]}],
        "instruction_groups": [{"title": "", "steps": ["Bake"]}],
    }
    fallback_recipe = {
        "title": "Topsy-Turvy Banana Crunch Cake",
        "servings": "8",
        "ingredient_groups": [{"title": "", "items": ["2 cups flour"]}],
        "instruction_groups": [{"title": "", "steps": ["Bake"]}],
    }

    merged = main._merge_ocr_ai_cleanup_result(ai_recipe, fallback_recipe)

    assert merged["title"] == "Topsy-Turvy Banana Crunch Cake"
    assert merged["servings"] == "10"


def test_parse_recipe_text_from_ocr_merges_ai_cleanup_with_deterministic_fallback():
    deterministic_recipe = {
        "title": "Banana Crunch Cake",
        "servings": "8",
        "prep_time": "15 min",
        "cook_time": "30 min",
        "total_time": "45 min",
        "prep_minutes": 15,
        "cook_minutes": 30,
        "total_minutes": 45,
        "ingredient_groups": [{"title": "", "items": ["2 cups flour", "3 bananas"]}],
        "instruction_groups": [{"title": "", "steps": ["Mix batter", "Bake until done"]}],
    }
    ai_recipe = {
        "title": "",
        "servings": "",
        "prep_time": "",
        "cook_time": "",
        "total_time": "",
        "ingredient_groups": [{"title": "Cake", "items": ["2 cups flour", "3 ripe bananas"]}],
        "instruction_groups": [{"title": "", "steps": ["Whisk ingredients", "Bake"]}],
    }

    with patch("backend.app.main.parse_social_caption_recipe", return_value=deterministic_recipe), patch(
        "backend.app.main.call_ollama_review", return_value=ai_recipe
    ):
        parsed, parser_source = main._parse_recipe_text_from_ocr(
            "ocr text",
            source_url="image://upload/cake.png",
            ocr_confidence=91.5,
        )

    assert parser_source == "ai_cleanup"
    assert parsed["title"] == "Banana Crunch Cake"
    assert parsed["servings"] == "8"
    assert parsed["prep_time"] == "15 minutes"
    assert parsed["cook_time"] == "30 minutes"
    assert parsed["ingredient_groups"] == [{"title": "Cake", "items": ["2 cups flour", "3 ripe bananas"]}]
    assert parsed["instruction_groups"] == [{"title": "Instructions", "steps": ["Whisk ingredients", "Bake"]}]


def test_build_ai_prompt_adds_low_trust_quantity_rules_when_ocr_confidence_is_low():
    prompt = main.build_ai_prompt("1 cup sugar", low_trust_quantities=True)
    assert "Treat quantities as low-trust fields." in prompt
    assert 'do NOT "fix" it by guessing a new number' in prompt


def test_build_ai_prompt_omits_low_trust_quantity_rules_when_confidence_is_not_low():
    prompt = main.build_ai_prompt("1 cup sugar", low_trust_quantities=False)
    assert "Treat quantities as low-trust fields." not in prompt


def test_import_image_endpoint_requires_image_form_field():
    pytest.importorskip("multipart")
    client = TestClient(main.app)
    main.app.dependency_overrides[main.require_user] = lambda: {"id": 1}
    try:
        response = client.post("/import/image", files={})
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 422
    body = response.json()
    assert body["detail"][0]["loc"][-1] == "image"


def test_import_image_endpoint_accepts_multipart_image_field():
    pytest.importorskip("multipart")
    client = TestClient(main.app)
    main.app.dependency_overrides[main.require_user] = lambda: {"id": 1}
    with patch("backend.app.main._import_image_recipe_from_upload", return_value={"title": "ok"}) as mock_import:
        try:
            response = client.post(
                "/import/image",
                files={"image": ("recipe.png", b"fake-image-bytes", "image/png")},
            )
        finally:
            main.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"title": "ok"}
    mock_import.assert_called_once()


def test_split_instruction_sentences_preserves_semicolon_clauses_from_ocr_text():
    ocr_text = (
        "Spoon half of batter into prepared pan; sprinkle with half of oat topping. "
        "Top with remaining batter and topping."
    )

    steps = main._split_instruction_sentences(ocr_text)

    assert steps == [
        "Spoon half of batter into prepared pan; sprinkle with half of oat topping. Top with remaining batter and topping.",
    ]


def test_split_instruction_sentences_recovers_missing_with_clause_verbs():
    ocr_text = "Spoon half of batter into prepared pan; with half of oat topping"

    steps = main._split_instruction_sentences(ocr_text)

    assert steps == [
        "Spoon half of batter into prepared pan.",
        "sprinkle with half of oat topping.",
    ]


def test_split_instruction_sentences_rewrites_double_with_oat_topping_phrase():
    ocr_text = "Spoon half of batter into prepared pan; with half of oat topping with remaining batter and topping"

    steps = main._split_instruction_sentences(ocr_text)

    assert steps == [
        "Spoon half of batter into prepared pan; sprinkle with half of oat topping. Top with remaining batter and topping.",
    ]


def test_split_instruction_sentences_breaks_merged_smooth_to_spoon_step():
    ocr_text = (
        "Combine cake mix, sour cream, banana and egg in medium bowl. "
        "Beat with electric mixer at low speed about 1 minute or until blended. "
        "Increase to medium; beat 1 to 2 minutes or until smooth; Spoon half of batter into prepared pan; "
        "sprinkle with half of oat topping with remaining batter and topping"
    )

    steps = main._split_instruction_sentences(ocr_text)

    assert any(step.endswith("until smooth.") for step in steps)
    spoon_step = next((step for step in steps if step.startswith("Spoon half of batter into prepared pan")), "")
    assert spoon_step
    assert "sprinkle with half of oat topping" in spoon_step
    assert "Top with remaining batter and topping" in spoon_step


def test_split_instruction_sentences_breaks_clean_to_cool_transition():
    ocr_text = "Bake 25 to 30 minutes or until toothpick inserted into center comes out clean Cool completely on wire rack."

    steps = main._split_instruction_sentences(ocr_text)

    assert steps == [
        "Bake 25 to 30 minutes or until toothpick inserted into center comes out clean.",
        "Cool completely on wire rack.",
    ]


def test_split_instruction_sentences_adds_missing_break_after_crumbly_transition():
    ocr_text = "Cut in butter until crumbly Stir in pecans"

    steps = main._split_instruction_sentences(ocr_text)

    assert steps == [
        "Cut in butter until crumbly.",
        "Stir in pecans.",
    ]


def test_split_instruction_sentences_rewrites_colon_after_smooth_transition():
    ocr_text = "Increase speed; beat until smooth: Spoon into pan"

    steps = main._split_instruction_sentences(ocr_text)

    assert steps == [
        "Increase speed; beat until smooth.",
        "Spoon into pan.",
    ]


def test_parse_social_caption_recipe_for_ocr_prefers_uppercase_food_title_line_even_with_noisy_title_hint():
    ocr_text = "Suackiw' Buack Cakes TOPSY-TURVY BANANA CRUNCH CAKE"

    parsed = main.parse_social_caption_recipe(
        ocr_text,
        source_url="image://upload/scan.png",
        title_hint="Suackiw' Buack Cakes TOPSY-TURVY BANANA CRUNCH CAKE",
    )

    assert parsed["title"] == "TOPSY-TURVY BANANA CRUNCH CAKE"


def test_parse_social_caption_recipe_for_ocr_keeps_mixed_case_title_before_ingredients_heading():
    ocr_text = "\n".join(
        [
            "Favorite Family Recipes",
            "Topsy-Turvy Banana Crunch Cake",
            "Ingredients",
            "2 cups flour",
            "Instructions",
            "Bake until done.",
        ]
    )

    parsed = main.parse_social_caption_recipe(
        ocr_text,
        source_url="image://upload/scan.png",
        title_hint="",
    )

    assert parsed["title"] == "Topsy-Turvy Banana Crunch Cake"


def test_parse_social_caption_recipe_for_ocr_ignores_noisy_leading_metadata_lines():
    ocr_text = "\n".join(
        [
            "www.example.com",
            "Prep Time 15 min",
            "Page 1 of 2",
            "Topsy-Turvy Banana Crunch Cake",
            "Ingredients",
            "2 cups flour",
        ]
    )

    parsed = main.parse_social_caption_recipe(
        ocr_text,
        source_url="image://upload/scan.png",
        title_hint="",
    )

    assert parsed["title"] == "Topsy-Turvy Banana Crunch Cake"


def test_extract_ocr_title_from_lines_prefers_title_before_inline_ingredients_heading():
    lines = [
        "Favorite Family Recipes",
        "Topsy-Turvy Banana Crunch Cake Ingredients",
        "2 cups flour",
    ]

    assert main._extract_ocr_title_from_lines(lines) == "Topsy-Turvy Banana Crunch Cake"


def test_extract_ocr_title_from_lines_trims_blob_line_before_servings_and_ingredients():
    lines = [
        "TOPSYTURVY BANANA CRUNCH CAKE Makes 9 servings 1/3 cup oats 2 tablespoons brown sugar",
    ]

    assert main._extract_ocr_title_from_lines(lines) == "TOPSYTURVY BANANA CRUNCH CAKE"


def test_parse_social_caption_recipe_for_ocr_preserves_title_from_single_line_blob_before_servings_noise():
    ocr_text = (
        "TOPSYTURVY BANANA CRUNCH CAKE Makes 9 servings 1/s cup uncooked old-fashioned oats "
        "3 tablespoons packed brown sugar 1 tablespoon all-purpose flour 1/4 teaspoon ground cinnamon "
        "2 tablespoons butter 2 tablespoons chopped pecans 1 1 package (9 ounces) yellow cake mix "
        "without pudding in the mix 1/2 cup sour cream Yz cup mashed banana (about 1 medium) 1 egg, lightly beaten "
        "1 . Preheat oven to 350* Lightly grease 8-inch square baking pan."
    )

    parsed = main.parse_social_caption_recipe(
        ocr_text,
        source_url="image://upload/scan.png",
        title_hint="",
    )

    assert parsed["title"] == "TOPSYTURVY BANANA CRUNCH CAKE"


def test_extract_ocr_title_from_lines_prefers_recipe_like_suffix_from_mixed_case_line():
    lines = [
        "Favorite Family Recipes Topsy-Turvy Banana Crunch Cake",
        "Ingredients",
        "2 cups flour",
    ]

    assert main._extract_ocr_title_from_lines(lines) == "Topsy-Turvy Banana Crunch Cake"


def test_extract_ocr_title_from_lines_ignores_noisy_same_line_page_chrome():
    lines = [
        "Page 1 Favorite Family Recipes Topsy-Turvy Banana Crunch Cake",
        "Ingredients",
        "2 cups flour",
    ]

    assert main._extract_ocr_title_from_lines(lines) == "Topsy-Turvy Banana Crunch Cake"


def test_parse_social_caption_recipe_for_ocr_prefers_title_suffix_before_ingredients_heading():
    ocr_text = "\n".join(
        [
            "Favorite Family Recipes Topsy-Turvy Banana Crunch Cake",
            "Ingredients",
            "2 cups flour",
            "Instructions",
            "Bake until done.",
        ]
    )

    parsed = main.parse_social_caption_recipe(
        ocr_text,
        source_url="image://upload/scan.png",
        title_hint="",
    )

    assert parsed["title"] == "Topsy-Turvy Banana Crunch Cake"


def test_parse_social_caption_recipe_for_url_keeps_existing_first_line_title_behavior():
    caption_text = "Suackiw Buack Cakes TOPSY-TURVY BANANA CRUNCH CAKE\nmix and bake."

    parsed = main.parse_social_caption_recipe(
        caption_text,
        source_url="https://example.com/recipe-post",
        title_hint="",
    )

    assert parsed["title"] == "Suackiw Buack Cakes TOPSY-TURVY BANANA CRUNCH CAKE"


def test_extract_ingredient_candidates_keeps_optional_line_without_quantity():
    text = "\n".join(
        [
            "Ingredients",
            "2 cups flour",
            "Melted chocolate (optional, see Tip)",
            "Mix until smooth.",
        ]
    )
    lines = [line for line in text.split("\n") if line.strip()]

    ingredients = main._extract_ingredient_candidates_from_text(lines, text)

    assert "Melted chocolate (optional, see Tip)" in ingredients


def test_extract_ingredient_candidates_keeps_salt_to_taste_without_quantity():
    text = "\n".join(
        [
            "Ingredients",
            "1 cup broth",
            "Salt to taste",
            "Bake for 20 minutes.",
        ]
    )
    lines = [line for line in text.split("\n") if line.strip()]

    ingredients = main._extract_ingredient_candidates_from_text(lines, text)

    assert "Salt to taste" in ingredients


def test_extract_ingredient_candidates_excludes_instruction_drizzle_line():
    text = "\n".join(
        [
            "Ingredients",
            "1 cup flour",
            "Drizzle with melted chocolate, if desired.",
            "Serve warm.",
        ]
    )
    lines = [line for line in text.split("\n") if line.strip()]

    ingredients = main._extract_ingredient_candidates_from_text(lines, text)

    assert "Drizzle with melted chocolate, if desired" not in ingredients


def test_parse_social_caption_recipe_bounds_oversized_first_line_and_finishes_quickly():
    huge_prefix = ("metadata " * 3000) + "TOPSY-TURVY BANANA CRUNCH CAKE"
    text = "\n".join([huge_prefix, "Ingredients", "2 cups flour", "Instructions", "Bake until done."])

    started = time.perf_counter()
    parsed = main.parse_social_caption_recipe(text, source_url="image://upload/scan.png", title_hint="")
    elapsed = time.perf_counter() - started

    assert elapsed < 1.0
    assert "Ingredients" not in parsed["title"]


def test_parse_pasted_recipe_text_bounds_oversized_metadata_lines():
    raw_text = "\n".join(
        [
            "Weeknight Soup",
            "Servings: " + ("4 " * 3000),
            "Prep Time: 15 minutes",
            "Ingredients",
            "1 cup broth",
            "Instructions",
            "Simmer gently.",
        ]
    )

    started = time.perf_counter()
    parsed = main._parse_pasted_recipe_text(raw_text)
    elapsed = time.perf_counter() - started

    assert elapsed < 1.0
    assert parsed["title"] == "Weeknight Soup"
    assert parsed["prep_time"] == "15 minutes"
    assert parsed["ingredients"] == ["1 cup broth"]
