from __future__ import annotations

from dataclasses import dataclass, field
from html import unescape
import json
import logging
import re
import time
from typing import Optional
from urllib.parse import parse_qs, unquote, urlparse

import requests

logger = logging.getLogger(__name__)

MOBILE_SAFARI_USER_AGENT = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"
MAX_REDIRECTS = 5

REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

SOCIAL_HOSTS = ("facebook.com", "fb.watch", "instagram.com", "instagr.am")
SOCIAL_INTERNAL_HOSTS = SOCIAL_HOSTS + ("l.facebook.com", "lm.facebook.com", "l.instagram.com", "fbcdn.net")
SOCIAL_DESTINATION_BLOCKED_HOSTS = ("wapforum.org", "w3.org", "schema.org", "ogp.me")
SOCIAL_DESTINATION_BLOCKED_HOST_KEYWORDS = ("schema", "opengraph", "xmlns", "dtd")
SOCIAL_DESTINATION_BLOCKED_PATH_TOKENS = (
    ".dtd",
    ".xsd",
    ".xml",
    "/dtd/",
    "/schema/",
    "/schemas/",
    "xhtml-mobile10",
)
SOCIAL_DESTINATION_ASSET_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".mp4",
    ".mov",
    ".webm",
    ".m3u8",
    ".mp3",
    ".wav",
    ".pdf",
    ".zip",
    ".css",
    ".js",
    ".json",
)
KNOWN_FOOD_DOMAINS = (
    "allrecipes.com",
    "foodnetwork.com",
    "delish.com",
    "seriouseats.com",
    "epicurious.com",
    "simplyrecipes.com",
    "thekitchn.com",
    "tastesbetterfromscratch.com",
    "sallysbakingaddiction.com",
    "natashaskitchen.com",
    "eatingwell.com",
)
ENABLE_HEADLESS_FALLBACK = True


@dataclass
class SocialResolutionResult:
    source: str
    canonical_url: Optional[str]
    resolved_url: Optional[str]
    method: Optional[str]
    post_id: Optional[str]
    error: Optional[str]
    headless_attempted: bool = False
    headless_candidate_urls: list[str] = field(default_factory=list)
    fast_path_candidate_urls: list[str] = field(default_factory=list)
    ytdlp_title: str = ""
    ytdlp_description: str = ""
    ytdlp_webpage_url: str = ""
    ytdlp_description_urls: list[str] = field(default_factory=list)


def _host_matches(host: str, candidates: tuple[str, ...]) -> bool:
    normalized = (host or "").lower().strip()
    if not normalized:
        return False
    return any(normalized == candidate or normalized.endswith(f".{candidate}") for candidate in candidates)


def _is_external_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    host = (parsed.netloc or "").lower().strip()
    return parsed.scheme in ("http", "https") and bool(host) and not _host_matches(host, SOCIAL_INTERNAL_HOSTS)


def _social_destination_rejection_reason(url: str) -> str:
    value = (url or "").strip()
    if not value:
        return "empty_url"
    lowered = value.lower()
    if lowered.startswith(("javascript:", "data:", "mailto:")):
        return "unsupported_scheme_prefix"
    try:
        parsed = urlparse(value)
    except Exception:
        return "urlparse_failed"
    if parsed.scheme not in ("http", "https"):
        return "unsupported_scheme"
    host = (parsed.netloc or "").lower().strip()
    if not host:
        return "missing_host"
    if _host_matches(host, SOCIAL_INTERNAL_HOSTS):
        return "social_internal_host"
    if _host_matches(host, SOCIAL_DESTINATION_BLOCKED_HOSTS):
        return "blocked_spec_host"
    if any(token in host for token in SOCIAL_DESTINATION_BLOCKED_HOST_KEYWORDS):
        return "spec_namespace_host"
    if any(token in host for token in ("cdn", "static", "img", "image", "media", "assets")):
        return "asset_host"
    path = (parsed.path or "").strip()
    if not path or path == "/":
        return "missing_real_path"
    lowered_path = path.lower()
    if any(token in lowered_path for token in SOCIAL_DESTINATION_BLOCKED_PATH_TOKENS):
        return "spec_or_schema_path"
    if any(lowered_path.endswith(extension) for extension in SOCIAL_DESTINATION_ASSET_EXTENSIONS):
        return "asset_or_media_path"
    if len(host.split(".")) < 2:
        return "invalid_host"
    return ""


def is_valid_social_destination_url(url: str) -> bool:
    return _social_destination_rejection_reason(url) == ""


def _strip_url_noise(value: str) -> str:
    cleaned = (value or "").strip().strip('"\'<>')
    while cleaned and cleaned[-1] in ".,);:!?]":
        cleaned = cleaned[:-1]
    return cleaned.strip()


def _decode_social_redirect(url: str) -> str:
    value = _strip_url_noise(url)
    if not value:
        return ""
    try:
        parsed = urlparse(value)
    except Exception:
        return value
    host = (parsed.netloc or "").lower().strip()
    params = parse_qs(parsed.query)
    if _host_matches(host, ("l.facebook.com", "lm.facebook.com", "l.instagram.com")):
        wrapped = (params.get("u") or [""])[0]
        if wrapped:
            return _strip_url_noise(unquote(unescape(wrapped)))
    if _host_matches(host, ("facebook.com", "m.facebook.com")) and parsed.path.startswith("/redirect/"):
        wrapped = (params.get("u") or [""])[0]
        if wrapped:
            return _strip_url_noise(unquote(unescape(wrapped)))
    return value


def _extract_url_candidates(html: str) -> list[str]:
    if not html:
        return []
    decoded_html = unescape(html)
    values: list[str] = []
    values.extend(
        unescape(match.group(1))
        for match in re.finditer(r'<a\b[^>]*href\s*=\s*["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    )
    values.extend(
        unescape(match.group(1))
        for match in re.finditer(
            r'<meta\b[^>]*property\s*=\s*["\']og:(?:url|description)["\'][^>]*content\s*=\s*["\']([^"\']+)["\']',
            html,
            flags=re.IGNORECASE,
        )
    )
    values.extend(
        unescape(match.group(1))
        for match in re.finditer(r'<meta\b[^>]*content\s*=\s*["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    )
    values.extend(
        match.group(0)
        for match in re.finditer(r"https?://[^\s\"'<>]+", decoded_html, flags=re.IGNORECASE)
    )
    values.extend(
        match.group(1)
        for match in re.finditer(
            r'(?:window\.__data|__NEXT_DATA__|application/ld\+json)[^<]*?(https?://[^\s\"\'<>]+)',
            decoded_html,
            flags=re.IGNORECASE,
        )
    )

    extracted: list[str] = []
    seen: set[str] = set()
    for value in values:
        decoded = _decode_social_redirect(value)
        candidate = _strip_url_noise(decoded)
        if not candidate:
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        extracted.append(candidate)
    return extracted


def _filter_external_candidates(candidates: list[str]) -> list[str]:
    filtered: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        decoded = _decode_social_redirect(candidate)
        cleaned = _strip_url_noise(decoded)
        if not cleaned:
            continue
        rejection = _social_destination_rejection_reason(cleaned)
        if rejection:
            logger.info("social-resolver candidate rejected url=%s reason=%s", cleaned, rejection)
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        filtered.append(cleaned)
        logger.info("social-resolver candidate accepted url=%s", cleaned)
    return filtered


def _candidate_score(url: str) -> float:
    lowered = url.lower()
    parsed = urlparse(url)
    path = (parsed.path or "").lower()
    host = (parsed.netloc or "").lower().strip()
    points = 0.0

    if "/recipe/" in path or "/recipes/" in path:
        points += 0.9
    elif any(fragment in path for fragment in ("/recipe-", "-recipe", "/food/", "/dish/", "/blog/")):
        points += 0.35

    if _host_matches(host, KNOWN_FOOD_DOMAINS):
        points += 0.45
    if any(token in host for token in ("recipe", "food", "kitchen", "cooking", "bake", "eat")):
        points += 0.15
    if any(token in lowered for token in ("ingredients", "instructions", "print-recipe")):
        points += 0.12

    if len(url) < 28:
        points -= 0.25
    if len(path) > 24:
        points += 0.1
    if any(token in host for token in ("bit.ly", "tinyurl.com", "t.co", "short.link", "buff.ly")):
        points -= 0.45
    if any(token in lowered for token in ("utm_", "fbclid=", "gclid=", "doubleclick", "tracking", "pixel")):
        points -= 0.4

    return round(points, 3)


def _is_tracking_url(url: str) -> bool:
    lowered = (url or "").lower()
    return any(
        token in lowered
        for token in ("utm_", "fbclid=", "gclid=", "doubleclick", "tracking", "pixel", "adservice")
    )


def _pick_best_candidate(candidates: list[str], threshold: float = 0.35) -> Optional[str]:
    if not candidates:
        return None
    ranked = sorted(((candidate, _candidate_score(candidate)) for candidate in candidates), key=lambda item: item[1], reverse=True)
    best_url, best_score = ranked[0]
    logger.info("social-resolver candidate_count=%d best_score=%.3f best_url=%s", len(candidates), best_score, best_url)
    if best_score < threshold:
        return None
    return best_url


def _pick_first_strong_candidate(candidates: list[str]) -> Optional[str]:
    for candidate in candidates:
        score = _candidate_score(candidate)
        if score >= 0.2 or any(token in candidate.lower() for token in ("/recipe/", "/recipes/", "recipe", "food")):
            return candidate
    return candidates[0] if candidates else None


def _fetch_url(url: str, retries: int = 3) -> tuple[str, str]:
    last_error: Exception | None = None
    session = requests.Session()
    session.max_redirects = MAX_REDIRECTS
    for attempt in range(1, retries + 1):
        headers = {**REQUEST_HEADERS, "User-Agent": MOBILE_SAFARI_USER_AGENT}
        try:
            response = session.get(url, allow_redirects=True, timeout=8, headers=headers)
            final_url = str(response.url or "").strip()
            logger.info("social-resolver fetch_success attempt=%d source_url=%s final_url=%s", attempt, url, final_url)
            return final_url, response.text or ""
        except Exception as exc:
            last_error = exc
            logger.info("social-resolver fetch_retry attempt=%d source_url=%s reason=%s", attempt, url, exc)
            if attempt < retries:
                time.sleep(min(0.9, 0.25 * attempt))
    raise RuntimeError(f"fetch_failed:{last_error}")


def _fetch_url_for_user_agent(url: str, user_agent: str) -> tuple[str, str]:
    headers = {**REQUEST_HEADERS, "User-Agent": user_agent}
    session = requests.Session()
    session.max_redirects = MAX_REDIRECTS
    response = session.get(url, allow_redirects=True, timeout=8, headers=headers)
    final_url = str(response.url or "").strip()
    logger.info("social-resolver fetch_user_agent source_url=%s final_url=%s", url, final_url)
    return final_url, response.text or ""


def _resolve_with_ytdlp(url: str) -> tuple[Optional[str], dict]:
    debug: dict[str, str | int | list[str]] = {
        "title": "",
        "description": "",
        "webpage_url": "",
        "description_urls": [],
    }
    logger.info("social_ytdlp_attempt source_url=%s", url)

    try:
        import yt_dlp
    except Exception as exc:
        logger.info("social_ytdlp_no_match source_url=%s reason=import_failed:%s", url, exc)
        return None, debug

    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "extract_flat": False,
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False) or {}
    except Exception as exc:
        logger.info("social_ytdlp_no_match source_url=%s reason=extract_failed:%s", url, exc)
        return None, debug

    if not isinstance(info, dict):
        logger.info("social_ytdlp_no_match source_url=%s reason=unexpected_payload", url)
        return None, debug

    entries = info.get("entries")
    if isinstance(entries, list) and entries and isinstance(entries[0], dict):
        info = entries[0]

    title = str(info.get("title") or "").strip()
    description = str(info.get("description") or "").strip()
    webpage_url = str(info.get("webpage_url") or info.get("original_url") or "").strip()
    debug["title"] = title
    debug["description"] = description
    debug["webpage_url"] = webpage_url
    if title:
        logger.info("social_ytdlp_title=%s", title[:180])
    else:
        logger.info("social_ytdlp_title=")

    description_urls = [
        _strip_url_noise(match.group(0))
        for match in re.finditer(r"https?://[^\s\"'<>]+", description, flags=re.IGNORECASE)
    ]
    debug["description_urls"] = description_urls[:10]
    logger.info("social_ytdlp_description_url_count=%d", len(description_urls))

    for candidate in description_urls:
        decoded = _strip_url_noise(_decode_social_redirect(candidate))
        if not decoded:
            continue
        rejection = _social_destination_rejection_reason(decoded)
        if rejection:
            logger.info("social-resolver candidate rejected url=%s reason=%s", decoded, rejection)
            continue
        logger.info("social-resolver candidate accepted url=%s", decoded)
        logger.info("social_ytdlp_success resolved_url=%s", decoded)
        return decoded, debug

    logger.info("social_ytdlp_no_match source_url=%s", url)
    return None, debug


def _extract_facebook_post_id(*sources: str) -> Optional[str]:
    patterns = [
        r"/reel/(\d{15,})",
        r"/reel/video/(\d{15,})",
        r"story_fbid=(\d{15,})",
        r"[?&]fbid=(\d{15,})",
        r'"videoID"\s*:\s*"?(\d{15,})"?',
        r'"reel_id"\s*:\s*"?(\d{15,})"?',
        r"\b(\d{15,})\b",
    ]

    for source in sources:
        text = unquote(source or "")
        if not text:
            continue
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                candidate = (match.group(1) or "").strip()
                if candidate.isdigit() and len(candidate) >= 15:
                    return candidate
    return None


def _canonicalize_instagram_url(url: str) -> Optional[str]:
    parsed = urlparse(url or "")
    path = re.sub(r"/+", "/", parsed.path or "")
    match = re.match(r"^/(reel|p|tv)/([A-Za-z0-9_-]+)", path)
    if not match:
        return None
    kind, code = match.groups()
    return f"https://www.instagram.com/{kind}/{code}/"


def _fetch_with_playwright(url: str) -> tuple[Optional[str], list[str]]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        logger.info("social-resolver headless_unavailable url=%s reason=%s", url, exc)
        return None, []

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(user_agent=MOBILE_SAFARI_USER_AGENT)
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(2500)
            html = page.content() or ""
            browser.close()
    except Exception as exc:
        logger.info("social-resolver headless_failed url=%s reason=%s", url, exc)
        return None, []

    rendered_html = unescape(html or "")
    collected: list[str] = []

    def add_candidates(values: list[str], stage: str) -> None:
        for value in values:
            decoded = _strip_url_noise(_decode_social_redirect(value))
            if not decoded:
                continue
            rejection = _social_destination_rejection_reason(decoded)
            if rejection:
                logger.info("social-resolver candidate rejected url=%s reason=%s", decoded, rejection)
                continue
            if decoded in collected:
                continue
            collected.append(decoded)
            logger.info("social-resolver candidate accepted url=%s stage=%s", decoded, stage)

    def meta_values_for_property(meta_property: str) -> list[str]:
        return [
            unescape(match.group(1))
            for match in re.finditer(
                rf'<meta\b[^>]*property\s*=\s*["\']{re.escape(meta_property)}["\'][^>]*content\s*=\s*["\']([^"\']+)["\']',
                html,
                flags=re.IGNORECASE,
            )
        ]

    # Stage A: Meta tag scan order must mirror the standalone script.
    add_candidates(meta_values_for_property("og:url"), "facebook_headless_meta_og_url_match")
    add_candidates(meta_values_for_property("og:description"), "facebook_headless_meta_og_description_match")
    og_title_values = meta_values_for_property("og:title")
    add_candidates(og_title_values, "facebook_headless_meta_og_title_match")
    for value in og_title_values:
        decoded = _strip_url_noise(_decode_social_redirect(value))
        rejection = _social_destination_rejection_reason(decoded)
        if not rejection:
            logger.info("facebook_headless_meta_og_title_match url=%s", decoded)
            return decoded, collected
        if decoded:
            logger.info("social-resolver candidate rejected url=%s reason=%s", decoded, rejection)

    # Stage B: JSON-LD scripts.
    add_candidates(
        [
            url_match.group(0)
            for script_match in re.finditer(
                r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                html,
                flags=re.IGNORECASE | re.DOTALL,
            )
            for url_match in re.finditer(
                r"https?://[^\s\"'<>]+",
                unescape(script_match.group(1)),
                flags=re.IGNORECASE,
            )
        ],
        "facebook_headless_jsonld_match",
    )
    # Stage C: Inline scripts.
    add_candidates(
        [
            url_match.group(0)
            for script_match in re.finditer(r"<script\b[^>]*>(.*?)</script>", html, flags=re.IGNORECASE | re.DOTALL)
            for url_match in re.finditer(
                r"https?://[^\s\"'<>]+",
                unescape(script_match.group(1)),
                flags=re.IGNORECASE,
            )
        ],
        "facebook_headless_script_match",
    )
    # Stage D: Anchor links.
    add_candidates(
        [
            unescape(match.group(1))
            for match in re.finditer(r'<a\b[^>]*href\s*=\s*["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
        ],
        "facebook_headless_anchor_match",
    )
    # Stage E: Raw rendered HTML URL regex.
    add_candidates(
        [match.group(0) for match in re.finditer(r"https?://[^\s\"'<>]+", rendered_html, flags=re.IGNORECASE)],
        "facebook_headless_raw_match",
    )

    selected = _pick_best_candidate(collected, threshold=0.2) or _pick_first_strong_candidate(collected)
    logger.info("social-resolver headless_complete url=%s candidate_count=%d selected=%s", url, len(collected), selected or "")
    return selected, collected


def _fetch_with_selenium(url: str) -> tuple[Optional[str], list[str]]:
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait
    except Exception as exc:
        logger.info("facebook_selenium_failed canonical_url=%s reason=%s", url, exc)
        return None, []

    driver = None
    try:
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument(f"--user-agent={MOBILE_SAFARI_USER_AGENT}")
        service = Service("/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(20)
        driver.get(url)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(2.0)

        html = driver.page_source or ""
    except Exception as exc:
        logger.info("facebook_selenium_failed canonical_url=%s reason=%s", url, exc)
        if driver:
            driver.quit()
        return None, []

    rendered_html = unescape(html)
    collected: list[str] = []

    def add_candidate(value: str, stage: str) -> Optional[str]:
        decoded = _strip_url_noise(_decode_social_redirect(value))
        if not decoded:
            return None
        rejection = _social_destination_rejection_reason(decoded)
        if rejection:
            logger.info("social-resolver candidate rejected url=%s reason=%s", decoded, rejection)
            return None
        if decoded not in collected:
            collected.append(decoded)
            logger.info("social-resolver candidate accepted url=%s stage=%s", decoded, stage)
        return decoded

    def meta_values(meta_property: str) -> list[str]:
        matches = re.finditer(
            rf'<meta\b[^>]*property\s*=\s*["\']{re.escape(meta_property)}["\'][^>]*content\s*=\s*["\']([^"\']+)["\']',
            html,
            flags=re.IGNORECASE,
        )
        return [unescape(match.group(1)) for match in matches]

    # Stage A: meta tags in required order.
    for value in meta_values("og:url"):
        add_candidate(value, "facebook_selenium_meta_og_url_match")
    for value in meta_values("og:description"):
        add_candidate(value, "facebook_selenium_meta_og_description_match")
    for value in meta_values("og:title"):
        matched = add_candidate(value, "facebook_selenium_meta_og_title_match")
        if matched:
            logger.info("facebook_selenium_meta_og_title_match url=%s", matched)
            driver.quit()
            return matched, collected

    # Stage B: JSON-LD scripts.
    for script_match in re.finditer(
        r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        script_content = unescape(script_match.group(1))
        try:
            parsed_script = json.loads(script_content)
            script_text = json.dumps(parsed_script, ensure_ascii=False)
        except Exception:
            script_text = script_content
        for url_match in re.finditer(r"https?://[^\s\"'<>]+", script_text, flags=re.IGNORECASE):
            add_candidate(url_match.group(0), "facebook_selenium_jsonld_match")

    # Stage C: anchor hrefs.
    for match in re.finditer(r'<a\b[^>]*href\s*=\s*["\']([^"\']+)["\']', html, flags=re.IGNORECASE):
        add_candidate(unescape(match.group(1)), "facebook_selenium_anchor_match")

    # Stage D: raw rendered HTML URL regex.
    for match in re.finditer(r"https?://[^\s\"'<>]+", rendered_html, flags=re.IGNORECASE):
        add_candidate(match.group(0), "facebook_selenium_raw_match")

    driver.quit()
    selected = _pick_best_candidate(collected, threshold=0.2) or _pick_first_strong_candidate(collected)
    return selected, collected


def _extract_facebook_recovery_signals(text: str) -> tuple[Optional[str], Optional[str], list[str]]:
    if not text:
        return None, None, []

    decoded = unquote(unescape(text))
    canonical_patterns = [
        r"https?://(?:www\.)?facebook\.com/reel/(\d{15,})",
        r"https?://(?:www\.)?facebook\.com/(?:watch/\?v=|videos/)(\d{15,})",
        r"(?:^|[\"'/\s])reel/(\d{15,})(?:[/?\"'\s]|$)",
        r'"videoID"\s*:\s*"?(\d{15,})"?',
        r'"reel_id"\s*:\s*"?(\d{15,})"?',
    ]

    post_id: Optional[str] = None
    for pattern in canonical_patterns:
        match = re.search(pattern, decoded, flags=re.IGNORECASE)
        if match:
            candidate = (match.group(1) or "").strip()
            if candidate.isdigit() and len(candidate) >= 15:
                post_id = candidate
                break

    canonical_url = f"https://www.facebook.com/reel/{post_id}" if post_id else None
    candidates = _extract_url_candidates(decoded)
    external_candidates = _filter_external_candidates(candidates)
    direct_external = _pick_best_candidate(external_candidates)
    return canonical_url, direct_external, external_candidates


def _resolve_facebook_share_with_playwright(url: str) -> tuple[Optional[str], Optional[str], list[str]]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        logger.info("social-resolver headless_unavailable url=%s reason=%s", url, exc)
        return None, None, []

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(user_agent=MOBILE_SAFARI_USER_AGENT)
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_load_state("networkidle", timeout=10000)
            page.wait_for_timeout(2000)
            html = page.content() or ""
            browser.close()
    except Exception as exc:
        logger.info("social-resolver headless_share_failed url=%s reason=%s", url, exc)
        return None, None, []

    canonical_url, external_url, external_candidates = _extract_facebook_recovery_signals(html)
    logger.info(
        "social-resolver headless_share_complete url=%s canonical_url=%s external_count=%d external_url=%s",
        url,
        canonical_url or "",
        len(external_candidates),
        external_url or "",
    )
    return canonical_url, external_url, external_candidates


def resolve_facebook_url(url: str) -> SocialResolutionResult:
    ytdlp_url, ytdlp_debug = _resolve_with_ytdlp(url)
    if ytdlp_url:
        return SocialResolutionResult(
            source="facebook",
            canonical_url=str(ytdlp_debug.get("webpage_url") or "").strip() or None,
            resolved_url=ytdlp_url,
            method="ytdlp",
            post_id=_extract_facebook_post_id(url, str(ytdlp_debug.get("webpage_url") or "")),
            error=None,
            headless_attempted=False,
            ytdlp_title=str(ytdlp_debug.get("title") or ""),
            ytdlp_description=str(ytdlp_debug.get("description") or ""),
            ytdlp_webpage_url=str(ytdlp_debug.get("webpage_url") or ""),
            ytdlp_description_urls=list(ytdlp_debug.get("description_urls") or [])[:10],
        )

    try:
        redirected_url, redirected_html = _fetch_url(url)
    except Exception as exc:
        return SocialResolutionResult(
            source="facebook",
            canonical_url=None,
            resolved_url=None,
            method="none",
            post_id=None,
            error=f"facebook_fetch_failed:{exc}",
            headless_attempted=False,
            ytdlp_title=str(ytdlp_debug.get("title") or ""),
            ytdlp_description=str(ytdlp_debug.get("description") or ""),
            ytdlp_webpage_url=str(ytdlp_debug.get("webpage_url") or ""),
            ytdlp_description_urls=list(ytdlp_debug.get("description_urls") or [])[:10],
        )

    post_id = _extract_facebook_post_id(url, redirected_url, redirected_html)
    logger.info("facebook_post_id_found post_id=%s", post_id or "")
    if not post_id:
        logger.info("social-resolver facebook_fast_path_post_id_failed source_url=%s", url)
        share_canonical_url: Optional[str] = None
        share_external_url: Optional[str] = None
        share_candidates: list[str] = []
        share_headless_attempted = False
        if ENABLE_HEADLESS_FALLBACK:
            share_headless_attempted = True
            logger.info("social-resolver facebook_headless_triggered source_url=%s", url)
            share_canonical_url, share_external_url, share_candidates = _resolve_facebook_share_with_playwright(url)
        if share_external_url:
            share_rejection = _social_destination_rejection_reason(share_external_url)
            if share_rejection:
                logger.info("social-resolver candidate rejected url=%s reason=%s", share_external_url, share_rejection)
                share_external_url = None
            else:
                logger.info("social-resolver candidate accepted url=%s", share_external_url)
        if share_external_url:
            logger.info("social-resolver facebook_headless_success url=%s", share_external_url)
            logger.info("facebook_headless_success resolved_url=%s", share_external_url)
            logger.info("Final selected URL: %s", share_external_url)
            return SocialResolutionResult(
                source="facebook",
                canonical_url=share_canonical_url,
                resolved_url=share_external_url,
                method="headless",
                post_id=_extract_facebook_post_id(share_canonical_url or ""),
                error=None,
                headless_attempted=share_headless_attempted,
                headless_candidate_urls=share_candidates,
            )
        if ENABLE_HEADLESS_FALLBACK:
            logger.info("social-resolver facebook_headless_failed source_url=%s", url)
        if share_canonical_url:
            post_id = _extract_facebook_post_id(share_canonical_url)
            logger.info(
                "social-resolver facebook_headless_share_canonical source_url=%s canonical_url=%s post_id=%s",
                url,
                share_canonical_url,
                post_id or "",
            )

    if not post_id:
        logger.info("social-resolver facebook_resolution_failed source_url=%s reason=facebook_post_id_not_found", url)
        return SocialResolutionResult(
            source="facebook",
            canonical_url=None,
            resolved_url=None,
            method="none",
            post_id=None,
            error="facebook_post_id_not_found",
            headless_attempted=share_headless_attempted,
            headless_candidate_urls=share_candidates,
            ytdlp_title=str(ytdlp_debug.get("title") or ""),
            ytdlp_description=str(ytdlp_debug.get("description") or ""),
            ytdlp_webpage_url=str(ytdlp_debug.get("webpage_url") or ""),
            ytdlp_description_urls=list(ytdlp_debug.get("description_urls") or [])[:10],
        )

    canonical_url = f"https://www.facebook.com/reel/{post_id}"
    logger.info("facebook_canonical_url=%s", canonical_url)
    best_url = ""
    best_score = float("-inf")
    fetch_errors: list[str] = []
    candidate_pool: list[str] = []
    headless_attempted = False
    headless_candidates: list[str] = []
    for user_agent in (MOBILE_SAFARI_USER_AGENT,):
        try:
            final_url, html = _fetch_url_for_user_agent(canonical_url, user_agent)
        except Exception as exc:
            fetch_errors.append(str(exc))
            continue

        final_rejection = _social_destination_rejection_reason(final_url)
        if not final_rejection and not _is_tracking_url(final_url):
            final_score = _candidate_score(final_url)
            if final_score >= 0.35 and final_score > best_score:
                best_url = final_url
                best_score = final_score
            logger.info("social-resolver candidate accepted url=%s", final_url)
        elif final_url:
            logger.info("social-resolver candidate rejected url=%s reason=%s", final_url, final_rejection or "tracking_url")

        candidates = _extract_url_candidates(html)
        logger.info("Step 3: URLs found count=%d canonical_url=%s", len(candidates), canonical_url)
        filtered_candidates = _filter_external_candidates(candidates)
        logger.info("Step 4: Filtered URLs count=%d canonical_url=%s", len(filtered_candidates), canonical_url)
        if not filtered_candidates and candidates:
            logger.info("social-resolver facebook_only_social_urls canonical_url=%s", canonical_url)
        candidate_pool.extend(filtered_candidates)
        candidate_best = _pick_best_candidate(filtered_candidates)
        if candidate_best:
            candidate_score = _candidate_score(candidate_best)
            if candidate_score > best_score:
                best_url = candidate_best
                best_score = candidate_score

    attempted_user_agents = 1
    best = best_url or _pick_best_candidate(candidate_pool)
    logger.info(
        "social-resolver facebook_fast_path_candidates canonical_url=%s candidate_count=%d selected=%s",
        canonical_url,
        len(candidate_pool),
        best or "",
    )
    if best:
        best_rejection = _social_destination_rejection_reason(best)
        if best_rejection:
            logger.info("social-resolver candidate rejected url=%s reason=%s", best, best_rejection)
            best = None
    if best:
        logger.info("social-resolver candidate accepted url=%s", best)
        logger.info("Final selected URL: %s", best)
        return SocialResolutionResult(
            source="facebook",
            canonical_url=canonical_url,
            resolved_url=best,
            method="fast",
            post_id=post_id,
            error=None,
            headless_attempted=False,
            fast_path_candidate_urls=candidate_pool[:10],
            ytdlp_title=str(ytdlp_debug.get("title") or ""),
            ytdlp_description=str(ytdlp_debug.get("description") or ""),
            ytdlp_webpage_url=str(ytdlp_debug.get("webpage_url") or ""),
            ytdlp_description_urls=list(ytdlp_debug.get("description_urls") or [])[:10],
        )

    logger.info("facebook_fast_path_no_result canonical_url=%s", canonical_url)
    logger.info("facebook_headless_trigger canonical_url=%s", canonical_url)
    headless_attempted = True
    headless_result, headless_candidates = _fetch_with_playwright(canonical_url)
    if headless_result:
        headless_rejection = _social_destination_rejection_reason(headless_result)
        if headless_rejection:
            logger.info("social-resolver candidate rejected url=%s reason=%s", headless_result, headless_rejection)
            headless_result = None
    if headless_result:
        logger.info("social-resolver candidate accepted url=%s", headless_result)
        logger.info("facebook_headless_success resolved_url=%s", headless_result)
        logger.info("Final selected URL: %s", headless_result)
        logger.info("social-resolver facebook_headless_success url=%s", headless_result)
        return SocialResolutionResult(
            source="facebook",
            canonical_url=canonical_url,
            resolved_url=headless_result,
            method="headless",
            post_id=post_id,
            error=None,
            headless_attempted=headless_attempted,
            headless_candidate_urls=headless_candidates[:10],
            fast_path_candidate_urls=candidate_pool[:10],
            ytdlp_title=str(ytdlp_debug.get("title") or ""),
            ytdlp_description=str(ytdlp_debug.get("description") or ""),
            ytdlp_webpage_url=str(ytdlp_debug.get("webpage_url") or ""),
            ytdlp_description_urls=list(ytdlp_debug.get("description_urls") or [])[:10],
        )
    logger.info("facebook_headless_failed canonical_url=%s", canonical_url)

    logger.info("facebook_selenium_trigger canonical_url=%s", canonical_url)
    selenium_result, _ = _fetch_with_selenium(canonical_url)
    if selenium_result:
        selenium_rejection = _social_destination_rejection_reason(selenium_result)
        if selenium_rejection:
            logger.info("social-resolver candidate rejected url=%s reason=%s", selenium_result, selenium_rejection)
            selenium_result = None
    if selenium_result:
        logger.info("social-resolver candidate accepted url=%s", selenium_result)
        logger.info("facebook_selenium_success resolved_url=%s", selenium_result)
        logger.info("Final selected URL: %s", selenium_result)
        return SocialResolutionResult(
            source="facebook",
            canonical_url=canonical_url,
            resolved_url=selenium_result,
            method="selenium",
            post_id=post_id,
            error=None,
            headless_attempted=headless_attempted,
            headless_candidate_urls=headless_candidates[:10],
            fast_path_candidate_urls=candidate_pool[:10],
            ytdlp_title=str(ytdlp_debug.get("title") or ""),
            ytdlp_description=str(ytdlp_debug.get("description") or ""),
            ytdlp_webpage_url=str(ytdlp_debug.get("webpage_url") or ""),
            ytdlp_description_urls=list(ytdlp_debug.get("description_urls") or [])[:10],
        )
    logger.info("facebook_selenium_failed canonical_url=%s", canonical_url)

    logger.info("social-resolver facebook_resolution_failed canonical_url=%s reason=facebook_external_url_not_found", canonical_url)
    if not best_url and fetch_errors and len(fetch_errors) == attempted_user_agents:
        error = f"facebook_fetch_failed:{';'.join(fetch_errors)}"
    else:
        error = "facebook_external_url_not_found"
    return SocialResolutionResult(
        source="facebook",
        canonical_url=canonical_url,
        resolved_url=None,
        method="none",
        post_id=post_id,
        error=error,
        headless_attempted=headless_attempted,
        headless_candidate_urls=headless_candidates[:10],
        fast_path_candidate_urls=candidate_pool[:10],
        ytdlp_title=str(ytdlp_debug.get("title") or ""),
        ytdlp_description=str(ytdlp_debug.get("description") or ""),
        ytdlp_webpage_url=str(ytdlp_debug.get("webpage_url") or ""),
        ytdlp_description_urls=list(ytdlp_debug.get("description_urls") or [])[:10],
    )


def resolve_instagram_url(url: str) -> SocialResolutionResult:
    ytdlp_url, ytdlp_debug = _resolve_with_ytdlp(url)
    if ytdlp_url:
        return SocialResolutionResult(
            source="instagram",
            canonical_url=str(ytdlp_debug.get("webpage_url") or "").strip() or None,
            resolved_url=ytdlp_url,
            method="ytdlp",
            post_id=None,
            error=None,
            ytdlp_title=str(ytdlp_debug.get("title") or ""),
            ytdlp_description=str(ytdlp_debug.get("description") or ""),
            ytdlp_webpage_url=str(ytdlp_debug.get("webpage_url") or ""),
            ytdlp_description_urls=list(ytdlp_debug.get("description_urls") or [])[:10],
        )

    canonical_url = _canonicalize_instagram_url(url)
    if not canonical_url:
        return SocialResolutionResult(
            source="instagram",
            canonical_url=None,
            resolved_url=None,
            method="none",
            post_id=None,
            error="instagram_canonical_url_not_found",
            ytdlp_title=str(ytdlp_debug.get("title") or ""),
            ytdlp_description=str(ytdlp_debug.get("description") or ""),
            ytdlp_webpage_url=str(ytdlp_debug.get("webpage_url") or ""),
            ytdlp_description_urls=list(ytdlp_debug.get("description_urls") or [])[:10],
        )

    try:
        final_url, html = _fetch_url(canonical_url)
    except Exception as exc:
        return SocialResolutionResult(
            source="instagram",
            canonical_url=canonical_url,
            resolved_url=None,
            method="none",
            post_id=None,
            error=f"instagram_fetch_failed:{exc}",
            ytdlp_title=str(ytdlp_debug.get("title") or ""),
            ytdlp_description=str(ytdlp_debug.get("description") or ""),
            ytdlp_webpage_url=str(ytdlp_debug.get("webpage_url") or ""),
            ytdlp_description_urls=list(ytdlp_debug.get("description_urls") or [])[:10],
        )

    final_rejection = _social_destination_rejection_reason(final_url)
    if not final_rejection:
        logger.info("social-resolver candidate accepted url=%s", final_url)
        return SocialResolutionResult(
            source="instagram",
            canonical_url=canonical_url,
            resolved_url=final_url,
            method="fast_path",
            post_id=None,
            error=None,
            ytdlp_title=str(ytdlp_debug.get("title") or ""),
            ytdlp_description=str(ytdlp_debug.get("description") or ""),
            ytdlp_webpage_url=str(ytdlp_debug.get("webpage_url") or ""),
            ytdlp_description_urls=list(ytdlp_debug.get("description_urls") or [])[:10],
        )
    if final_url:
        logger.info("social-resolver candidate rejected url=%s reason=%s", final_url, final_rejection)

    candidates = _extract_url_candidates(html)
    filtered_candidates = _filter_external_candidates(candidates)
    best = _pick_best_candidate(filtered_candidates)
    logger.info(
        "social-resolver instagram_candidates canonical_url=%s candidate_count=%d selected=%s",
        canonical_url,
        len(filtered_candidates),
        best or "",
    )
    if best:
        return SocialResolutionResult(
            source="instagram",
            canonical_url=canonical_url,
            resolved_url=best,
            method="fast_path",
            post_id=None,
            error=None,
            ytdlp_title=str(ytdlp_debug.get("title") or ""),
            ytdlp_description=str(ytdlp_debug.get("description") or ""),
            ytdlp_webpage_url=str(ytdlp_debug.get("webpage_url") or ""),
            ytdlp_description_urls=list(ytdlp_debug.get("description_urls") or [])[:10],
        )

    return SocialResolutionResult(
        source="instagram",
        canonical_url=canonical_url,
        resolved_url=None,
        method="none",
        post_id=None,
        error="instagram_external_url_not_found",
        ytdlp_title=str(ytdlp_debug.get("title") or ""),
        ytdlp_description=str(ytdlp_debug.get("description") or ""),
        ytdlp_webpage_url=str(ytdlp_debug.get("webpage_url") or ""),
        ytdlp_description_urls=list(ytdlp_debug.get("description_urls") or [])[:10],
    )


def resolve_social_url(url: str) -> SocialResolutionResult:
    parsed = urlparse(url or "")
    host = (parsed.netloc or "").lower().strip()
    if _host_matches(host, ("facebook.com", "fb.watch")):
        return resolve_facebook_url(url)
    if _host_matches(host, ("instagram.com", "instagr.am")):
        return resolve_instagram_url(url)
    return SocialResolutionResult(
        source="unknown",
        canonical_url=None,
        resolved_url=None,
        method="none",
        post_id=None,
        error="unsupported_social_url",
    )
