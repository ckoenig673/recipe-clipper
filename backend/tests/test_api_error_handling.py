import tempfile
from pathlib import Path
import logging

import pytest
from fastapi.testclient import TestClient

from backend.app import main


def _create_user(email: str = "u@example.com") -> int:
    conn = main.get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (email, password_hash, is_admin, is_active, created_at) VALUES (?, ?, 0, 1, ?)",
        (email, main.hash_password("pw123456"), main.utcnow_iso()),
    )
    conn.commit()
    user_id = int(cur.lastrowid)
    conn.close()
    return user_id


def _login(client: TestClient, email: str = "u@example.com", password: str = "pw123456"):
    return client.post("/auth/login", json={"email": email, "password": password})


def test_unhandled_exception_response_is_sanitized(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        original_db = main.DB
        try:
            main.DB = str(Path(tmp_dir) / "recipes.db")
            main.init_db()
            _create_user()
            client = TestClient(main.app, raise_server_exceptions=False)
            assert _login(client).status_code == 200

            def _raise_conn_error():
                raise RuntimeError("traceback leaked from C:\\internal\\secrets.py:12")

            monkeypatch.setattr(main, "get_conn", _raise_conn_error)
            response = client.get("/recipes")

            assert response.status_code == 500
            payload = response.json()
            assert payload == {
                "detail": main.INTERNAL_SERVER_ERROR_MESSAGE,
                "correlation_id": payload["correlation_id"],
            }
            assert payload["correlation_id"]
            assert response.headers["X-Correlation-ID"] == payload["correlation_id"]
            assert "traceback" not in response.text.lower()
            assert "secrets.py" not in response.text
        finally:
            main.DB = original_db


def test_internal_http_exception_does_not_expose_environment_key(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        original_db = main.DB
        try:
            main.DB = str(Path(tmp_dir) / "recipes.db")
            monkeypatch.delenv(main.SETTINGS_ENCRYPTION_KEY_ENV, raising=False)
            main.init_db()
            _create_user()
            client = TestClient(main.app, raise_server_exceptions=False)
            assert _login(client).status_code == 200

            response = client.put(
                "/settings/import/facebook-cookie",
                json={"facebook_cookie": "c_user=123; xs=abc"},
            )

            assert response.status_code == 500
            payload = response.json()
            assert payload["detail"] == main.INTERNAL_SERVER_ERROR_MESSAGE
            assert payload["correlation_id"]
            assert response.headers["X-Correlation-ID"] == payload["correlation_id"]
            assert main.SETTINGS_ENCRYPTION_KEY_ENV not in response.text
        finally:
            main.DB = original_db


def test_extract_metadata_parser_exception_returns_controlled_failure(monkeypatch, caplog):
    with tempfile.TemporaryDirectory() as tmp_dir:
        original_db = main.DB
        try:
            main.DB = str(Path(tmp_dir) / "recipes.db")
            main.init_db()
            _create_user()
            client = TestClient(main.app, raise_server_exceptions=False)
            assert _login(client).status_code == 200

            def _raise_parser_error(_url: str):
                raise RuntimeError("traceback leaked from C:\\internal\\parser.py:63")

            monkeypatch.setattr(main, "fetch_recipe_data_from_url", _raise_parser_error)
            with caplog.at_level(logging.ERROR):
                response = client.get("/extract-metadata", params={"url": "https://example.com/recipe"})

            assert response.status_code == 502
            payload = response.json()
            assert payload == {
                "detail": main.INTERNAL_SERVER_ERROR_MESSAGE,
                "correlation_id": payload["correlation_id"],
            }
            assert payload["correlation_id"]
            assert response.headers["X-Correlation-ID"] == payload["correlation_id"]
            assert "traceback" not in response.text.lower()
            assert "parser.py" not in response.text
            assert "extract-metadata failed path=/extract-metadata" in caplog.text
            assert f"correlation_id={payload['correlation_id']}" in caplog.text
            assert "error_type=RuntimeError" in caplog.text
            assert "traceback leaked from C:\\internal\\parser.py:63" in caplog.text
        finally:
            main.DB = original_db


def test_extract_metadata_direct_invocation_without_request_logs_diagnostics_and_raises_sanitized_http_error(
    monkeypatch, caplog
):
    def _raise_parser_error(_url: str):
        raise RuntimeError("traceback leaked from C:\\internal\\parser.py:63")

    monkeypatch.setattr(main, "fetch_recipe_data_from_url", _raise_parser_error)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(main.HTTPException) as exc_info:
            main.extract_metadata(url="https://example.com/recipe", _={})

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Recipe extraction failed while processing this page."
    assert "extract-metadata failed path=<direct-call>" in caplog.text
    assert "error_type=RuntimeError" in caplog.text
    assert "traceback leaked from C:\\internal\\parser.py:63" in caplog.text
