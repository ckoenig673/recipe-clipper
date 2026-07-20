import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app import main


def _create_user(email: str = 'u@example.com') -> None:
    conn = main.get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (email, password_hash, is_admin, is_active, created_at) VALUES (?, ?, 0, 1, ?)",
        (email, main.hash_password('pw123456'), main.utcnow_iso()),
    )
    conn.commit()
    conn.close()


def test_import_services_status_endpoint_reports_service_states():
    with tempfile.TemporaryDirectory() as tmp_dir:
        original_db = main.DB
        try:
            main.DB = str(Path(tmp_dir) / 'recipes.db')
            main.init_db()
            _create_user()
            client = TestClient(main.app)
            assert client.post('/auth/login', json={'email': 'u@example.com', 'password': 'pw123456'}).status_code == 200
            with patch('backend.app.main._safe_service_check', side_effect=[('online', 'http://ocr.local'), ('offline', 'http://social.local'), ('not_configured', None)]), patch('backend.app.main._ollama_status', return_value=('online', 'http://ollama.local')):
                response = client.get('/status/import-services')

            assert response.status_code == 200
            payload = response.json()
            assert payload['services']['backend']['status'] == 'online'
            assert payload['services']['ocr_worker']['status'] == 'online'
            assert payload['services']['social_downloader']['status'] == 'offline'
            assert payload['services']['whisper_processor']['status'] == 'not_configured'
            assert payload['services']['ollama']['status'] == 'online'
            assert payload['warning']
        finally:
            main.DB = original_db
