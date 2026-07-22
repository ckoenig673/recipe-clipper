import sys
import types

import pytest

from backend.app.social_video_pipeline import (
    _clean_instruction_steps,
    clean_transcript_for_recipe,
    download_social_media_with_ytdlp,
    merge_and_clean_ingredients,
)
from backend.app.hostname_matching import hostname_matches_domain


def test_clean_transcript_for_recipe_removes_phone_and_promo_chatter():
    raw = "Call me at 555-111-2222, follow for more, and serves 8 people. Add onions and garlic."
    cleaned = clean_transcript_for_recipe(raw)
    assert "555-111-2222" not in cleaned
    assert "follow" not in cleaned.lower()
    assert "serves 8" not in cleaned.lower()
    assert "Add onions and garlic." in cleaned


def test_merge_and_clean_ingredients_expands_holy_trinity_and_recovers_measurements():
    ai_ingredients = ["holy trinity", "chuck roast", "brown gravy mix"]
    transcript = "Use 3 pound chuck roast and 2 packs brown gravy mix."

    merged, measurements_partial = merge_and_clean_ingredients(ai_ingredients, transcript)

    assert measurements_partial is True
    assert merged[:3] == ["onion", "bell pepper", "celery"]
    assert "3 pound chuck roast" in merged
    assert "2 packs brown gravy mix" in merged


def test_merge_and_clean_ingredients_normalizes_brands_splits_herbs_and_drops_serving_only_items():
    ai_ingredients = [
        "liam perry worcestershire sauce",
        "a few sprigs of rosemary and thyme",
        "for serving bunny bread",
    ]
    transcript = "Add a few sprigs of rosemary and thyme with worcestershire sauce."

    merged, _ = merge_and_clean_ingredients(ai_ingredients, transcript)

    assert "worcestershire sauce" in merged
    assert "a few sprigs of rosemary" in merged
    assert "a few sprigs of thyme" in merged
    assert all("bunny bread" not in item for item in merged)


def test_clean_instruction_steps_builds_readable_sentence_steps():
    cleaned = _clean_instruction_steps(
        ["1) brown beef in oil", "then add onion and garlic", " simmer for 20 minutes "]
    )
    assert cleaned == [
        "Brown beef in oil.",
        "Then add onion and garlic.",
        "Simmer for 20 minutes.",
    ]


def test_merge_and_clean_ingredients_adds_salt_black_pepper_and_finishing_garnish_when_explicit():
    ai_ingredients = ["2 lb beef", "1 onion"]
    transcript = (
        "Season with salt and black pepper. "
        "Cook until tender. "
        "Finish with chopped chives before serving."
    )

    merged, _ = merge_and_clean_ingredients(ai_ingredients, transcript)

    assert "salt" in merged
    assert "black pepper" in merged
    assert "chopped chives" in merged


def test_merge_and_clean_ingredients_preserves_explicit_fraction_measurements_from_transcript():
    ai_ingredients = ["chicken broth", "rice"]
    transcript = "Add 1 1/2 cups chicken broth and 3/4 cup rice."

    merged, measurements_partial = merge_and_clean_ingredients(ai_ingredients, transcript)

    assert measurements_partial is True
    assert any(item.startswith("1 1/2 cups") for item in merged)
    assert "3/4 cup rice" in merged


def test_download_social_media_with_ytdlp_retries_with_cookie_auth(monkeypatch, tmp_path):
    attempts = []
    extract_calls = []

    class _FakeYoutubeDL:
        def __init__(self, options):
            self.options = options
            attempts.append(options)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, source_url, download):
            extract_calls.append((self.options, source_url, download))
            if not self.options.get("cookiesfrombrowser") and not self.options.get("cookiefile"):
                raise RuntimeError("anonymous failed")
            return {"id": "abc123", "ext": "m4a"}

        def prepare_filename(self, info):
            return str(tmp_path / f"media.{info.get('ext', 'bin')}")

    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=_FakeYoutubeDL))
    monkeypatch.setenv("SOCIAL_VIDEO_YTDLP_COOKIES_FROM_BROWSER", "firefox")
    monkeypatch.delenv("SOCIAL_VIDEO_YTDLP_COOKIES_FILE", raising=False)

    info, media_path = download_social_media_with_ytdlp("https://facebook.com/reel/123", str(tmp_path))

    assert info["id"] == "abc123"
    assert media_path.endswith("media.m4a")
    assert len(attempts) == 2
    assert attempts[0].get("cookiesfrombrowser") is None
    assert attempts[1]["cookiesfrombrowser"] == ("firefox",)
    assert [call[2] for call in extract_calls if call[0] is attempts[1]] == [False, True]


def test_download_social_media_with_ytdlp_uses_db_cookie_temp_file_and_cleans_up(monkeypatch, tmp_path):
    attempts = []
    cookie_path_holder = {"path": None}

    class _FakeYoutubeDL:
        def __init__(self, options):
            self.options = options
            attempts.append(options)
            if options.get("cookiefile"):
                cookie_path_holder["path"] = options["cookiefile"]
                cookie_domain = open(options["cookiefile"], "r", encoding="utf-8").read().split("\t", 1)[0]
                assert hostname_matches_domain(cookie_domain, "facebook.com")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, source_url, download):
            if not self.options.get("cookiefile"):
                raise RuntimeError("anonymous failed")
            return {"id": "abc123", "ext": "m4a"}

        def prepare_filename(self, info):
            return str(tmp_path / f"media.{info.get('ext', 'bin')}")

    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=_FakeYoutubeDL))
    monkeypatch.delenv("SOCIAL_VIDEO_YTDLP_COOKIES_FROM_BROWSER", raising=False)
    monkeypatch.delenv("SOCIAL_VIDEO_YTDLP_COOKIES_FILE", raising=False)

    info, media_path = download_social_media_with_ytdlp(
        "https://facebook.com/reel/123",
        str(tmp_path),
        facebook_cookie=".facebook.com\tTRUE\t/\tTRUE\t0\tc_user\t12345",
    )

    assert info["id"] == "abc123"
    assert media_path.endswith("media.m4a")
    assert len(attempts) == 2
    assert attempts[1]["cookiefile"].endswith("facebook-cookie.txt")
    assert cookie_path_holder["path"] is not None
    assert not (tmp_path / "facebook-cookie.txt").exists()


def test_download_social_media_with_ytdlp_ignores_legacy_cookie_file_env(monkeypatch, tmp_path):
    attempts = []

    class _FakeYoutubeDL:
        def __init__(self, options):
            self.options = options
            attempts.append(options)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, source_url, download):
            if not self.options.get("cookiefile"):
                raise RuntimeError("anonymous failed")
            return {"id": "abc123", "ext": "m4a"}

        def prepare_filename(self, info):
            return str(tmp_path / f"media.{info.get('ext', 'bin')}")

    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=_FakeYoutubeDL))
    monkeypatch.setenv("SOCIAL_VIDEO_YTDLP_COOKIES_FILE", "/app/data/cookies.txt")

    download_social_media_with_ytdlp(
        "https://facebook.com/reel/123",
        str(tmp_path),
        facebook_cookie=".facebook.com\tTRUE\t/\tTRUE\t0\tc_user\t12345",
    )

    assert len(attempts) == 2
    assert attempts[1]["cookiefile"].endswith("facebook-cookie.txt")


def test_download_social_media_via_processor_uses_configured_url_and_passes_cookie(monkeypatch):
    from backend.app import social_video_pipeline as pipeline

    captured = {}

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"success": True, "media_path": "/app/data/social-downloads/media.m4a", "info": {"id": "x1"}}

    def _fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr(pipeline.requests, "post", _fake_post)

    info, media_path = pipeline.download_social_media_via_processor(
        "https://facebook.com/reel/123",
        downloader_url="http://social:8790/download/social-video",
        facebook_cookie="SECRET_COOKIE",
    )

    assert info["id"] == "x1"
    assert media_path.endswith("media.m4a")
    assert captured["url"].endswith("/download/social-video")
    assert captured["json"]["facebook_cookie"] == "SECRET_COOKIE"


def test_download_social_media_via_processor_log_never_includes_raw_cookie(monkeypatch, caplog):
    from backend.app import social_video_pipeline as pipeline

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"success": True, "media_path": "/app/data/social-downloads/media.m4a", "info": {}}

    monkeypatch.setattr(pipeline.requests, "post", lambda *args, **kwargs: _Resp())

    secret_cookie = "VERY_SECRET_COOKIE_VALUE"
    pipeline.download_social_media_via_processor(
        "https://facebook.com/reel/123",
        downloader_url="http://social:8790/download/social-video",
        facebook_cookie=secret_cookie,
    )

    assert secret_cookie not in caplog.text


def test_transcribe_audio_via_processor_returns_transcript(monkeypatch):
    from backend.app import social_video_pipeline as pipeline

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"success": True, "transcript": "hello world"}

    monkeypatch.setattr(pipeline.requests, "post", lambda *args, **kwargs: _Resp())

    transcript = pipeline.transcribe_audio_via_processor(
        "/app/data/social-downloads/audio_16k.wav",
        whisper_processor_url="http://whisper:8791/transcribe",
        model_size="small",
        device="cpu",
        compute_type="int8",
    )

    assert transcript == "hello world"


def test_transcribe_audio_via_processor_failure_raises_clean_error(monkeypatch):
    from backend.app import social_video_pipeline as pipeline

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"success": False, "error": "processor unavailable", "stage": "whisper"}

    monkeypatch.setattr(pipeline.requests, "post", lambda *args, **kwargs: _Resp())

    with pytest.raises(RuntimeError, match="processor unavailable"):
        pipeline.transcribe_audio_via_processor(
            "/app/data/social-downloads/audio_16k.wav",
            whisper_processor_url="http://whisper:8791/transcribe",
            model_size="small",
            device="cpu",
            compute_type="int8",
        )


def test_pipeline_uses_whisper_processor_when_configured(monkeypatch):
    from backend.app import social_video_pipeline as pipeline

    monkeypatch.setenv("WHISPER_PROCESSOR_URL", "http://whisper:8791/transcribe")
    monkeypatch.setenv("SOCIAL_DOWNLOADER_URL", "")

    monkeypatch.setattr(pipeline, "download_social_media_with_ytdlp", lambda *a, **k: ({"title": "t"}, "/tmp/m.m4a"))
    monkeypatch.setattr(pipeline, "extract_audio_to_wav", lambda *a, **k: "/tmp/audio_16k.wav")
    monkeypatch.setattr(pipeline, "transcribe_audio_via_processor", lambda *a, **k: "spoken text")
    monkeypatch.setattr(pipeline, "transcribe_audio_with_faster_whisper", lambda *a, **k: (_ for _ in ()).throw(AssertionError("fallback should not be used")))
    monkeypatch.setattr(pipeline, "classify_transcript_recipe_relevance_with_ollama", lambda *a, **k: True)
    monkeypatch.setattr(pipeline, "structure_recipe_from_transcript_with_ollama", lambda *a, **k: {"ingredients": [], "instructions": [], "title": "x"})

    result = pipeline.run_social_video_transcript_pipeline(
        "https://facebook.com/reel/1",
        ollama_base_url="http://ollama",
        ollama_model="llama3",
        ollama_timeout_seconds=30,
    )
    assert result.transcript_text == "spoken text"


def test_pipeline_falls_back_to_local_whisper_when_processor_not_configured(monkeypatch):
    from backend.app import social_video_pipeline as pipeline

    monkeypatch.delenv("WHISPER_PROCESSOR_URL", raising=False)
    monkeypatch.setenv("SOCIAL_DOWNLOADER_URL", "")

    monkeypatch.setattr(pipeline, "download_social_media_with_ytdlp", lambda *a, **k: ({"title": "t"}, "/tmp/m.m4a"))
    monkeypatch.setattr(pipeline, "extract_audio_to_wav", lambda *a, **k: "/tmp/audio_16k.wav")
    monkeypatch.setattr(pipeline, "transcribe_audio_with_faster_whisper", lambda *a, **k: "local transcript")
    monkeypatch.setattr(pipeline, "transcribe_audio_via_processor", lambda *a, **k: (_ for _ in ()).throw(AssertionError("processor should not be used")))
    monkeypatch.setattr(pipeline, "classify_transcript_recipe_relevance_with_ollama", lambda *a, **k: True)
    monkeypatch.setattr(pipeline, "structure_recipe_from_transcript_with_ollama", lambda *a, **k: {"ingredients": [], "instructions": [], "title": "x"})

    result = pipeline.run_social_video_transcript_pipeline(
        "https://facebook.com/reel/1",
        ollama_base_url="http://ollama",
        ollama_model="llama3",
        ollama_timeout_seconds=30,
    )
    assert result.transcript_text == "local transcript"


def test_pipeline_skips_ai_extraction_when_classifier_says_not_recipe_related(monkeypatch):
    from backend.app import social_video_pipeline as pipeline

    monkeypatch.delenv("WHISPER_PROCESSOR_URL", raising=False)
    monkeypatch.setenv("SOCIAL_DOWNLOADER_URL", "")

    monkeypatch.setattr(pipeline, "download_social_media_with_ytdlp", lambda *a, **k: ({"title": "t"}, "/tmp/m.m4a"))
    monkeypatch.setattr(pipeline, "extract_audio_to_wav", lambda *a, **k: "/tmp/audio_16k.wav")
    monkeypatch.setattr(pipeline, "transcribe_audio_with_faster_whisper", lambda *a, **k: "this is a restaurant review and not a recipe")
    monkeypatch.setattr(pipeline, "classify_transcript_recipe_relevance_with_ollama", lambda *a, **k: False)
    monkeypatch.setattr(
        pipeline,
        "structure_recipe_from_transcript_with_ollama",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("extraction should be skipped")),
    )

    result = pipeline.run_social_video_transcript_pipeline(
        "https://facebook.com/reel/1",
        ollama_base_url="http://ollama",
        ollama_model="llama3",
        ollama_timeout_seconds=30,
    )

    assert result.success is False
    assert result.failure_stage == "ai_classification"
    assert result.fallback_reason == "transcript_pipeline_failed:ai_classification_not_recipe_related"
