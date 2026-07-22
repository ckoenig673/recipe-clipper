import socket
from unittest.mock import patch

import pytest
import requests
from requests.cookies import RequestsCookieJar

from backend.app import main
from backend.app.url_validation import (
    PublicUrlValidationError,
    USER_FACING_PUBLIC_URL_ERROR,
    _ResolvedPublicUrl,
    _ValidatedAddressAdapter,
    safe_get,
    validate_public_url,
)


class _MockResponse:
    def __init__(self, url: str, *, status_code: int = 200, headers: dict | None = None, text: str = ""):
        self.url = url
        self.status_code = status_code
        self.headers = headers or {"Content-Type": "text/html; charset=utf-8"}
        self.text = text
        self.history = []
        self.cookies = RequestsCookieJar()
        self.raw = None
        self.request = None

    @property
    def is_redirect(self) -> bool:
        return self.status_code in {301, 302, 303, 307, 308}

    @property
    def is_permanent_redirect(self) -> bool:
        return self.status_code in {301, 308}

    def raise_for_status(self):
        return None

    @property
    def content(self) -> bytes:
        return self.text.encode("utf-8")


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


def test_safe_get_binds_https_request_to_validated_ipv4_address():
    attempted_destinations = []

    def _fake_create_connection(address, timeout, source_address=None, socket_options=None):
        attempted_destinations.append(address)
        assert address == ("93.184.216.34", 443)
        assert source_address is None
        assert socket_options is not None
        raise requests.exceptions.ConnectionError("stop after destination assertion")

    with patch("backend.app.url_validation.socket.getaddrinfo", return_value=_mock_addrinfo("93.184.216.34")), patch(
        "backend.app.url_validation.urllib3_connection.create_connection",
        side_effect=_fake_create_connection,
    ):
        with pytest.raises(requests.exceptions.ConnectionError, match="stop after destination assertion"):
            safe_get("https://example.com/recipe")

    assert attempted_destinations == [("93.184.216.34", 443)]


def test_safe_get_preserves_original_hostname_visible_to_application_code():
    def _fake_send(self, request, **_kwargs):
        assert request.url == "https://example.com/recipe"
        assert request.headers.get("Host") is None
        return _MockResponse("https://example.com/recipe")

    with patch("backend.app.url_validation.socket.getaddrinfo", return_value=_mock_addrinfo("93.184.216.34")), patch(
        "requests.adapters.HTTPAdapter.send",
        autospec=True,
        side_effect=_fake_send,
    ):
        response = safe_get("https://example.com/recipe")

    assert response.url == "https://example.com/recipe"


def test_safe_get_binds_https_request_to_validated_ipv6_address():
    attempted_destinations = []

    def _fake_create_connection(address, timeout, source_address=None, socket_options=None):
        attempted_destinations.append(address)
        assert address == ("2606:2800:220:1:248:1893:25c8:1946", 443)
        raise requests.exceptions.ConnectionError("stop after destination assertion")

    with patch(
        "backend.app.url_validation.socket.getaddrinfo",
        return_value=_mock_addrinfo("2606:2800:220:1:248:1893:25c8:1946"),
    ), patch(
        "backend.app.url_validation.urllib3_connection.create_connection",
        side_effect=_fake_create_connection,
    ):
        with pytest.raises(requests.exceptions.ConnectionError, match="stop after destination assertion"):
            safe_get("https://example.com/recipe")

    assert attempted_destinations == [("2606:2800:220:1:248:1893:25c8:1946", 443)]


def test_safe_get_resists_dns_rebinding_between_validation_and_connect():
    addrinfo_calls = []

    def _fake_getaddrinfo(hostname, port, *args, **kwargs):
        addrinfo_calls.append((hostname, port))
        if hostname == "example.com":
            return _mock_addrinfo("93.184.216.34")
        if hostname == "93.184.216.34":
            return _mock_addrinfo("93.184.216.34")
        if hostname == "169.254.169.254":
            return _mock_addrinfo("169.254.169.254")
        raise AssertionError(f"unexpected hostname: {hostname}")

    def _fake_create_connection(address, timeout, source_address=None, socket_options=None):
        assert address == ("93.184.216.34", 443)
        raise requests.exceptions.ConnectionError("stop after destination assertion")

    with patch("backend.app.url_validation.socket.getaddrinfo", side_effect=_fake_getaddrinfo), patch(
        "backend.app.url_validation.urllib3_connection.create_connection",
        side_effect=_fake_create_connection,
    ):
        with pytest.raises(requests.exceptions.ConnectionError, match="stop after destination assertion"):
            safe_get("https://example.com/recipe")

    assert ("example.com", 443) in addrinfo_calls
    assert ("169.254.169.254", 443) not in addrinfo_calls


def test_validated_address_adapter_preserves_https_hostname_for_tls():
    target = _ResolvedPublicUrl(
        normalized_url="https://example.com/recipe",
        origin_prefix="https://example.com",
        scheme="https",
        hostname="example.com",
        host_header="example.com",
        port=443,
        resolved_ips=("93.184.216.34",),
    )
    adapter = _ValidatedAddressAdapter(target, "93.184.216.34")
    request = requests.Request("GET", target.normalized_url).prepare()

    with patch.object(adapter.poolmanager, "connection_from_host", return_value=object()) as mock_connection_from_host:
        adapter.get_connection_with_tls_context(request, verify=True)

    _args, kwargs = mock_connection_from_host.call_args
    assert kwargs["host"] == "example.com"
    assert kwargs["port"] == 443
    assert kwargs["scheme"] == "https"
    assert kwargs["pool_kwargs"]["assert_hostname"] == "example.com"
    assert kwargs["pool_kwargs"]["server_hostname"] == "example.com"


def test_validated_https_connection_preserves_sni_and_certificate_hostname():
    connection = adapter = None
    target = _ResolvedPublicUrl(
        normalized_url="https://example.com/recipe",
        origin_prefix="https://example.com",
        scheme="https",
        hostname="example.com",
        host_header="example.com",
        port=443,
        resolved_ips=("93.184.216.34",),
    )
    adapter = _ValidatedAddressAdapter(target, "93.184.216.34")
    pool = adapter.poolmanager.connection_from_host(
        host="example.com",
        port=443,
        scheme="https",
        pool_kwargs={"assert_hostname": "example.com", "server_hostname": "example.com"},
    )
    connection = pool._new_conn()

    assert connection.host == "example.com"
    assert connection.server_hostname == "example.com"
    assert connection.assert_hostname == "example.com"


def test_extract_metadata_returns_controlled_error_for_blocked_direct_url():
    with pytest.raises(main.HTTPException) as exc_info:
        main.extract_metadata(url="http://127.0.0.1/recipe", _={})

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == USER_FACING_PUBLIC_URL_ERROR
