from typing import Optional
from fastapi import FastAPI, UploadFile, File, HTTPException
from PIL import Image, ImageOps
import numpy as np
import easyocr
import io
import time
import logging
import re

app = FastAPI(title="ocr-worker", version="1.0.0")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ocr-worker")

# Loaded once when the container starts. First start can take time while EasyOCR downloads models.
reader = easyocr.Reader(["en"], gpu=False)

RECIPE_KEYWORDS = [
    "cup", "cups", "teaspoon", "teaspoons", "tablespoon", "tablespoons", "tsp", "tbsp",
    "ingredients", "instructions", "bake", "oven", "mix", "preheat", "servings",
    "sugar", "flour", "butter", "egg", "eggs", "banana", "cinnamon", "oats", "pecans",
    "cake", "sour", "cream",
]

FRACTION_TOKENS = ["1/2", "1/3", "1/4", "2/3", "3/4", "1/8", "3/8", "5/8", "7/8"]
UNICODE_FRACTIONS = ["½", "⅓", "¼", "⅔", "¾", "⅛", "⅜", "⅝", "⅞"]


def clean_text(text: str) -> str:
    text = text or ""
    text = text.replace("\x0c", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_ocr_text(text: str) -> str:
    normalized = text or ""

    # Temperature fixes (e.g. OCR reading degree symbol as 8/0 or space).
    normalized = re.sub(r"\b(3\d{2})[80]F\b", r"\1°F", normalized)
    normalized = re.sub(r"\b(\d{2,3})\s+F\b", r"\1°F", normalized)

    # Fraction fixes near recipe units.
    normalized = re.sub(r"\b14\s+(teaspoons?)\b", r"1/4 \1", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\b14\s+tsp\b", "1/4 tsp", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bY\s+(cups?)\b", r"1/3 \1", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bY4\s+(teaspoons?)\b", r"1/4 \1", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bY4\s+tsp\b", "1/4 tsp", normalized, flags=re.IGNORECASE)

    normalized = re.sub(r"\b1/1\s+(cups?)\b", r"1/2 \1", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\b1/1\s+(teaspoons?)\b", r"1/2 \1", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\b1/1\s+tsp\b", "1/2 tsp", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bpackage\s*\(", "1 package (", normalized, flags=re.IGNORECASE)

    # Common recipe word OCR fixes.
    normalized = re.sub(r"\bfour(\s+and\s+cinnamon)\b", r"flour\1", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bfour(,\s+and\s+cinnamon)\b", r"flour\1", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bfour(\s+cinnamon)\b", r"flour\1", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bsuger\b", "sugar", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bbrowm\b", "brown", normalized, flags=re.IGNORECASE)

    return normalized


def score_text(text: str) -> tuple[int, int]:
    lowered = (text or "").lower()
    keyword_score = sum(lowered.count(k) for k in RECIPE_KEYWORDS)

    ascii_fraction_score = sum(lowered.count(f) for f in FRACTION_TOKENS)
    unicode_fraction_score = sum(text.count(f) for f in UNICODE_FRACTIONS)
    fraction_score = ascii_fraction_score + unicode_fraction_score

    return keyword_score, fraction_score


def rank_candidate(confidence_percent: float, keyword_score: int, fraction_score: int, text_length: int) -> float:
    return (
        (confidence_percent * 2.0)
        + (keyword_score * 20.0)
        + (fraction_score * 35.0)
        + min(text_length / 10.0, 40.0)
    )


@app.get("/health")
async def health():
    return {"status": "ok", "engine": "easyocr"}


@app.post("/ocr/image")
async def ocr_image(
    file: Optional[UploadFile] = File(default=None),
    image: Optional[UploadFile] = File(default=None),
):
    request_started = time.perf_counter()

    upload = image or file
    if upload is None:
        raise HTTPException(status_code=422, detail="Image file is required")

    contents = await upload.read()
    if not contents:
        raise HTTPException(status_code=422, detail="Image file is empty")

    try:
        source_image = Image.open(io.BytesIO(contents))
        source_image = ImageOps.exif_transpose(source_image).convert("RGB")
    except Exception as exc:
        logger.exception("ocr_image_invalid_upload filename=%s error=%s", upload.filename, exc)
        raise HTTPException(status_code=422, detail="Invalid image file")

    # Production-ish default:
    # - Try normal orientation first.
    # - Try 90 degrees if needed.
    # - Avoid 180/270 by default because they double OCR time and rarely help for phone recipe shots.
    rotations = [0, 90]

    best = None
    candidates = []

    logger.info(
        "ocr_image_started filename=%s bytes=%s size=%sx%s rotations=%s",
        upload.filename,
        len(contents),
        source_image.width,
        source_image.height,
        rotations,
    )

    for rotation in rotations:
        rotation_started = time.perf_counter()

        img = source_image if rotation == 0 else source_image.rotate(rotation, expand=True)
        result = reader.readtext(np.array(img), detail=1, paragraph=False)

        raw_text = clean_text("\n".join([str(r[1]).strip() for r in result if len(r) >= 2 and str(r[1]).strip()]))
        text = normalize_ocr_text(raw_text)

        confidence_values = []
        for row in result:
            if len(row) < 3:
                continue
            try:
                confidence_values.append(float(row[2]) * 100.0)
            except Exception:
                pass

        confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
        keyword_score, fraction_score = score_text(text)
        text_length = len(text)
        rank = rank_candidate(confidence, keyword_score, fraction_score, text_length)
        elapsed = time.perf_counter() - rotation_started

        candidate = {
            "raw_text": raw_text,
            "text": text,
            "confidence": confidence,
            "rotation": rotation,
            "keyword_score": keyword_score,
            "fraction_score": fraction_score,
            "text_length": text_length,
            "rank": rank,
            "elapsed_seconds": round(elapsed, 3),
        }
        candidates.append(candidate)

        logger.info(
            "ocr_rotation_result rotation=%s confidence=%.2f keyword_score=%s fraction_score=%s text_length=%s rank=%.2f elapsed=%.2fs",
            rotation,
            confidence,
            keyword_score,
            fraction_score,
            text_length,
            rank,
            elapsed,
        )

        if best is None or candidate["rank"] > best["rank"]:
            best = candidate

        # Early exit: if we already have a strong recipe-looking result, stop before extra rotations.
        if confidence >= 82 and keyword_score >= 8 and text_length >= 300:
            logger.info("ocr_early_exit rotation=%s reason=strong_candidate", rotation)
            break

    if best is None or not best.get("text"):
        raise HTTPException(status_code=422, detail="No OCR text found")

    total_elapsed = time.perf_counter() - request_started
    logger.info(
        "ocr_image_finished selected_rotation=%s confidence=%.2f keyword_score=%s fraction_score=%s text_length=%s total_elapsed=%.2fs",
        best["rotation"],
        best["confidence"],
        best["keyword_score"],
        best["fraction_score"],
        best["text_length"],
        total_elapsed,
    )

    return {
        "engine": "easyocr",
        "raw_text": best["raw_text"],
        "text": best["text"],
        "confidence": best["confidence"],
        "rotation": best["rotation"],
        "keyword_score": best["keyword_score"],
        "fraction_score": best["fraction_score"],
        "text_length": best["text_length"],
        "rank": best["rank"],
        "elapsed_seconds": round(total_elapsed, 3),
        "candidates": [
            {
                "rotation": c["rotation"],
                "confidence": c["confidence"],
                "keyword_score": c["keyword_score"],
                "fraction_score": c["fraction_score"],
                "text_length": c["text_length"],
                "rank": c["rank"],
                "elapsed_seconds": c["elapsed_seconds"],
            }
            for c in candidates
        ],
    }
