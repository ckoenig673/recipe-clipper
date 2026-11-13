#!/usr/bin/env python3
"""
facebook_reel_pipeline.py

All-in-one standalone troubleshooting pipeline for Facebook recipe reels.

This is an opt-in diagnostic utility, not part of the application runtime or
automated test suite. It can download third-party media and write transcripts,
metadata, and model output to disk. Use only content you are authorized to
process, keep cookie files outside the repository, and review output before
sharing it.

What it does:
1. Pulls Facebook reel/watch/share metadata with yt-dlp
2. Downloads best available audio/media
3. Extracts mono 16 kHz WAV with ffmpeg
4. Transcribes audio with faster-whisper
5. Detects website/domain mentions from transcript + metadata
6. Sends transcript to Ollama endpoint
7. Builds a targeted search query from inferred title + detected domain
8. Searches DuckDuckGo HTML for a likely real recipe URL
9. Optionally fetches that page and extracts basic recipe signals / JSON-LD info
10. Writes all intermediate artifacts for debugging

Requirements:
  py -m pip install faster-whisper yt-dlp requests beautifulsoup4
  ffmpeg must be installed and available on PATH

Example:
  py scripts/diagnostics/facebook_reel_pipeline.py ^
    --url "https://www.facebook.com/share/v/EXAMPLE_ID/" ^
    --outdir "fb_recipe_debug_output" ^
    --whisper-model small ^
    --ollama-model llama3:latest

Optional auth for Facebook:
  --cookies-from-browser chrome
  --cookies-file cookies.txt
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urljoin, urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    requests = None  # type: ignore
    BeautifulSoup = None  # type: ignore

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None  # type: ignore


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:138.0) "
    "Gecko/20100101 Firefox/138.0"
)

URL_RE = re.compile(r'https?://[^\s<>"\']+')
DOMAIN_RE = re.compile(
    r'\b(?:[a-zA-Z0-9-]+\.)+(?:com|net|org|co|io|tv|app|ai|me|us|uk|ca|au|dev|info|biz)\b'
)


def log(msg: str) -> None:
    print(msg, flush=True)


def require_binary(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"Required binary '{name}' was not found on PATH.")


def run_cmd(cmd: List[str]) -> None:
    log(f"[cmd] {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def yt_dlp_cmd() -> List[str]:
    return [sys.executable, "-m", "yt_dlp"]


def normalize_url(candidate: str) -> str:
    candidate = candidate.strip().rstrip(".,;:!?)]}")
    if not candidate.startswith(("http://", "https://")):
        return f"https://{candidate}"
    return candidate


def canonical_domain(value: str) -> str:
    url = normalize_url(value)
    parsed = urlparse(url)
    netloc = parsed.netloc.lower().strip()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    if netloc.startswith("m."):
        netloc = netloc[2:]
    return netloc


def is_facebook_domain(value: str) -> bool:
    domain = canonical_domain(value).lower().rstrip(".")
    return domain == "facebook.com" or domain.endswith(".facebook.com")


def extract_urls_and_domains(text: str) -> List[str]:
    found: List[str] = []

    for raw in URL_RE.findall(text or ""):
        found.append(normalize_url(raw))

    for raw in DOMAIN_RE.findall(text or ""):
        url = normalize_url(raw)
        if url not in found:
            found.append(url)

    deduped: List[str] = []
    seen = set()
    for item in found:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def download_audio(
    url: str,
    outdir: Path,
    cookies_from_browser: str | None,
    cookies_file: str | None,
) -> Tuple[Path, Dict[str, Any]]:
    outtmpl = str(outdir / "download.%(ext)s")

    meta_cmd = yt_dlp_cmd() + [
        "--dump-single-json",
        "--no-playlist",
        "-o", outtmpl,
        url,
    ]
    if cookies_from_browser:
        meta_cmd.extend(["--cookies-from-browser", cookies_from_browser])
    if cookies_file:
        meta_cmd.extend(["--cookies", cookies_file])

    log("[step 1/9] Fetching metadata with yt-dlp...")
    result = subprocess.run(meta_cmd, capture_output=True, text=True, check=True)
    metadata = json.loads(result.stdout)
    (outdir / "yt_dlp_info.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    download_cmd = yt_dlp_cmd() + [
        "--no-playlist",
        "-f", "bestaudio/best",
        "-o", outtmpl,
        url,
    ]
    if cookies_from_browser:
        download_cmd.extend(["--cookies-from-browser", cookies_from_browser])
    if cookies_file:
        download_cmd.extend(["--cookies", cookies_file])

    log("[step 2/9] Downloading best available audio/media...")
    run_cmd(download_cmd)

    candidates = sorted(outdir.glob("download.*"))
    candidates = [
        p for p in candidates
        if p.name not in {
            "yt_dlp_info.json",
            "metadata.json",
            "ollama_recipe.json",
            "pipeline_summary.json",
        }
    ]
    if not candidates:
        raise RuntimeError("yt-dlp finished but no downloaded file was found.")

    downloaded = max(candidates, key=lambda p: p.stat().st_mtime)
    log(f"[ok] Downloaded media: {downloaded}")
    return downloaded, metadata


def extract_wav(input_media: Path, outdir: Path) -> Path:
    require_binary("ffmpeg")
    wav_path = outdir / "audio.wav"

    log("[step 3/9] Extracting mono 16 kHz WAV with ffmpeg...")
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(input_media),
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        str(wav_path),
    ]
    run_cmd(cmd)
    log(f"[ok] WAV written: {wav_path}")
    return wav_path


def transcribe_audio(
    wav_path: Path,
    model_name: str,
    device: str,
    compute_type: str,
    beam_size: int,
    language: str | None,
    vad_filter: bool,
) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    if WhisperModel is None:
        raise RuntimeError("faster-whisper is not installed. Run: py -m pip install faster-whisper")

    log("[step 4/9] Loading faster-whisper model...")
    model = WhisperModel(model_name, device=device, compute_type=compute_type)

    log("[step 4/9] Transcribing audio...")
    segments, info = model.transcribe(
        str(wav_path),
        beam_size=beam_size,
        vad_filter=vad_filter,
        language=language,
    )

    transcript_lines: List[str] = []
    segment_rows: List[Dict[str, Any]] = []

    for seg in segments:
        text = (seg.text or "").strip()
        if not text:
            continue
        transcript_lines.append(text)
        segment_rows.append(
            {
                "start": round(float(seg.start), 3),
                "end": round(float(seg.end), 3),
                "text": text,
            }
        )

    transcript = "\n".join(transcript_lines)
    summary = {
        "language": getattr(info, "language", None),
        "language_probability": getattr(info, "language_probability", None),
        "duration": getattr(info, "duration", None),
        "duration_after_vad": getattr(info, "duration_after_vad", None),
        "model": model_name,
        "device": device,
        "compute_type": compute_type,
        "beam_size": beam_size,
        "vad_filter": vad_filter,
    }
    return transcript, segment_rows, summary


def collect_candidate_sites(transcript: str, metadata: Dict[str, Any], recipe_json: Dict[str, Any] | None = None) -> List[str]:
    chunks = [transcript or ""]
    recipe_json = recipe_json or {}

    for source in (metadata, recipe_json):
        for key in ("description", "title", "fulltitle", "webpage_url", "original_url"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                chunks.append(value)

    for item in recipe_json.get("mentioned_websites", []) or []:
        if isinstance(item, str) and item.strip():
            chunks.append(item)

    urls = extract_urls_and_domains("\n".join(chunks))
    urls.sort(key=lambda u: (is_facebook_domain(u), canonical_domain(u), u))
    return urls


def build_prompt(transcript: str, metadata: Dict[str, Any], candidate_sites: List[str]) -> str:
    title = metadata.get("title") or metadata.get("fulltitle") or ""
    description = metadata.get("description") or ""
    uploader = metadata.get("uploader") or ""
    sites_text = "\\n".join(f"- {site}" for site in candidate_sites) if candidate_sites else "- none found"

    return f"""
You are extracting a recipe from a social media video transcript.

Your job:
- read the transcript carefully
- reconstruct the recipe in a simple, usable, cookable format
- keep only recipe content
- preserve useful cooking detail from the transcript
- do NOT invent ingredients, amounts, times, temperatures, or steps
- if something is unclear, keep it conservative instead of guessing

Return STRICT JSON only.
Do not wrap in markdown.
Do not add explanations.

Use exactly this shape:
{{
  "title": "",
  "ingredients": [],
  "instructions": [],
  "mentioned_websites": []
}}

Rules:
0. Use a clean recipe title. Remove obvious social-media noise such as view counts, reactions, hashtags, and page names when they are not part of the title.
1. Keep ingredients as plain readable strings.
2. Keep instruction steps as plain readable strings.
3. Include measurements and units when they are explicitly stated in the transcript.
4. Use ingredient quantities exactly as they appear in the transcript. Do not convert units or rewrite quantities.
5. If multiple measurements are stated, keep the original format without changing values.
6. Do NOT normalize away useful detail such as grams, millilitres, cloves, sticks, kilos, cups, tablespoons, teaspoons, or temperatures.
7. If salt is used anywhere in the recipe, include "salt" in the ingredient list, even if no quantity is given.
8. If black pepper is used anywhere in the recipe, include "black pepper" in the ingredient list, even if no quantity is given.
9. If an ingredient is clearly applied as part of the finished dish, you may include it in the ingredient list even if it is added at the end.
10. If a finishing ingredient is clearly applied to the final dish, it may be included in the ingredient list, but do not invent a quantity.
11. Do NOT omit clearly used seasonings just because the amount is not stated.
12. Preserve cooking order exactly.
13. Preserve timing details when stated, such as "cook for 4 to 5 minutes" or "bake for 40 minutes".
14. Preserve temperature details when stated.
15. Preserve useful technique/detail such as browned, caramelized, simmered, reduced, mashed, piped, or baked.
16. When a step contains multiple distinct actions, split them into separate steps when that improves clarity.
17. When heat, ingredient addition, and cooking action are clearly separate actions, prefer separate steps instead of merging them into one large step.
18. Do NOT over-compress the recipe into just a few large steps.
19. Prefer slightly more detail over over-summarizing.
20. If a side item is mentioned but is not part of the core recipe, do not include it as a required ingredient.
21. If a website or domain is mentioned, include it under "mentioned_websites".
22. Do NOT add commentary, serving suggestions, or channel outro text as recipe steps.
23. Ignore non-recipe social text such as “thanks for watching”, “hit subscribe”, “link in bio”, and similar creator outro language.
24. If caramelization or browning is explicitly mentioned, preserve that detail in the instructions.
25. If garnish is only mentioned as an optional finishing touch at the very end, do not include it as a required ingredient unless it is clearly part of the intended final dish.

Video metadata:
Title: {title}
Uploader: {uploader}
Description: {description}

Candidate websites/domains found:
{sites_text}

Transcript:
{transcript}
""".strip()


def call_ollama_generate(model: str, prompt: str, ollama_url: str, temperature: float) -> Tuple[str, Dict[str, Any]]:
    if requests is None:
        raise RuntimeError("requests is not installed. Run: py -m pip install requests")

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": temperature},
    }

    resp = requests.post(
        f"{ollama_url.rstrip('/')}/api/generate",
        json=payload,
        timeout=600,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("response", ""), data


def parse_ollama_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r'\{.*\}', text, flags=re.DOTALL)
    if match:
        return json.loads(match.group(0))

    raise ValueError("Could not parse JSON from Ollama response")


def normalize_recipe(recipe: Dict[str, Any], candidate_sites: List[str]) -> Dict[str, Any]:
    title = str(recipe.get("title") or "").strip()
    ingredients = [
        str(item).strip()
        for item in (recipe.get("ingredients") or [])
        if str(item).strip()
    ]
    instructions = [
        str(item).strip()
        for item in (recipe.get("instructions") or [])
        if str(item).strip()
    ]

    mentioned_websites: List[str] = []
    for item in (recipe.get("mentioned_websites") or []):
        clean = str(item).strip()
        if clean:
            normalized = normalize_url(clean)
            if normalized not in mentioned_websites:
                mentioned_websites.append(normalized)

    for site in candidate_sites:
        if site not in mentioned_websites:
            mentioned_websites.append(site)

    return {
        "title": title,
        "ingredients": ingredients,
        "instructions": instructions,
        "mentioned_websites": mentioned_websites,
    }


def clean_title_text(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r'^\d+\s*[KM]?\s*views\s*[·|]\s*', '', text, flags=re.I)
    text = re.sub(r'\|\s*[^|]+$', '', text)
    text = re.sub(r'comment .*? inbox!?', '', text, flags=re.I)
    text = text.replace("I’ve perfected my ", "")
    text = text.replace("I've perfected my ", "")
    text = text.replace(" and yes it uses a whole bottle of wine", "")
    text = text.strip(" -|·")
    return " ".join(text.split()).strip()


def guess_domain(candidate_sites: List[str]) -> Optional[str]:
    for site in candidate_sites:
        dom = canonical_domain(site)
        if dom and "facebook.com" not in dom:
            return dom
    return None


def guess_title(transcript: str, metadata: Dict[str, Any], recipe_json: Dict[str, Any]) -> str:
    title = str(recipe_json.get("title") or "").strip()
    if title:
        return title

    meta_title = clean_title_text(str(metadata.get("title") or metadata.get("fulltitle") or ""))
    if meta_title:
        return meta_title

    first_line = transcript.splitlines()[0].strip() if transcript.strip() else ""
    first_line = re.sub(r'^I have perfected my ', '', first_line, flags=re.I)
    first_line = re.sub(r'\.\s*This is how you do it\.?$', '', first_line, flags=re.I)
    return " ".join(first_line.split()).strip()


def build_search_query(title: str, domain: str) -> str:
    return f"{title} site:{domain}".strip() if title and domain else f"{title} {domain}".strip()


def unwrap_search_result_url(value: str) -> str:
    absolute_url = urljoin("https://html.duckduckgo.com/", (value or "").strip())
    parsed = urlparse(absolute_url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if host == "duckduckgo.com" or host.endswith(".duckduckgo.com"):
        destination = (parse_qs(parsed.query).get("uddg") or [""])[0]
        if destination:
            return unquote(destination).strip()
    return absolute_url


def ddg_search(query: str, max_results: int = 10) -> List[Dict[str, str]]:
    if requests is None or BeautifulSoup is None:
        raise RuntimeError("Install dependencies: py -m pip install requests beautifulsoup4")

    url = "https://html.duckduckgo.com/html/"
    headers = {"User-Agent": USER_AGENT}
    data = {"q": query}

    resp = requests.post(url, headers=headers, data=data, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    results: List[Dict[str, str]] = []

    for result in soup.select(".result"):
        link_tag = result.select_one(".result__title a.result__a")
        snippet_tag = result.select_one(".result__snippet")
        if not link_tag:
            continue

        href = unwrap_search_result_url(link_tag.get("href") or "")
        title = " ".join(link_tag.get_text(" ", strip=True).split())
        snippet = " ".join(snippet_tag.get_text(" ", strip=True).split()) if snippet_tag else ""

        if href:
            results.append({"title": title, "url": href, "snippet": snippet})
        if len(results) >= max_results:
            break

    return results


def choose_best_result(results: List[Dict[str, str]], domain: str, title: str) -> Optional[Dict[str, str]]:
    domain = canonical_domain(domain) if domain else ""
    title_tokens = {t.lower() for t in re.findall(r"[a-zA-Z0-9]+", title) if len(t) > 2}

    scored: List[Tuple[int, Dict[str, str]]] = []
    for item in results:
        score = 0
        url = item["url"]
        item_domain = canonical_domain(url)

        if item_domain == domain:
            score += 100
        elif domain and domain in item_domain:
            score += 80

        text = f'{item["title"]} {item["snippet"]}'.lower()
        for token in title_tokens:
            if token in text:
                score += 5

        if "/recipe" in url:
            score += 10
        if "#recipe" in url.lower():
            score += 6
        if "recipe" in item["title"].lower():
            score += 3

        scored.append((score, item))

    if not scored:
        return None

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def fetch_page(url: str) -> str:
    if requests is None:
        raise RuntimeError("Install dependencies: py -m pip install requests beautifulsoup4")
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text


def is_recipe_jsonld_node(node: Any) -> bool:
    if not isinstance(node, dict):
        return False
    node_types = node.get("@type")
    return node_types == "Recipe" or (isinstance(node_types, list) and "Recipe" in node_types)


def extract_page_signals(html: str) -> Dict[str, Any]:
    if BeautifulSoup is None:
        raise RuntimeError("Install dependencies: py -m pip install beautifulsoup4")

    soup = BeautifulSoup(html, "html.parser")

    page_title = ""
    if soup.title and soup.title.string:
        page_title = " ".join(soup.title.string.split()).strip()

    jsonld_blocks: List[Dict[str, Any]] = []
    recipe_jsonld: List[Dict[str, Any]] = []

    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string or tag.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
            jsonld_blocks.append(data)
        except Exception:
            continue

    def walk(obj: Any):
        if isinstance(obj, dict):
            yield obj
            for value in obj.values():
                yield from walk(value)
        elif isinstance(obj, list):
            for item in obj:
                yield from walk(item)

    for block in jsonld_blocks:
        for node in walk(block):
            if is_recipe_jsonld_node(node):
                recipe_jsonld.append(node)

    recipe_node = recipe_jsonld[0] if recipe_jsonld else {}

    ingredients = recipe_node.get("recipeIngredient") or []
    instructions = recipe_node.get("recipeInstructions") or []
    instruction_count = len(instructions) if isinstance(instructions, list) else (1 if instructions else 0)

    return {
        "page_title": page_title,
        "jsonld_recipe_found": bool(recipe_node),
        "recipe_name": recipe_node.get("name"),
        "ingredient_count": len(ingredients) if isinstance(ingredients, list) else 0,
        "instruction_count": instruction_count,
        "has_recipe_fragment": "#recipe" in html.lower(),
        "canonical_url": (
            recipe_node.get("mainEntityOfPage")
            if isinstance(recipe_node.get("mainEntityOfPage"), str)
            else None
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="All-in-one FB reel -> transcript -> Ollama -> source finder pipeline.")
    parser.add_argument("--url", required=True, help="Facebook watch/reel/share URL")
    parser.add_argument("--outdir", default="fb_recipe_debug_output", help="Output directory")
    parser.add_argument("--whisper-model", default="small", help="Whisper model: tiny, base, small, medium, large-v3, etc.")
    parser.add_argument("--device", default="cpu", help="Whisper device: cpu or cuda")
    parser.add_argument("--compute-type", default="int8", help="Whisper compute type")
    parser.add_argument("--beam-size", type=int, default=5, help="Beam size for transcription")
    parser.add_argument("--language", default=None, help="Optional language code like en")
    parser.add_argument("--no-vad-filter", action="store_true", help="Disable VAD filtering")
    parser.add_argument("--cookies-from-browser", default=None, help="yt-dlp cookies source: chrome, firefox, edge")
    parser.add_argument("--cookies-file", default=None, help="Netscape-format cookies file for yt-dlp")
    parser.add_argument("--ollama-model", default="llama3:latest", help="Ollama model name")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434", help="Base URL for Ollama")
    parser.add_argument("--temperature", type=float, default=0.2, help="Ollama sampling temperature")
    parser.add_argument("--skip-search", action="store_true", help="Skip search/source-finder stage")
    parser.add_argument("--skip-fetch", action="store_true", help="Search only, do not fetch candidate recipe page")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    outdir = Path(args.outdir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    log(f"[info] Output directory: {outdir}")
    log(f"[info] Source URL: {args.url}")
    log(f"[info] Ollama URL: {args.ollama_url}")
    log(f"[info] Ollama model: {args.ollama_model}")

    try:
        downloaded_media, yt_dlp_info = download_audio(
            url=args.url,
            outdir=outdir,
            cookies_from_browser=args.cookies_from_browser,
            cookies_file=args.cookies_file,
        )

        wav_path = extract_wav(downloaded_media, outdir)

        transcript, segment_rows, transcription_summary = transcribe_audio(
            wav_path=wav_path,
            model_name=args.whisper_model,
            device=args.device,
            compute_type=args.compute_type,
            beam_size=args.beam_size,
            language=args.language,
            vad_filter=not args.no_vad_filter,
        )

        transcript_path = outdir / "transcript.txt"
        transcript_path.write_text(transcript, encoding="utf-8")

        segments_path = outdir / "transcript_segments.json"
        segments_path.write_text(json.dumps(segment_rows, indent=2, ensure_ascii=False), encoding="utf-8")

        candidate_sites_initial = collect_candidate_sites(transcript, yt_dlp_info, None)
        prompt = build_prompt(transcript, yt_dlp_info, candidate_sites_initial)

        prompt_path = outdir / "ollama_recipe_prompt.txt"
        prompt_path.write_text(prompt, encoding="utf-8")

        log("[step 5/9] Candidate sites/domains found before Ollama:")
        if candidate_sites_initial:
            for site in candidate_sites_initial:
                log(f"  - {site}")
        else:
            log("  - none found")

        log("[step 6/9] Sending transcript to Ollama...")
        response_text, raw_ollama = call_ollama_generate(
            model=args.ollama_model,
            prompt=prompt,
            ollama_url=args.ollama_url,
            temperature=args.temperature,
        )

        raw_response_path = outdir / "ollama_raw_response.txt"
        raw_response_path.write_text(response_text, encoding="utf-8")

        parsed = parse_ollama_json(response_text)
        normalized_recipe = normalize_recipe(parsed, candidate_sites_initial)

        recipe_path = outdir / "ollama_recipe.json"
        recipe_path.write_text(json.dumps(normalized_recipe, indent=2, ensure_ascii=False), encoding="utf-8")

        summary: Dict[str, Any] = {
            "source_url": args.url,
            "downloaded_file": str(downloaded_media),
            "wav_file": str(wav_path),
            "video_title": yt_dlp_info.get("title"),
            "uploader": yt_dlp_info.get("uploader"),
            "duration": yt_dlp_info.get("duration"),
            "transcription": transcription_summary,
            "candidate_sites_initial": candidate_sites_initial,
            "ollama_model": args.ollama_model,
            "ollama_url": args.ollama_url,
            "ollama_recipe_title": normalized_recipe.get("title"),
        }

        if not args.skip_search:
            log("[step 7/9] Building source-finder query...")
            candidate_sites_final = collect_candidate_sites(transcript, yt_dlp_info, normalized_recipe)
            chosen_domain = guess_domain(candidate_sites_final)
            chosen_title = guess_title(transcript, yt_dlp_info, normalized_recipe)
            search_query = build_search_query(chosen_title, chosen_domain or "")

            (outdir / "source_finder_inputs.json").write_text(
                json.dumps(
                    {
                        "candidate_sites": candidate_sites_final,
                        "chosen_domain": chosen_domain,
                        "chosen_title": chosen_title,
                        "search_query": search_query,
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            log(f"[info] title guess:  {chosen_title}")
            log(f"[info] domain guess: {chosen_domain or '(none)'}")
            log(f"[info] query:       {search_query}")

            log("[step 8/9] Searching for likely source recipe URL...")
            results = ddg_search(search_query, max_results=10)
            (outdir / "search_results.json").write_text(
                json.dumps(results, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            best = choose_best_result(results, chosen_domain or "", chosen_title)
            summary["source_finder"] = {
                "candidate_sites": candidate_sites_final,
                "chosen_domain": chosen_domain,
                "chosen_title": chosen_title,
                "search_query": search_query,
            }

            if best:
                best_url = best["url"]
                (outdir / "best_candidate_url.txt").write_text(best_url, encoding="utf-8")
                log(f"[ok] best candidate URL: {best_url}")
                summary["source_finder"]["best_candidate"] = best

                if not args.skip_fetch:
                    log("[step 9/9] Fetching candidate source page...")
                    html = fetch_page(best_url)
                    (outdir / "candidate_page.html").write_text(html, encoding="utf-8", errors="replace")

                    signals = extract_page_signals(html)
                    (outdir / "candidate_page_signals.json").write_text(
                        json.dumps(signals, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    summary["source_finder"]["page_signals"] = signals
                    log("[page signals]")
                    print(json.dumps(signals, indent=2, ensure_ascii=False))
            else:
                log("[warn] no suitable search result found")
                summary["source_finder"]["best_candidate"] = None

        (outdir / "pipeline_summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        log("")
        log("[done] Files written:")
        for name in [
            "yt_dlp_info.json",
            "transcript.txt",
            "transcript_segments.json",
            "ollama_recipe_prompt.txt",
            "ollama_raw_response.txt",
            "ollama_recipe.json",
            "source_finder_inputs.json" if not args.skip_search else None,
            "search_results.json" if not args.skip_search else None,
            "best_candidate_url.txt" if not args.skip_search else None,
            "candidate_page.html" if (not args.skip_search and not args.skip_fetch) else None,
            "candidate_page_signals.json" if (not args.skip_search and not args.skip_fetch) else None,
            "pipeline_summary.json",
        ]:
            if name:
                log(f"  - {outdir / name}")

        log("")
        log("[recipe preview]")
        print(json.dumps(normalized_recipe, indent=2, ensure_ascii=False))
        return 0

    except subprocess.CalledProcessError as exc:
        log("")
        log("[error] External command failed.")
        log(f"Command: {' '.join(exc.cmd) if exc.cmd else '<unknown>'}")
        log(f"Return code: {exc.returncode}")
        if getattr(exc, "stdout", None):
            log("--- stdout ---")
            print(exc.stdout)
        if getattr(exc, "stderr", None):
            log("--- stderr ---")
            print(exc.stderr)
        return 1
    except Exception as exc:
        log("")
        log(f"[error] {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
