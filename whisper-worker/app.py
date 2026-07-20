from __future__ import annotations

import importlib
import logging
import os
import time
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

logger = logging.getLogger("whisper_processor")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="whisper-worker", version="1.0.0")

_MODEL_CACHE: dict[tuple[str, str, str], object] = {}
_RUNTIME_VALIDATION: dict[str, object] = {"ok": True, "missing": []}
_REQUIRED_RUNTIME_MODULES = {
    "faster_whisper": "faster-whisper",
    "requests": "requests",
}


def _validate_runtime_dependencies() -> dict[str, object]:
    missing: list[str] = []
    for module_name, package_name in _REQUIRED_RUNTIME_MODULES.items():
        try:
            importlib.import_module(module_name)
        except Exception:
            missing.append(package_name)
    status = {"ok": not missing, "missing": missing}
    _RUNTIME_VALIDATION.update(status)
    return status


@app.on_event("startup")
def validate_startup_dependencies() -> None:
    validation = _validate_runtime_dependencies()
    if validation["ok"]:
        logger.info("whisper_startup_validation_ok required=%s", sorted(_REQUIRED_RUNTIME_MODULES.values()))
        return
    logger.error("whisper_startup_validation_failed missing=%s", validation["missing"])


@app.get("/health")
def health() -> dict:
    validation = _validate_runtime_dependencies()
    return {
        "status": "ok" if validation["ok"] else "degraded",
        "service": "whisper-worker",
        "runtime_dependencies": validation,
    }


class TranscribeRequest(BaseModel):
    audio_path: str
    model_size: str | None = None
    device: str | None = None
    compute_type: str | None = None


class TranscribeResponse(BaseModel):
    success: bool
    transcript: str | None = None
    elapsed_seconds: float | None = None
    error: str | None = None
    stage: str | None = None


def _resolve(value: str | None, env_key: str, default: str) -> str:
    return (value or os.getenv(env_key, default)).strip() or default


def _get_model(model_size: str, device: str, compute_type: str):
    from faster_whisper import WhisperModel

    key = (model_size, device, compute_type)
    model = _MODEL_CACHE.get(key)
    if model is None:
        logger.info("whisper_model_load_start model=%s device=%s compute_type=%s", model_size, device, compute_type)
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        _MODEL_CACHE[key] = model
        logger.info("whisper_model_load_done model=%s device=%s compute_type=%s", model_size, device, compute_type)
    return model


@app.post("/transcribe", response_model=TranscribeResponse)
def transcribe(req: TranscribeRequest) -> TranscribeResponse:
    started = time.monotonic()
    try:
        validation = _validate_runtime_dependencies()
        if not validation["ok"]:
            missing_list = ", ".join(validation["missing"])
            error = f"Missing runtime dependencies: {missing_list}. Check whisper-worker requirements/install."
            logger.error("whisper_transcription_startup_validation_failed missing=%s", validation["missing"])
            return TranscribeResponse(success=False, error=error[:200], stage="startup_validation")
        audio_path = str(Path(req.audio_path))
        model_size = _resolve(req.model_size, "WHISPER_MODEL", "small")
        device = _resolve(req.device, "WHISPER_DEVICE", "cpu")
        compute_type = _resolve(req.compute_type, "WHISPER_COMPUTE_TYPE", "int8")
        logger.info(
            "whisper_transcription_request_started audio_path=%s model=%s device=%s compute_type=%s",
            audio_path,
            model_size,
            device,
            compute_type,
        )
        model = _get_model(model_size, device, compute_type)
        segments, _ = model.transcribe(audio_path)
        transcript = " ".join((str(segment.text or "").strip() for segment in segments if str(segment.text or "").strip())).strip()
        elapsed = time.monotonic() - started
        logger.info(
            "whisper_transcription_request_done audio_path=%s transcript_chars=%d elapsed_s=%.3f",
            audio_path,
            len(transcript),
            elapsed,
        )
        return TranscribeResponse(success=True, transcript=transcript, elapsed_seconds=elapsed)
    except Exception as exc:
        logger.exception("whisper_transcription_request_failed error=%s", str(exc))
        return TranscribeResponse(success=False, error=str(exc)[:200], stage="whisper")
