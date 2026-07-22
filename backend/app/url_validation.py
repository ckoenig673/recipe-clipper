import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from requests.adapters import HTTPAdapter
from urllib3 import PoolManager
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connection import connection as urllib3_connection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import ConnectTimeoutError, NameResolutionError, NewConnectionError
from urllib3.poolmanager import PoolKey, _default_key_normalizer


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


@dataclass(frozen=True)
class _ResolvedPublicUrl:
    normalized_url: str
    origin_prefix: str
    scheme: str
    hostname: str
    host_header: str
    port: int
    resolved_ips: tuple[str, ...]


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


def _resolve_public_url(url: str) -> _ResolvedPublicUrl:
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

    normalized_url = urlunparse(parsed._replace(fragment=""))
    return _ResolvedPublicUrl(
        normalized_url=normalized_url,
        origin_prefix=f"{parsed.scheme}://{parsed.netloc}",
        scheme=parsed.scheme,
        hostname=hostname,
        host_header=parsed.netloc,
        port=port,
        resolved_ips=tuple(sorted(resolved_ips)),
    )


def validate_public_url(url: str) -> str:
    return _resolve_public_url(url).normalized_url


class _ValidatedAddressAdapter(HTTPAdapter):
    def __init__(self, target: _ResolvedPublicUrl, destination_ip: str):
        self._target = target
        self._destination_ip = destination_ip
        super().__init__()

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        pool_kwargs["destination_ip"] = self._destination_ip
        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            **pool_kwargs,
        )
        self.poolmanager.pool_classes_by_scheme = {
            "http": _ValidatedHTTPConnectionPool,
            "https": _ValidatedHTTPSConnectionPool,
        }
        self.poolmanager.key_fn_by_scheme = {
            "http": _validated_pool_key,
            "https": _validated_pool_key,
        }

    def get_connection_with_tls_context(self, request, verify, proxies=None, cert=None):
        host_params, pool_kwargs = self.build_connection_pool_key_attributes(request, verify, cert)
        host_params["port"] = self._target.port
        host_params["scheme"] = self._target.scheme
        if self._target.scheme == "https":
            pool_kwargs["assert_hostname"] = self._target.hostname
            pool_kwargs["server_hostname"] = self._target.hostname
        return self.poolmanager.connection_from_host(**host_params, pool_kwargs=pool_kwargs)


class _ValidatedHTTPConnection(HTTPConnection):
    def __init__(self, *args, destination_ip: str, **kwargs):
        self._validated_destination_ip = destination_ip
        super().__init__(*args, **kwargs)

    def _new_conn(self):
        try:
            sock = urllib3_connection.create_connection(
                (self._validated_destination_ip, self.port),
                self.timeout,
                source_address=self.source_address,
                socket_options=self.socket_options,
            )
        except socket.gaierror as exc:
            raise NameResolutionError(self.host, self, exc) from exc
        except TimeoutError as exc:
            raise ConnectTimeoutError(
                self,
                f"Connection to {self.host} timed out. (connect timeout={self.timeout})",
            ) from exc
        except OSError as exc:
            raise NewConnectionError(self, f"Failed to establish a new connection: {exc}") from exc
        return sock


class _ValidatedHTTPSConnection(HTTPSConnection):
    def __init__(self, *args, destination_ip: str, **kwargs):
        self._validated_destination_ip = destination_ip
        super().__init__(*args, **kwargs)

    def _new_conn(self):
        try:
            sock = urllib3_connection.create_connection(
                (self._validated_destination_ip, self.port),
                self.timeout,
                source_address=self.source_address,
                socket_options=self.socket_options,
            )
        except socket.gaierror as exc:
            raise NameResolutionError(self.host, self, exc) from exc
        except TimeoutError as exc:
            raise ConnectTimeoutError(
                self,
                f"Connection to {self.host} timed out. (connect timeout={self.timeout})",
            ) from exc
        except OSError as exc:
            raise NewConnectionError(self, f"Failed to establish a new connection: {exc}") from exc
        return sock


class _ValidatedHTTPConnectionPool(HTTPConnectionPool):
    ConnectionCls = _ValidatedHTTPConnection


class _ValidatedHTTPSConnectionPool(HTTPSConnectionPool):
    ConnectionCls = _ValidatedHTTPSConnection


def _validated_pool_key(request_context):
    normalized_context = {key: value for key, value in request_context.items() if key != "destination_ip"}
    return _default_key_normalizer(PoolKey, normalized_context)


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
        # Flow:
        # 1. Normalize and resolve the destination hostname.
        # 2. Reject any non-public resolved address.
        # 3. Bind the outbound socket to one validated IP literal so the HTTP client
        #    never performs a second hostname lookup during connect.
        # 4. Preserve the original hostname in the Host header and HTTPS SNI/cert checks.
        # 5. Re-run the same process for every redirect target before following it.
        for _ in range(max_redirects + 1):
            target = _resolve_public_url(current_url)
            response = None
            last_error = None
            for destination_ip in target.resolved_ips:
                adapter = _ValidatedAddressAdapter(target, destination_ip)
                original_adapters = active_session.adapters.copy()
                try:
                    active_session.mount(target.origin_prefix, adapter)
                    response = active_session.get(
                        target.normalized_url,
                        headers=headers,
                        timeout=timeout,
                        allow_redirects=False,
                    )
                    break
                except requests.RequestException as exc:
                    last_error = exc
                finally:
                    active_session.adapters = original_adapters
                    adapter.close()
            if response is None:
                if last_error is not None:
                    raise last_error
                raise PublicUrlValidationError(USER_FACING_PUBLIC_URL_ERROR)
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
