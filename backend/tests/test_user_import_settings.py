import tempfile
from pathlib import Path

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


def test_import_settings_auth_required():
    with tempfile.TemporaryDirectory() as tmp_dir:
        original_db = main.DB
        try:
            main.DB = str(Path(tmp_dir) / "recipes.db")
            main.init_db()
            client = TestClient(main.app)
            assert client.get("/settings/import").status_code == 401
        finally:
            main.DB = original_db


def test_save_get_delete_facebook_cookie_metadata_only(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        original_db = main.DB
        try:
            main.DB = str(Path(tmp_dir) / "recipes.db")
            monkeypatch.setenv("USER_SETTINGS_ENCRYPTION_KEY", "l1k8sEHPAs6TLKG3tA4aF6k5DAt84sYI6FqdtYYdlcE=")
            main.init_db()
            _create_user()
            client = TestClient(main.app)
            assert _login(client).status_code == 200

            raw_cookie = "c_user=123; xs=abc"
            put_resp = client.put("/settings/import/facebook-cookie", json={"facebook_cookie": raw_cookie})
            assert put_resp.status_code == 200

            get_resp = client.get("/settings/import")
            assert get_resp.status_code == 200
            payload = get_resp.json()
            assert payload["has_facebook_cookie"] is True
            assert payload["facebook_cookie_updated_at"]
            assert "facebook_cookie" not in payload

            conn = main.get_conn()
            row = conn.execute("SELECT facebook_cookie_encrypted FROM user_import_settings LIMIT 1").fetchone()
            conn.close()
            assert row is not None
            assert raw_cookie not in str(row["facebook_cookie_encrypted"])

            delete_resp = client.delete("/settings/import/facebook-cookie")
            assert delete_resp.status_code == 200
            get_after_delete = client.get("/settings/import").json()
            assert get_after_delete["has_facebook_cookie"] is False
        finally:
            main.DB = original_db


def test_facebook_cookie_validation_error_handles_raw_bytes_safely(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        original_db = main.DB
        try:
            main.DB = str(Path(tmp_dir) / "recipes.db")
            monkeypatch.setenv("USER_SETTINGS_ENCRYPTION_KEY", "l1k8sEHPAs6TLKG3tA4aF6k5DAt84sYI6FqdtYYdlcE=")
            main.init_db()
            _create_user()
            client = TestClient(main.app)
            assert _login(client).status_code == 200

            response = client.put(
                "/settings/import/facebook-cookie",
                data=b'{"facebook_cookie":"# Netscape HTTP Cookie File\\nc_user=123"}',
            )
            assert response.status_code == 422
            payload = response.json()
            assert "detail" in payload
            assert payload["detail"][0]["input"] == "<bytes omitted>"
        finally:
            main.DB = original_db


def test_facebook_cookie_test_statuses(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        original_db = main.DB
        try:
            main.DB = str(Path(tmp_dir) / "recipes.db")
            monkeypatch.setenv("USER_SETTINGS_ENCRYPTION_KEY", "l1k8sEHPAs6TLKG3tA4aF6k5DAt84sYI6FqdtYYdlcE=")
            main.init_db()
            _create_user()
            client = TestClient(main.app)
            assert _login(client).status_code == 200

            missing = client.post("/settings/import/facebook-cookie/test")
            assert missing.status_code == 200
            assert missing.json()["status"] == "missing_cookie"

            client.put("/settings/import/facebook-cookie", json={"facebook_cookie": "not-a-cookie"})
            invalid = client.post("/settings/import/facebook-cookie/test")
            assert invalid.status_code == 200
            assert invalid.json()["status"] == "invalid_format"

            client.put("/settings/import/facebook-cookie", json={"facebook_cookie": "c_user=123; xs=abc"})
            ok = client.post("/settings/import/facebook-cookie/test")
            assert ok.status_code == 200
            assert ok.json()["status"] == "success"
        finally:
            main.DB = original_db


def test_unreadable_facebook_cookie_reports_recovery_state_and_can_be_replaced_or_cleared(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        original_db = main.DB
        try:
            main.DB = str(Path(tmp_dir) / "recipes.db")
            monkeypatch.setenv("USER_SETTINGS_ENCRYPTION_KEY", "l1k8sEHPAs6TLKG3tA4aF6k5DAt84sYI6FqdtYYdlcE=")
            main.init_db()
            user_id = _create_user()
            client = TestClient(main.app)
            assert _login(client).status_code == 200

            conn = main.get_conn()
            conn.execute(
                '''
                INSERT INTO user_import_settings (user_id, facebook_cookie_encrypted, facebook_cookie_updated_at, updated_at)
                VALUES (?, ?, ?, ?)
                ''',
                (user_id, "%%%not-valid-base64%%%", main.utcnow_iso(), main.utcnow_iso()),
            )
            conn.commit()
            conn.close()

            get_resp = client.get("/settings/import")
            assert get_resp.status_code == 200
            payload = get_resp.json()
            assert payload["has_facebook_cookie"] is True
            assert payload["facebook_cookie_status"] == "unreadable"
            assert payload["facebook_cookie_error"]["setting"] == "facebook_cookie"
            assert "Delete or replace it in Import Settings" in payload["facebook_cookie_warning"]

            test_resp = client.post("/settings/import/facebook-cookie/test")
            assert test_resp.status_code == 200
            assert test_resp.json()["status"] == "unreadable_cookie"
            assert test_resp.json()["setting"] == "facebook_cookie"

            replace_resp = client.put("/settings/import/facebook-cookie", json={"facebook_cookie": "c_user=123; xs=abc"})
            assert replace_resp.status_code == 200
            replaced = client.get("/settings/import").json()
            assert replaced["facebook_cookie_status"] == "configured"
            assert replaced["facebook_cookie_warning"] == ""
            assert replaced["facebook_cookie_error"] is None

            clear_resp = client.delete("/settings/import/facebook-cookie")
            assert clear_resp.status_code == 200
            cleared = client.get("/settings/import").json()
            assert cleared["has_facebook_cookie"] is False
            assert cleared["facebook_cookie_status"] == "missing"
        finally:
            main.DB = original_db
