import importlib.util
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parents[1] / "app.py"
    spec = importlib.util.spec_from_file_location("whisper_worker_app", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_transcribe_failure_response_is_sanitized(monkeypatch):
    module = _load_module()

    def _raise_model(_model_size: str, _device: str, _compute_type: str):
        raise RuntimeError("failed at /app/internal/whisper.py with SQL details")

    monkeypatch.setattr(module, "_get_model", _raise_model)
    monkeypatch.setattr(module, "_validate_runtime_dependencies", lambda: {"ok": True, "missing": []})
    payload = module.TranscribeRequest(audio_path="sample.wav")

    response = module.transcribe(payload)

    assert response.success is False
    assert response.error == module.INTERNAL_ERROR_MESSAGE
    assert response.stage == "whisper"
    assert response.diagnostic_id
    assert "whisper.py" not in (response.error or "")
    assert "SQL" not in (response.error or "")
