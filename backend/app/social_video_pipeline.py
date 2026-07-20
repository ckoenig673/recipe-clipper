from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


class YtDlpExtractError(RuntimeError):
    """Raised when yt-dlp fails while extracting/downloading social video metadata."""


class TranscriptPipelineStageError(RuntimeError):
    """Raised when a transcript pipeline stage fails."""

    def __init__(self, stage: str, exc: Exception):
        self.stage = stage
        self.reason = f"transcript_pipeline_failed:{stage}"
        super().__init__(f"{self.reason}: {exc}")


@dataclass
class TranscriptPipelineResult:
    transcript_text: str
    cleaned_transcript_text: str
    structured_recipe: dict
    mentioned_websites: list[str]
    title_inferred: bool
    measurements_partial: bool
    success: bool = True
    fallback_reason: str = ""
    failure_stage: str = ""


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _extract_urls(text: str) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []
    for match in re.finditer(r"\b(?:https?://)?(?:www\.)?[a-z0-9][a-z0-9\-]{0,62}(?:\.[a-z0-9][a-z0-9\-]{0,62})+\b", text or "", re.IGNORECASE):
        candidate = match.group(0).strip().strip(".,)")
        if not candidate:
            continue
        if "://" not in candidate:
            candidate = f"https://{candidate}"
        if candidate in seen:
            continue
        seen.add(candidate)
        results.append(candidate)
    return results


def _as_string_list(value) -> list[str]:
    if isinstance(value, list):
        return [_clean_text(item) for item in value if _clean_text(item)]
    return []


_PROMO_PATTERNS = [
    r"\b(?:follow|like|share|subscribe|comment|dm|inbox)\b",
    r"\b(?:link in bio|shop(?: now)?|order now|available at)\b",
    r"\b(?:walmart|target|costco|kroger|publix|whole foods)\b",
]
_SERVING_CHATTER_PATTERNS = [
    r"\b(?:serves?|servings?|feeds?)\s+\d+\b",
    r"\b(?:perfect for|great for)\s+(?:a\s+)?(?:crowd|party|family)\b",
]
_NOISY_INGREDIENT_PHRASES = [
    r"\bfrom\s+\w+\b",
    r"\bbrand(?:ed)?\b",
    r"\bname\s*brand\b",
]
_SERVING_ONLY_INGREDIENT_RE = re.compile(
    r"^(?:for\s+serving|to\s+serve|serve\s+with|optional\s+garnish)\b",
    re.IGNORECASE,
)
_BRAND_PREFIX_RE = re.compile(
    r"^(?:[a-z][a-z']+\s+){1,2}(?=(?:worcestershire sauce|cornbread mix|bread|stock|broth|sauce|seasoning)\b)",
    re.IGNORECASE,
)
_MEASUREMENT_RE = re.compile(
    r"\b(\d+(?:\s+\d+/\d+|/\d+|(?:\.\d+)?)?)\s*"
    r"(pounds?|lbs?|ounces?|oz|cups?|tablespoons?|tbsp|teaspoons?|tsp|cans?|packs?|packages?|pkgs?)\s+"
    r"([a-z][a-z\s\-]{2,60}?)(?=[,.;]| and | then | with |$)",
    re.IGNORECASE,
)
_SALT_RE = re.compile(r"\bkosher salt\b|\bsea salt\b|\bsalt\b", re.IGNORECASE)
_BLACK_PEPPER_RE = re.compile(r"\bblack pepper\b|\bfreshly ground pepper\b", re.IGNORECASE)
_FINISHING_GARNISH_RE = re.compile(
    r"\b(?:finish|finished|garnish|top|topped|sprinkle|sprinkled)\b[^.]{0,80}\bwith\s+([a-z][a-z\s\-]{2,40})",
    re.IGNORECASE,
)


def clean_transcript_for_recipe(transcript_text: str) -> str:
    text = str(transcript_text or "")
    text = re.sub(r"(?:\+?1[\s\-.]?)?(?:\(?\d{3}\)?[\s\-.]?)\d{3}[\s\-.]?\d{4}", " ", text)
    for pattern in _PROMO_PATTERNS + _SERVING_CHATTER_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def standardize_ingredient_name(value: str) -> str:
    text = _clean_text(value).lower()
    text = re.sub(r"[{}[\]\"]", " ", text)
    text = re.sub(r"\b(?:name|ingredient|item)\s*:\s*", " ", text)
    for pattern in _NOISY_INGREDIENT_PHRASES:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    text = re.sub(_BRAND_PREFIX_RE, "", text).strip()
    text = re.sub(r"\b(?:organic|fresh|premium|best)\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" ,.-")
    return text


def _split_joined_ingredient(text: str) -> list[str]:
    cleaned = standardize_ingredient_name(text)
    if not cleaned:
        return []
    match = re.match(r"^(?P<prefix>a\s+few\s+sprigs\s+of)\s+(?P<a>[a-z ]+?)\s+and\s+(?P<b>[a-z ]+)$", cleaned)
    if match:
        prefix = _clean_text(match.group("prefix"))
        left = _clean_text(match.group("a"))
        right = _clean_text(match.group("b"))
        return [f"{prefix} {left}".strip(), f"{prefix} {right}".strip()]
    match = re.match(r"^(?P<a>rosemary|thyme)\s+and\s+(?P<b>rosemary|thyme)$", cleaned)
    if match:
        return [match.group("a"), match.group("b")]
    return [cleaned]


def _clean_instruction_steps(ai_instructions: list[str]) -> list[str]:
    cleaned_steps: list[str] = []
    for step in ai_instructions or []:
        line = _clean_text(step)
        if not line:
            continue
        line = re.sub(r"^\d+[\).\s-]*", "", line).strip()
        line = re.sub(r"\s+", " ", line).strip(" -")
        if not line:
            continue
        line = line[0].upper() + line[1:]
        if line[-1] not in ".!?":
            line = f"{line}."
        cleaned_steps.append(line)
    return cleaned_steps


def _extract_measured_ingredients_from_transcript(transcript_text: str) -> list[str]:
    measured: list[str] = []
    for match in _MEASUREMENT_RE.finditer(transcript_text or ""):
        qty = _clean_text(match.group(1))
        unit = _clean_text(match.group(2))
        ingredient = standardize_ingredient_name(match.group(3))
        if ingredient:
            measured.append(f"{qty} {unit} {ingredient}".strip())
    return measured


def _extract_conservative_finishing_garnish(transcript_text: str) -> list[str]:
    garnish: list[str] = []
    seen: set[str] = set()
    for match in _FINISHING_GARNISH_RE.finditer(transcript_text or ""):
        candidate = standardize_ingredient_name(match.group(1))
        candidate = re.sub(r"\b(?:before|for)\s+serving\b", "", candidate, flags=re.IGNORECASE).strip(" ,.-")
        if not candidate:
            continue
        if len(candidate.split()) > 5:
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        garnish.append(candidate)
    return garnish


def merge_and_clean_ingredients(ai_ingredients: list[str], transcript_text: str) -> tuple[list[str], bool]:
    merged: list[str] = []
    seen_index: dict[str, int] = {}
    measured = _extract_measured_ingredients_from_transcript(transcript_text)
    candidates = [str(item) for item in (ai_ingredients or []) if _clean_text(item)]
    candidates.extend(measured)
    candidates.extend(_extract_conservative_finishing_garnish(transcript_text))
    transcript_has_salt = bool(_SALT_RE.search(transcript_text or ""))
    transcript_has_black_pepper = bool(_BLACK_PEPPER_RE.search(transcript_text or ""))

    for raw in candidates:
        if _SERVING_ONLY_INGREDIENT_RE.search(_clean_text(raw)):
            continue
        for normalized_raw in _split_joined_ingredient(str(raw)):
            if not normalized_raw:
                continue
            if _SERVING_ONLY_INGREDIENT_RE.search(normalized_raw):
                continue
            if "holy trinity" in normalized_raw:
                expansions = ["onion", "bell pepper", "celery"]
                for exp in expansions:
                    if exp not in seen_index:
                        seen_index[exp] = len(merged)
                        merged.append(exp)
                continue
            key = re.sub(r"^\d+(?:\s+\d+/\d+|/\d+|(?:\.\d+)?)\s+[a-z]+\s+", "", normalized_raw).strip()
            if not key:
                key = normalized_raw
            existing_idx = seen_index.get(key)
            if existing_idx is None:
                seen_index[key] = len(merged)
                merged.append(normalized_raw)
                continue
            existing = merged[existing_idx]
            if not re.search(r"\d", existing) and re.search(r"\d", normalized_raw):
                merged[existing_idx] = normalized_raw

    merged_lower = [item.lower() for item in merged]
    if transcript_has_salt and not any("salt" in item for item in merged_lower):
        merged.append("salt")
    if transcript_has_black_pepper and not any("black pepper" in item or item.strip() == "pepper" for item in merged_lower):
        merged.append("black pepper")

    measurements_partial = any(re.search(r"\d", item) for item in merged)
    return merged, measurements_partial


def collect_candidate_websites(transcript_text: str, metadata: dict, structured_recipe: dict | None = None) -> list[str]:
    chunks: list[str] = [transcript_text or ""]
    source_payloads = [metadata or {}, structured_recipe or {}]
    for source in source_payloads:
        for key in ("description", "title", "fulltitle", "webpage_url", "original_url"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                chunks.append(value)
        for item in source.get("mentioned_websites", []) or []:
            if isinstance(item, str) and item.strip():
                chunks.append(item)
    return _extract_urls("\n".join(chunks))


def _size_mb(file_path: str) -> float:
    try:
        return round(os.path.getsize(file_path) / (1024 * 1024), 3)
    except OSError:
        return 0.0


def _size_bytes(file_path: str) -> int:
    try:
        return os.path.getsize(file_path)
    except OSError:
        return 0


class _YtDlpStructuredLogger:
    def debug(self, msg: str) -> None:
        # yt-dlp emits progress via debug() with [download] prefixes; suppress that noise.
        if msg and "download" not in msg.lower():
            logger.debug("social_transcript_ytdlp_debug message=%s", msg)

    def info(self, msg: str) -> None:
        # Keep regular chatter suppressed for concise pipeline logs.
        return

    def warning(self, msg: str) -> None:
        logger.warning("social_transcript_ytdlp_warning message=%s", msg)

    def error(self, msg: str) -> None:
        logger.error("social_transcript_ytdlp_error message=%s", msg)


def _get_ytdlp_cookie_retry_config() -> tuple[str | None, str | None]:
    """Optional cookie-backed retry config for yt-dlp."""
    cookies_from_browser = os.getenv("SOCIAL_VIDEO_YTDLP_COOKIES_FROM_BROWSER", "").strip() or None
    return cookies_from_browser, None


def _with_ytdlp_auth_options(base_options: dict, *, cookies_from_browser: str | None, cookies_file: str | None) -> dict:
    options = dict(base_options)
    if cookies_from_browser:
        options["cookiesfrombrowser"] = (cookies_from_browser,)
    if cookies_file:
        options["cookiefile"] = cookies_file
    return options


def _attempt_ytdlp_metadata_and_download(source_url: str, options: dict, mode: str) -> tuple[dict, str]:
    import yt_dlp

    logger.info("social_transcript_ytdlp_attempt mode=%s", mode)
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(source_url, download=False) or {}
        downloaded_info = ydl.extract_info(source_url, download=True) or info
        downloaded_path = ydl.prepare_filename(downloaded_info)
    logger.info("social_transcript_ytdlp_attempt_succeeded mode=%s", mode)
    return info, downloaded_path


def download_social_media_with_ytdlp(source_url: str, work_dir: str, *, facebook_cookie: str | None = None) -> tuple[dict, str]:
    output_template = str(Path(work_dir) / "media.%(ext)s")
    base_options = {
        "quiet": False,
        "no_warnings": False,
        "noprogress": True,
        "noplaylist": True,
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "logger": _YtDlpStructuredLogger(),
    }
    retry_cookies_from_browser, retry_cookies_file = _get_ytdlp_cookie_retry_config()
    cookie_file_path: str | None = None
    if facebook_cookie:
        cookie_file_path = str(Path(work_dir) / "facebook-cookie.txt")
        Path(cookie_file_path).write_text(facebook_cookie, encoding="utf-8")
        retry_cookies_file = cookie_file_path
    logger.info(
        "social_transcript_cookie_source user_db=%s env_file=%s",
        bool(facebook_cookie),
        bool(retry_cookies_file and retry_cookies_file != cookie_file_path),
    )
    logger.info("social_transcript_stage_a_start source_url=%s", source_url)
    started_at = time.monotonic()
    downloaded_path = ""
    last_exc: Exception | None = None

    attempts: list[tuple[str, dict]] = [("anonymous", _with_ytdlp_auth_options(base_options, cookies_from_browser=None, cookies_file=None))]
    if retry_cookies_from_browser or retry_cookies_file:
        attempts.append(
            (
                "cookie_retry",
                _with_ytdlp_auth_options(
                    base_options,
                    cookies_from_browser=retry_cookies_from_browser,
                    cookies_file=retry_cookies_file,
                ),
            )
        )

    try:
        for mode, options in attempts:
            try:
                info, downloaded_path = _attempt_ytdlp_metadata_and_download(source_url, options, mode)
                break
            except Exception as exc:
                logger.warning("social_transcript_ytdlp_attempt_failed mode=%s", mode)
                last_exc = exc
        else:
            raise last_exc or RuntimeError("yt_dlp_extract_failed")
    except Exception as exc:
        raise YtDlpExtractError(str(exc) or "yt_dlp_extract_failed_missing_or_expired_cookie") from exc
    finally:
        if cookie_file_path:
            try:
                Path(cookie_file_path).unlink(missing_ok=True)
            except Exception:
                logger.warning("social_transcript_cookie_cleanup_failed")
    logger.info(
        "social_transcript_stage_a_done source_url=%s media_path=%s media_mb=%.3f elapsed_s=%.3f",
        source_url,
        downloaded_path,
        _size_mb(downloaded_path),
        time.monotonic() - started_at,
    )
    return info, downloaded_path


def download_social_media_via_processor(source_url: str, *, downloader_url: str, facebook_cookie: str | None = None) -> tuple[dict, str]:
    logger.info("social_downloader_request_started source_url=%s cookie_provided=%s", source_url, bool(facebook_cookie))
    started_at = time.monotonic()
    response = requests.post(
        downloader_url,
        json={"url": source_url, "facebook_cookie": facebook_cookie or None},
        timeout=600,
    )
    response.raise_for_status()
    payload_raw = response.json()
    payload = payload_raw if isinstance(payload_raw, dict) else {}
    if not payload.get("success"):
        raise YtDlpExtractError(str(payload.get("error") or "download_failed"))
    media_path = str(payload.get("media_path") or "").strip()
    info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
    if not media_path:
        raise YtDlpExtractError("missing_media_path")
    logger.info(
        "social_downloader_request_succeeded media_path=%s elapsed_s=%.3f",
        media_path,
        time.monotonic() - started_at,
    )
    return info, media_path


def extract_audio_to_wav(media_path: str, wav_path: str, ffmpeg_bin: str = "ffmpeg") -> str:
    logger.info("social_transcript_stage_b_start media_path=%s", media_path)
    started_at = time.monotonic()
    subprocess.run(
        [ffmpeg_bin, "-y", "-i", media_path, "-ac", "1", "-ar", "16000", wav_path],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    logger.info(
        "social_transcript_stage_b_done media_path=%s wav_path=%s audio_mb=%.3f elapsed_s=%.3f",
        media_path,
        wav_path,
        _size_mb(wav_path),
        time.monotonic() - started_at,
    )
    return wav_path


def transcribe_audio_with_faster_whisper(audio_path: str, model_size: str, device: str, compute_type: str) -> str:
    from faster_whisper import WhisperModel

    logger.info("social_transcript_stage_c_start audio_path=%s model=%s device=%s compute_type=%s", audio_path, model_size, device, compute_type)
    started_at = time.monotonic()
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    segments, _ = model.transcribe(audio_path)
    transcript = " ".join(_clean_text(segment.text) for segment in segments if _clean_text(segment.text)).strip()
    logger.info(
        "social_transcript_stage_c_done audio_path=%s transcript_chars=%d elapsed_s=%.3f",
        audio_path,
        len(transcript),
        time.monotonic() - started_at,
    )
    return transcript


def transcribe_audio_via_processor(audio_path: str, *, whisper_processor_url: str, model_size: str, device: str, compute_type: str) -> str:
    logger.info(
        "social_transcript_stage_c_processor_start audio_path=%s model=%s device=%s compute_type=%s",
        audio_path,
        model_size,
        device,
        compute_type,
    )
    started_at = time.monotonic()
    response = requests.post(
        whisper_processor_url,
        json={
            "audio_path": audio_path,
            "model_size": model_size,
            "device": device,
            "compute_type": compute_type,
        },
        timeout=600,
    )
    response.raise_for_status()
    payload_raw = response.json()
    payload = payload_raw if isinstance(payload_raw, dict) else {}
    if not payload.get("success"):
        raise RuntimeError(str(payload.get("error") or "whisper_processor_failed"))
    transcript = _clean_text(payload.get("transcript") or "")
    logger.info(
        "social_transcript_stage_c_processor_done audio_path=%s transcript_chars=%d elapsed_s=%.3f",
        audio_path,
        len(transcript),
        time.monotonic() - started_at,
    )
    return transcript


def save_transcript_debug(transcript_text: str, debug_dir: str | None) -> None:
    if not debug_dir:
        return
    try:
        Path(debug_dir).mkdir(parents=True, exist_ok=True)
        debug_file = Path(debug_dir) / "latest_social_transcript.txt"
        debug_file.write_text(transcript_text, encoding="utf-8")
        logger.info("social_transcript_stage_c_debug_saved path=%s", str(debug_file))
    except Exception as exc:
        logger.info("social_transcript_stage_c_debug_save_failed reason=%s", exc)


def _is_retryable_ollama_error(exc: Exception) -> bool:
    if isinstance(exc, requests.exceptions.ReadTimeout):
        return True
    if isinstance(exc, requests.exceptions.HTTPError):
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        return isinstance(status_code, int) and 500 <= status_code <= 599
    return False


def classify_transcript_recipe_relevance_with_ollama(
    transcript_text: str,
    transcript_metadata: dict,
    ollama_base_url: str,
    ollama_model: str,
    ollama_timeout_seconds: int,
    max_transcript_chars: int,
) -> bool:
    clipped_transcript = (transcript_text or "")[:max_transcript_chars]
    metadata_title = _clean_text((transcript_metadata or {}).get("title") or (transcript_metadata or {}).get("fulltitle") or "")
    metadata_description = _clean_text((transcript_metadata or {}).get("description") or "")
    prompt = (
        "Determine whether this social-media video transcript is primarily describing a cookable recipe. "
        "Return strict JSON with exactly one boolean key named recipe_related. "
        "Return false for restaurant reviews, lifestyle chatter, product promotion, or general food talk without a cookable recipe.\n\n"
        f"Video metadata title: {metadata_title}\n"
        f"Video metadata description: {metadata_description}\n\n"
        "Transcript:\n\n"
        f"{clipped_transcript}"
    )
    logger.info("social_transcript_stage_d1_start transcript_chars=%d", len(clipped_transcript))
    started_at = time.monotonic()
    try:
        response = requests.post(
            f"{ollama_base_url.rstrip('/')}/api/generate",
            json={
                "model": ollama_model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0},
            },
            timeout=ollama_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        raw_response = payload.get("response")
        if isinstance(raw_response, str):
            cleaned = raw_response.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE).strip()
                cleaned = re.sub(r"\s*```$", "", cleaned).strip()
            parsed = json.loads(cleaned)
        elif isinstance(raw_response, dict):
            parsed = raw_response
        else:
            raise ValueError("invalid_ollama_transcript_classifier_response")
        recipe_related = bool(parsed.get("recipe_related")) if isinstance(parsed, dict) else False
        logger.info(
            "social_transcript_stage_d1_done transcript_chars=%d recipe_related=%s elapsed_s=%.3f",
            len(clipped_transcript),
            recipe_related,
            time.monotonic() - started_at,
        )
        return recipe_related
    except Exception as exc:
        raise TranscriptPipelineStageError("ai_classification", exc) from exc


def structure_recipe_from_transcript_with_ollama(
    transcript_text: str,
    transcript_metadata: dict,
    ollama_base_url: str,
    ollama_model: str,
    ollama_timeout_seconds: int,
    max_transcript_chars: int,
) -> dict:
    clipped_transcript = (transcript_text or "")[:max_transcript_chars]
    candidate_sites = collect_candidate_websites(clipped_transcript, transcript_metadata, None)
    metadata_title = _clean_text((transcript_metadata or {}).get("title") or (transcript_metadata or {}).get("fulltitle") or "")
    metadata_description = _clean_text((transcript_metadata or {}).get("description") or "")
    sites_text = "\\n".join(f"- {site}" for site in candidate_sites) if candidate_sites else "- none found"
    prompt = (
        "You are extracting a recipe from a social-media video transcript. "
        "Return strict JSON with keys: title, ingredients, instructions, mentioned_websites. "
        "Use arrays for ingredients/instructions/mentioned_websites and empty values when unknown. "
        "Rules: keep ingredients/instructions readable; keep cooking order; preserve explicit measurements/units exactly as spoken; never invent amounts/times/temperatures. "
        "Do not normalize away grams, ml, cloves, sticks, cups, tablespoons, teaspoons, or temperatures. "
        "If salt is clearly used, include salt even without quantity. If black pepper is clearly used, include black pepper even without quantity. "
        "A finishing garnish may be included only when clearly applied to the final dish; do not invent garnish quantities. "
        "Exclude social outro/promo chatter and non-recipe commentary. "
        "Do not over-compress steps; keep concise but cookable instructions. "
        "Normalize brand-heavy names to common ingredient names unless brand is essential. "
        "Split clearly merged herbs (example: rosemary and thyme) into separate ingredients where appropriate. "
        "Expand holy trinity as onion, bell pepper, celery. "
        "Use a clean recipe title without social noise.\n\n"
        f"Video metadata title: {metadata_title}\n"
        f"Video metadata description: {metadata_description}\n"
        f"Candidate websites/domains:\n{sites_text}\n\n"
        "Transcript:\n\n"
        f"{clipped_transcript}"
    )
    logger.info("social_transcript_stage_d_start transcript_chars=%d", len(clipped_transcript))
    started_at = time.monotonic()
    for attempt in range(2):
        try:
            response = requests.post(
                f"{ollama_base_url.rstrip('/')}/api/generate",
                json={
                    "model": ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0},
                },
                timeout=ollama_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            raw_response = payload.get("response")
            if isinstance(raw_response, str):
                response_length = len(raw_response)
            elif isinstance(raw_response, dict):
                response_length = len(json.dumps(raw_response))
            else:
                response_length = 0
            logger.info("ollama_response_length=%s", response_length)
            if isinstance(raw_response, str):
                cleaned = raw_response.strip()
                if cleaned.startswith("```"):
                    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE).strip()
                    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
                parsed = json.loads(cleaned)
            elif isinstance(raw_response, dict):
                parsed = raw_response
            else:
                raise ValueError("invalid_ollama_transcript_response")
            logger.info("social_transcript_stage_d_done transcript_chars=%d elapsed_s=%.3f", len(clipped_transcript), time.monotonic() - started_at)
            return parsed if isinstance(parsed, dict) else {}
        except Exception as exc:
            is_last_attempt = attempt == 1
            if is_last_attempt or not _is_retryable_ollama_error(exc):
                raise TranscriptPipelineStageError("ai_extraction", exc) from exc
            logger.warning(
                "social_transcript_stage_d_retry reason=%s attempt=%d",
                str(exc),
                attempt + 1,
            )
    raise RuntimeError("ollama_recipe_parsing_failed")


def run_social_video_transcript_pipeline(
    source_url: str,
    *,
    ollama_base_url: str,
    ollama_model: str,
    ollama_timeout_seconds: int,
    facebook_cookie: str | None = None,
) -> TranscriptPipelineResult:
    work_root = os.getenv("SOCIAL_VIDEO_TMP_DIR", "/tmp/recipe-clipper-social")
    whisper_model = os.getenv("SOCIAL_VIDEO_WHISPER_MODEL", "small")
    whisper_device = os.getenv("SOCIAL_VIDEO_WHISPER_DEVICE", "cpu")
    whisper_compute_type = os.getenv("SOCIAL_VIDEO_WHISPER_COMPUTE_TYPE", "int8")
    ffmpeg_bin = os.getenv("SOCIAL_VIDEO_FFMPEG_BIN", "ffmpeg")
    transcript_debug_dir = os.getenv("SOCIAL_VIDEO_TRANSCRIPT_DEBUG_DIR", "").strip() or None
    max_transcript_chars = int(os.getenv("SOCIAL_VIDEO_MAX_TRANSCRIPT_CHARS", "12000"))
    Path(work_root).mkdir(parents=True, exist_ok=True)
    social_downloader_url = os.getenv("SOCIAL_DOWNLOADER_URL", "").strip()
    whisper_processor_url = os.getenv("WHISPER_PROCESSOR_URL", "").strip()

    pipeline_started_at = time.monotonic()
    with tempfile.TemporaryDirectory(dir=work_root) as tmp_dir:
        logger.info("transcript_stage=start yt_dlp_download")
        try:
            if social_downloader_url:
                info, media_path = download_social_media_via_processor(
                    source_url,
                    downloader_url=social_downloader_url,
                    facebook_cookie=facebook_cookie,
                )
            else:
                info, media_path = download_social_media_with_ytdlp(source_url, tmp_dir, facebook_cookie=facebook_cookie)
            logger.info("transcript_stage=success yt_dlp_download")
            logger.info("video_file size=%s path=%s", _size_bytes(media_path), media_path)
        except Exception as exc:
            logger.error("transcript_stage=failed yt_dlp_download error=%s", str(exc))
            raise TranscriptPipelineStageError("ytdlp", exc) from exc

        wav_path = str(Path(tmp_dir) / "audio_16k.wav")
        logger.info("transcript_stage=start ffmpeg_audio_extraction")
        try:
            extract_audio_to_wav(media_path, wav_path, ffmpeg_bin=ffmpeg_bin)
            logger.info("transcript_stage=success ffmpeg_audio_extraction")
            logger.info("audio_file size=%s path=%s", _size_bytes(wav_path), wav_path)
        except Exception as exc:
            logger.error("transcript_stage=failed ffmpeg_audio_extraction error=%s", str(exc))
            raise TranscriptPipelineStageError("ffmpeg", exc) from exc

        logger.info("transcript_stage=start whisper_transcription")
        try:
            if whisper_processor_url:
                transcript_text = transcribe_audio_via_processor(
                    wav_path,
                    whisper_processor_url=whisper_processor_url,
                    model_size=whisper_model,
                    device=whisper_device,
                    compute_type=whisper_compute_type,
                )
            else:
                transcript_text = transcribe_audio_with_faster_whisper(
                    wav_path,
                    model_size=whisper_model,
                    device=whisper_device,
                    compute_type=whisper_compute_type,
                )
            logger.info("transcript_stage=success whisper_transcription")
            logger.info("transcript_length=%s", len(transcript_text))
        except Exception as exc:
            logger.error("transcript_stage=failed whisper_transcription error=%s", str(exc))
            raise TranscriptPipelineStageError("whisper", exc) from exc

        save_transcript_debug(transcript_text, transcript_debug_dir)
        cleaned_transcript = clean_transcript_for_recipe(transcript_text)
        logger.info(
            "social_transcript_cleanup_complete source_url=%s original_chars=%d cleaned_chars=%d",
            source_url,
            len(transcript_text),
            len(cleaned_transcript),
        )
        logger.info("transcript_stage=start ai_recipe_classification")
        try:
            recipe_related = classify_transcript_recipe_relevance_with_ollama(
                cleaned_transcript,
                transcript_metadata=info,
                ollama_base_url=ollama_base_url,
                ollama_model=ollama_model,
                ollama_timeout_seconds=ollama_timeout_seconds,
                max_transcript_chars=max_transcript_chars,
            )
            logger.info("transcript_stage=success ai_recipe_classification recipe_related=%s", recipe_related)
        except TranscriptPipelineStageError as exc:
            logger.error("social_transcript_stage_d1_failed reason=%s", exc.reason)
            return TranscriptPipelineResult(
                transcript_text=transcript_text,
                cleaned_transcript_text=cleaned_transcript,
                structured_recipe={"ingredients": [], "instructions": [], "title": None},
                mentioned_websites=[],
                title_inferred=False,
                measurements_partial=False,
                success=False,
                fallback_reason=f"transcript_pipeline_failed:{exc.stage}",
                failure_stage=exc.stage,
            )

        if not recipe_related:
            logger.info("transcript_stage=failed ai_recipe_classification reason=not_recipe_related")
            return TranscriptPipelineResult(
                transcript_text=transcript_text,
                cleaned_transcript_text=cleaned_transcript,
                structured_recipe={"ingredients": [], "instructions": [], "title": None},
                mentioned_websites=[],
                title_inferred=False,
                measurements_partial=False,
                success=False,
                fallback_reason="transcript_pipeline_failed:ai_classification_not_recipe_related",
                failure_stage="ai_classification",
            )

        logger.info("transcript_stage=start ai_recipe_extraction")
        try:
            structured = structure_recipe_from_transcript_with_ollama(
                cleaned_transcript,
                transcript_metadata=info,
                ollama_base_url=ollama_base_url,
                ollama_model=ollama_model,
                ollama_timeout_seconds=ollama_timeout_seconds,
                max_transcript_chars=max_transcript_chars,
            )
            logger.info("transcript_stage=success ai_recipe_extraction")
        except TranscriptPipelineStageError as exc:
            logger.error(
                "social_transcript_stage_d_failed reason=%s",
                exc.reason,
            )
            return TranscriptPipelineResult(
                transcript_text=transcript_text,
                cleaned_transcript_text=cleaned_transcript,
                structured_recipe={"ingredients": [], "instructions": [], "title": None},
                mentioned_websites=[],
                title_inferred=False,
                measurements_partial=False,
                success=False,
                fallback_reason=f"transcript_pipeline_failed:{exc.stage}",
                failure_stage=exc.stage,
            )
        merged_ingredients, measurements_partial = merge_and_clean_ingredients(
            _as_string_list(structured.get("ingredients")),
            transcript_text,
        )
        structured["ingredients"] = merged_ingredients
        structured["instructions"] = _clean_instruction_steps(_as_string_list(structured.get("instructions")))
        title_inferred = not bool(_clean_text(structured.get("title")))

    recovery_started_at = time.monotonic()
    websites = collect_candidate_websites(transcript_text, info, structured)
    logger.info(
        "social_transcript_stage_e_done source_url=%s recovered_url=%s elapsed_s=%.3f",
        source_url,
        websites[0] if websites else "",
        time.monotonic() - recovery_started_at,
    )

    logger.info(
        "social_transcript_pipeline_complete source_url=%s media_mb=%.3f audio_mb=%.3f transcript_chars=%d total_elapsed_s=%.3f",
        source_url,
        _size_mb(media_path),
        _size_mb(wav_path),
        len(transcript_text),
        time.monotonic() - pipeline_started_at,
    )

    return TranscriptPipelineResult(
        transcript_text=transcript_text,
        cleaned_transcript_text=cleaned_transcript,
        structured_recipe=structured,
        mentioned_websites=websites,
        title_inferred=title_inferred,
        measurements_partial=measurements_partial,
    )
