"""SSRF controls for MCP browser / fetch_url tools.

DNS-resolve before connect; deny private/link-local/metadata ranges;
optional host allowlist (global + tenant); redirect re-check; DNS pin.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlparse, urlunparse

# Hostnames known to be cloud metadata endpoints
_METADATA_HOSTS = frozenset(
    {
        "metadata.google.internal",
        "metadata.google.com",
        "metadata",
        "instance-data",
    }
)

DEFAULT_MAX_REDIRECTS = 5
DEFAULT_MAX_BYTES = 100_000


class SsrfError(ValueError):
    """Raised when a URL fails SSRF policy."""


def _parse_allowlist(raw: str | None) -> set[str] | None:
    if not raw or not str(raw).strip():
        return None
    return {h.strip().lower() for h in str(raw).split(",") if h.strip()}


def _env_get_ci(key: str) -> str | None:
    """Case-insensitive getenv (Windows may uppercase keys)."""
    val = os.getenv(key)
    if val is not None:
        return val
    key_u = key.upper()
    for ek, ev in os.environ.items():
        if ek.upper() == key_u:
            return ev
    return None


def _host_allowlist(*, tenant_id: str | None = None) -> set[str] | None:
    """Tenant allowlist wins when set; else global NSA_MCP_BROWSER_HOST_ALLOWLIST."""
    tid = (tenant_id or _env_get_ci("NSA_MCP_TENANT_ID") or "").strip()
    if tid:
        for key in (
            f"NSA_MCP_TENANT_{tid}_BROWSER_HOST_ALLOWLIST",
            f"NSA_MCP_TENANT_{tid}_NSA_MCP_BROWSER_HOST_ALLOWLIST",
        ):
            parsed = _parse_allowlist(_env_get_ci(key))
            if parsed is not None:
                return parsed
    return _parse_allowlist(_env_get_ci("NSA_MCP_BROWSER_HOST_ALLOWLIST"))


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if ip.is_loopback or ip.is_link_local or ip.is_private or ip.is_reserved:
        return True
    if ip.is_multicast or ip.is_unspecified:
        return True
    # CGNAT 100.64.0.0/10 + classic cloud metadata
    if isinstance(ip, ipaddress.IPv4Address):
        if ip in ipaddress.ip_network("100.64.0.0/10"):
            return True
        if ip == ipaddress.IPv4Address("169.254.169.254"):
            return True
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return _is_blocked_ip(ip.ipv4_mapped)
    return False


def resolve_and_validate_host(
    hostname: str,
    *,
    port: int | None = None,
    tenant_id: str | None = None,
) -> list[str]:
    """Resolve hostname; raise SsrfError if any address is blocked. Returns safe IPs."""
    host = (hostname or "").strip().lower().rstrip(".")
    if not host:
        raise SsrfError("empty hostname")
    if host in _METADATA_HOSTS:
        raise SsrfError(f"blocked metadata host: {host}")
    allow = _host_allowlist(tenant_id=tenant_id)
    if allow is not None and host not in allow:
        raise SsrfError(f"host not in NSA_MCP_BROWSER_HOST_ALLOWLIST: {host}")

    # Literal IP in hostname
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        if _is_blocked_ip(ip):
            raise SsrfError(f"blocked address: {host}")
        return [host]

    try:
        infos = socket.getaddrinfo(host, port or 0, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SsrfError(f"DNS resolution failed for {host}: {exc}") from exc
    resolved: list[str] = []
    for info in infos:
        addr = info[4][0]
        try:
            parsed_ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if _is_blocked_ip(parsed_ip):
            raise SsrfError(f"blocked resolved address {addr} for host {host}")
        resolved.append(addr)
    if not resolved:
        raise SsrfError(f"no usable addresses for {host}")
    return resolved


def validate_url_ssrf(
    url: str,
    *,
    allow_redirect_hops: int = DEFAULT_MAX_REDIRECTS,
    tenant_id: str | None = None,
) -> str:
    """Validate absolute http(s) URL against SSRF policy. Returns normalized URL."""
    if not url or not isinstance(url, str):
        raise SsrfError("url is required")
    raw = url.strip()
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    if scheme in {"file", "ftp", "data", "javascript"}:
        raise SsrfError(f"blocked scheme: {scheme}")
    if scheme not in {"http", "https"}:
        raise SsrfError('url must be an absolute http(s) URL, e.g. "https://example.com"')
    if parsed.username or parsed.password:
        raise SsrfError("URL userinfo is not allowed")
    host = parsed.hostname
    if not host:
        raise SsrfError("URL missing hostname")
    resolve_and_validate_host(host, port=parsed.port, tenant_id=tenant_id)
    return raw


def _format_ip_for_url(ip: str) -> str:
    """Bracket IPv6 literals for URL netloc."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if isinstance(addr, ipaddress.IPv6Address):
        return f"[{addr.compressed}]"
    return str(addr)


def pin_url_to_resolved_ip(
    url: str,
    *,
    tenant_id: str | None = None,
) -> tuple[str, str, list[str]]:
    """Validate URL, resolve host, return (connect_url, original_host, resolved_ips).

    connect_url uses a validated IP in the host position to close DNS-rebinding TOCTOU;
    callers must send Host: original_host.
    """
    validated = validate_url_ssrf(url, tenant_id=tenant_id)
    parsed = urlparse(validated)
    host = parsed.hostname or ""
    ips = resolve_and_validate_host(host, port=parsed.port, tenant_id=tenant_id)
    pinned_ip = ips[0]
    # Literal IP already — no rewrite needed
    try:
        ipaddress.ip_address(host)
        return validated, host, ips
    except ValueError:
        pass
    netloc = _format_ip_for_url(pinned_ip)
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    connect = urlunparse(
        (parsed.scheme, netloc, parsed.path or "", parsed.params, parsed.query, parsed.fragment)
    )
    return connect, host, ips


async def fetch_url_ssrf_safe(
    url: str,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    timeout: float = 20.0,
    tenant_id: str | None = None,
) -> dict:
    """httpx GET with per-hop SSRF checks, DNS pin, and size limit."""
    import httpx

    current = url.strip()
    redirects = 0
    final_logical_url = current
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        while True:
            connect_url, host, _ips = pin_url_to_resolved_ip(current, tenant_id=tenant_id)
            headers = {"Host": host} if host else {}
            resp = await client.get(connect_url, headers=headers)
            if resp.is_redirect:
                redirects += 1
                if redirects > max_redirects:
                    raise SsrfError(f"too many redirects (>{max_redirects})")
                loc = resp.headers.get("location")
                if not loc:
                    raise SsrfError("redirect without Location")
                # Join against logical URL (hostname), not pinned IP URL
                current = str(httpx.URL(current).join(loc))
                final_logical_url = current
                continue
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError:
                raise ValueError(f"HTTP {resp.status_code} fetching {final_logical_url}") from None
            raw = resp.content[: max_bytes + 1]
            truncated = len(raw) > max_bytes
            if truncated:
                raw = raw[:max_bytes]
            ctype = resp.headers.get("content-type", "application/octet-stream")
            try:
                text = raw.decode("utf-8")
                return {
                    "url": final_logical_url,
                    "status_code": resp.status_code,
                    "content_type": ctype,
                    "encoding": "utf-8",
                    "truncated": truncated,
                    "body": text,
                    "pinned_host": host,
                }
            except UnicodeDecodeError:
                import base64

                return {
                    "url": final_logical_url,
                    "status_code": resp.status_code,
                    "content_type": ctype,
                    "encoding": "base64",
                    "truncated": truncated,
                    "body": base64.b64encode(raw).decode("ascii"),
                    "pinned_host": host,
                }
