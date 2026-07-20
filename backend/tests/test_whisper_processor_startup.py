import importlib.util
from pathlib import Path


WHISPER_APP_PATH = Path(__file__).resolve().parents[2] / "whisper-worker" / "app.py"


def _load_whisper_app_module():
    spec = importlib.util.spec_from_file_location("whisper_processor_app_test", WHISPER_APP_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_whisper_processor_health_reports_missing_runtime_dependencies(monkeypatch):
    module = _load_whisper_app_module()

    def _fake_import(name):
        if name == "requests":
            raise ModuleNotFoundError("requests")
        return object()

    monkeypatch.setattr(module.importlib, "import_module", _fake_import)

    payload = module.health()

    assert payload["status"] == "degraded"
    assert payload["runtime_dependencies"]["ok"] is False
    assert payload["runtime_dependencies"]["missing"] == ["requests"]


def test_whisper_processor_transcribe_returns_startup_validation_error_when_dependency_missing(monkeypatch, tmp_path):
    module = _load_whisper_app_module()

    def _fake_import(name):
        if name == "requests":
            raise ModuleNotFoundError("requests")
        return object()

    monkeypatch.setattr(module.importlib, "import_module", _fake_import)

    response = module.transcribe(module.TranscribeRequest(audio_path=str(tmp_path / "audio.wav")))

    assert response.success is False
    assert response.stage == "startup_validation"
    assert "Missing runtime dependencies: requests" in (response.error or "")
