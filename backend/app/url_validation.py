import ipaddress
import socket
from urllib.parse import urljoin, urlparse, urlunparse

import requests


class PublicUrlValidationError(ValueError):
    pass


USER_FACING_PUBLIC_URL_ERROR = "Enter a public HTTP or HTTPS recipe URL."

LOCAL_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "localhost6",
    "localhost6.localdomain6",
}
BLOCKED_METADATA_HOSTNAMES = {
    "metadata",
    "metadata.google.internal",
    "metadata.azure.internal",
}
BLOCKED_IP_NETWORKS = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("ff00::/8"),
    ipaddress.ip_network("2001:db8::/32"),
)


def _normalized_hostname(hostname: str | None) -> str:
    return (hostname or "").rstrip(".").strip().lower()


def _is_blocked_hostname(hostname: str) -> bool:
    if not hostname:
        return True
    try:
        ipaddress.ip_address(hostname)
        return False
    except ValueError:
        pass
    if hostname in LOCAL_HOSTNAMES or hostname.endswith(".localhost"):
        return True
    if hostname in BLOCKED_METADATA_HOSTNAMES:
        return True
    if "." not in hostname:
        return True
    return False


def _is_blocked_ip(ip_text: str) -> bool:
    ip = ipaddress.ip_address(ip_text)
    if ip in ipaddress.ip_network("169.254.169.254/32"):
        return True
    if not ip.is_global:
        return True
    return any(ip in network for network in BLOCKED_IP_NETWORKS)


def validate_public_url(url: str) -> str:
    value = str(url or "").strip()
    if not value:
        raise PublicUrlValidationError(USER_FACING_PUBLIC_URL_ERROR)

    try:
        parsed = urlparse(value)
    except Exception as exc:
        raise PublicUrlValidationError(USER_FACING_PUBLIC_URL_ERROR) from exc

    if parsed.scheme not in ("http", "https"):
        raise PublicUrlValidationError(USER_FACING_PUBLIC_URL_ERROR)
    if parsed.username or parsed.password:
        raise PublicUrlValidationError(USER_FACING_PUBLIC_URL_ERROR)

    hostname = _normalized_hostname(parsed.hostname)
    if _is_blocked_hostname(hostname):
        raise PublicUrlValidationError(USER_FACING_PUBLIC_URL_ERROR)

    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise PublicUrlValidationError(USER_FACING_PUBLIC_URL_ERROR) from exc

    try:
        addrinfo = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise PublicUrlValidationError(USER_FACING_PUBLIC_URL_ERROR) from exc

    resolved_ips = {
        sockaddr[0]
        for _family, _socktype, _proto, _canonname, sockaddr in addrinfo
        if sockaddr and sockaddr[0]
    }
    if not resolved_ips:
        raise PublicUrlValidationError(USER_FACING_PUBLIC_URL_ERROR)

    for ip_text in resolved_ips:
        if _is_blocked_ip(ip_text):
            raise PublicUrlValidationError(USER_FACING_PUBLIC_URL_ERROR)

    return urlunparse(parsed._replace(fragment=""))


def safe_get(
    url: str,
    *,
    headers: dict | None = None,
    timeout: float = 8,
    max_redirects: int = 5,
    session: requests.Session | None = None,
) -> requests.Response:
    current_url = validate_public_url(url)
    owns_session = session is None
    active_session = session or requests.Session()
    try:
        for _ in range(max_redirects + 1):
            response = active_session.get(
                current_url,
                headers=headers,
                timeout=timeout,
                allow_redirects=False,
            )
            if response.is_redirect or response.is_permanent_redirect:
                location = (response.headers.get("Location") or "").strip()
                if not location:
                    return response
                current_url = validate_public_url(urljoin(current_url, location))
                continue
            return response
    finally:
        if owns_session:
            active_session.close()
    raise PublicUrlValidationError(USER_FACING_PUBLIC_URL_ERROR)
