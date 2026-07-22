import socket
from unittest.mock import patch

import pytest

from backend.app import main
from backend.app.url_validation import PublicUrlValidationError, USER_FACING_PUBLIC_URL_ERROR, safe_get, validate_public_url


class _MockResponse:
    def __init__(self, url: str, *, status_code: int = 200, headers: dict | None = None, text: str = ""):
        self.url = url
        self.status_code = status_code
        self.headers = headers or {"Content-Type": "text/html; charset=utf-8"}
        self.text = text

    @property
    def is_redirect(self) -> bool:
        return self.status_code in {301, 302, 303, 307, 308}

    @property
    def is_permanent_redirect(self) -> bool:
        return self.status_code in {301, 308}

    def raise_for_status(self):
        return None


def _mock_addrinfo(ip_text: str):
    family = socket.AF_INET6 if ":" in ip_text else socket.AF_INET
    sockaddr = (ip_text, 443, 0, 0) if family == socket.AF_INET6 else (ip_text, 443)
    return [(family, socket.SOCK_STREAM, 6, "", sockaddr)]


@pytest.mark.parametrize(
    ("url", "resolved_ip"),
    [
        ("https://example.com/recipe", "93.184.216.34"),
        ("http://example.com:8080/recipe?id=1", "93.184.216.34"),
        ("https://[2606:2800:220:1:248:1893:25c8:1946]/recipe", "2606:2800:220:1:248:1893:25c8:1946"),
    ],
)
def test_validate_public_url_accepts_public_http_and_https(url, resolved_ip):
    with patch("backend.app.url_validation.socket.getaddrinfo", return_value=_mock_addrinfo(resolved_ip)):
        assert validate_public_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/recipe",
        "https://user:pass@example.com/recipe",
        "https://localhost/recipe",
        "https://localhost.localdomain/recipe",
        "https://metadata.google.internal/computeMetadata/v1/",
        "https://recipe",
        "not-a-url",
    ],
)
def test_validate_public_url_rejects_non_public_host_patterns(url):
    with patch("backend.app.url_validation.socket.getaddrinfo", return_value=_mock_addrinfo("93.184.216.34")):
        with pytest.raises(PublicUrlValidationError, match=USER_FACING_PUBLIC_URL_ERROR):
            validate_public_url(url)


@pytest.mark.parametrize(
    "resolved_ip",
    [
        "127.0.0.1",
        "10.0.0.15",
        "172.16.0.10",
        "192.168.1.20",
        "169.254.169.254",
        "224.0.0.1",
        "::1",
        "fe80::1",
        "fc00::1",
    ],
)
def test_validate_public_url_rejects_non_public_resolved_ip_ranges(resolved_ip):
    with patch("backend.app.url_validation.socket.getaddrinfo", return_value=_mock_addrinfo(resolved_ip)):
        with pytest.raises(PublicUrlValidationError, match=USER_FACING_PUBLIC_URL_ERROR):
            validate_public_url("https://example.com/recipe")


def test_validate_public_url_rejects_unresolvable_host():
    with patch("backend.app.url_validation.socket.getaddrinfo", side_effect=socket.gaierror()):
        with pytest.raises(PublicUrlValidationError, match=USER_FACING_PUBLIC_URL_ERROR):
            validate_public_url("https://example.com/recipe")


def test_safe_get_revalidates_redirect_targets():
    responses = [
        _MockResponse(
            "https://example.com/start",
            status_code=302,
            headers={"Location": "http://127.0.0.1/admin"},
        )
    ]

    def _fake_getaddrinfo(hostname, *_args, **_kwargs):
        if hostname == "example.com":
            return _mock_addrinfo("93.184.216.34")
        if hostname == "127.0.0.1":
            return _mock_addrinfo("127.0.0.1")
        raise AssertionError(f"unexpected hostname: {hostname}")

    with patch("backend.app.url_validation.socket.getaddrinfo", side_effect=_fake_getaddrinfo), patch(
        "backend.app.url_validation.requests.Session.get",
        side_effect=responses,
    ):
        with pytest.raises(PublicUrlValidationError, match=USER_FACING_PUBLIC_URL_ERROR):
            safe_get("https://example.com/start")


def test_extract_metadata_returns_controlled_error_for_blocked_direct_url():
    with pytest.raises(main.HTTPException) as exc_info:
        main.extract_metadata(url="http://127.0.0.1/recipe", _={})

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == USER_FACING_PUBLIC_URL_ERROR
