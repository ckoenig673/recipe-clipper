import importlib.util
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parents[1] / "app.py"
    spec = importlib.util.spec_from_file_location("social_worker_app", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_download_failure_response_is_sanitized(monkeypatch):
    module = _load_module()

    def _raise_download(_source_url: str, _options: dict):
        raise RuntimeError("yt-dlp failed from C:\\workers\\social.py")

    monkeypatch.setattr(module, "_attempt_download", _raise_download)
    payload = module.DownloadRequest(url="https://example.com/video")

    response = module.download_social_video(payload)

    assert response.success is False
    assert response.error == module.INTERNAL_ERROR_MESSAGE
    assert response.stage == "yt-dlp"
    assert response.diagnostic_id
    assert "social.py" not in (response.error or "")
