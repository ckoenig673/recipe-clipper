from __future__ import annotations

from urllib.parse import urlparse

NETSCAPE_HTTPONLY_PREFIX = "#httponly_"


def normalize_hostname(hostname: str | None) -> str:
    return (hostname or "").strip().lstrip(".").rstrip(".").lower()


def normalize_netscape_cookie_domain(domain_field: str | None) -> str:
    normalized = (domain_field or "").strip()
    if normalized.lower().startswith(NETSCAPE_HTTPONLY_PREFIX):
        normalized = normalized[len(NETSCAPE_HTTPONLY_PREFIX) :]
    return normalize_hostname(normalized)


def hostname_matches_domain(hostname: str | None, expected_domain: str) -> bool:
    normalized_host = normalize_hostname(hostname)
    normalized_domain = normalize_hostname(expected_domain)
    if not normalized_host or not normalized_domain:
        return False
    return normalized_host == normalized_domain or normalized_host.endswith(f".{normalized_domain}")


def hostname_matches_any(hostname: str | None, domains: tuple[str, ...]) -> bool:
    return any(hostname_matches_domain(hostname, domain) for domain in domains)


def parse_hostname(value: str) -> str:
    try:
        return normalize_hostname(urlparse(value or "").hostname)
    except Exception:
        return ""


def url_hostname_matches_any(value: str, domains: tuple[str, ...]) -> bool:
    return hostname_matches_any(parse_hostname(value), domains)
