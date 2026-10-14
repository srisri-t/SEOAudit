"""URL validation, normalization, and SSRF prevention module.

Security Design & Defense-in-Depth:
1. Scheme Enforcement: Strictly allows 'http' and 'https' schemes only.
2. Credentials Rejection: Rejects any URL containing embedded credentials (e.g., user:pass@host).
3. Hostname Sanity: Rejects empty hosts, localhost labels, and internal domain suffixes.
4. Literal IP Filtering: Rejects private (RFC 1918), loopback, link-local (cloud metadata),
   multicast, and reserved IP ranges (both IPv4 and IPv6).
5. DNS Resolution Verification: Resolves hostnames before connections to verify all resolved
   IP addresses against prohibited network blocks, preventing DNS rebinding to internal infrastructure.
6. Documentation of TOCTOU: In standard socket environments, there remains a brief Time-Of-Check
   to Time-Of-Use (TOCTOU) window between DNS verification and the socket connect call. This is
   mitigated by per-hop validation during redirects and documented in project security notes.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse, urlunparse

from app.core.exceptions import AuditSecurityError

# Prohibited internal/private network ranges (CIDR blocks)
PROHIBITED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),          # Current network (local broadcast)
    ipaddress.ip_network("10.0.0.0/8"),         # Private-use (RFC 1918)
    ipaddress.ip_network("100.64.0.0/10"),      # Shared Address Space (CGNAT)
    ipaddress.ip_network("127.0.0.0/8"),        # Loopback
    ipaddress.ip_network("169.254.0.0/16"),     # Link-Local & AWS/GCP/Azure Cloud Metadata (169.254.169.254)
    ipaddress.ip_network("172.16.0.0/12"),      # Private-use (RFC 1918)
    ipaddress.ip_network("192.0.0.0/24"),       # IETF Protocol Assignments
    ipaddress.ip_network("192.0.2.0/24"),       # Documentation (TEST-NET-1)
    ipaddress.ip_network("192.168.0.0/16"),     # Private-use (RFC 1918)
    ipaddress.ip_network("198.18.0.0/15"),      # Benchmarking
    ipaddress.ip_network("198.51.100.0/24"),    # Documentation (TEST-NET-2)
    ipaddress.ip_network("203.0.113.0/24"),     # Documentation (TEST-NET-3)
    ipaddress.ip_network("224.0.0.0/4"),        # Multicast
    ipaddress.ip_network("240.0.0.0/4"),        # Reserved
    ipaddress.ip_network("255.255.255.255/32"), # Broadcast
    # IPv6 prohibited blocks
    ipaddress.ip_network("::1/128"),            # Loopback
    ipaddress.ip_network("::/128"),             # Unspecified
    ipaddress.ip_network("::ffff:0:0/96"),      # IPv4-mapped IPv6
    ipaddress.ip_network("64:ff9b::/96"),       # IPv4/IPv6 translation
    ipaddress.ip_network("100::/64"),           # Discard prefix
    ipaddress.ip_network("2001:db8::/32"),      # Documentation
    ipaddress.ip_network("fc00::/7"),           # Unique Local Address (ULA)
    ipaddress.ip_network("fe80::/10"),          # Link-local Unicast
    ipaddress.ip_network("ff00::/8"),           # Multicast
]

# Hostnames prohibited before DNS lookup
PROHIBITED_HOST_SUFFIXES = (
    "localhost",
    ".localhost",
    ".local",
    ".internal",
    ".lan",
    ".localdomain",
    ".corp",
    ".home",
)


def is_prohibited_ip(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True if an IP belongs to private, loopback, or reserved networks."""
    # Check if IPv6 is an IPv4-mapped IPv6 address (e.g. ::ffff:127.0.0.1)
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped:
        ip_obj = ip_obj.ipv4_mapped

    if (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    ):
        return True

    return any(ip_obj in network for network in PROHIBITED_NETWORKS)


def check_ip_str(host_str: str) -> None:
    """Check literal IP address string or alternative numeric representations."""
    cleaned = host_str.strip("[]")

    # Check decimal integer IP representation (e.g., 2130706433 = 127.0.0.1)
    if re.fullmatch(r"\d+", cleaned):
        try:
            num = int(cleaned)
            if 0 <= num <= 4294967295:
                ip_obj = ipaddress.IPv4Address(num)
                if is_prohibited_ip(ip_obj):
                    raise AuditSecurityError(
                        f"Prohibited numeric IP address representation detected: {cleaned} ({ip_obj})",
                        security_code="PROHIBITED_IP",
                    )
        except ValueError:
            pass

    # Standard IP address parsing
    try:
        ip_obj = ipaddress.ip_address(cleaned)
        if is_prohibited_ip(ip_obj):
            raise AuditSecurityError(
                f"Prohibited IP address destination detected: {cleaned}",
                security_code="PROHIBITED_IP",
            )
    except ValueError:
        # Not a literal IP address string, proceeding to hostname checks
        pass


def validate_and_normalize_url(raw_url: str, resolve_dns: bool = True) -> str:
    """Validate, normalize, and verify a target URL for safe HTTP auditing.

    Args:
        raw_url: The unvalidated input URL.
        resolve_dns: Whether to perform live DNS resolution checks against SSRF.

    Returns:
        Normalized safe URL string.

    Raises:
        AuditSecurityError: If URL fails security, syntax, or network checks.
    """
    if not raw_url or not isinstance(raw_url, str):
        raise AuditSecurityError("URL must be a non-empty string.", security_code="EMPTY_URL")

    cleaned = raw_url.strip()
    if not cleaned:
        raise AuditSecurityError("URL cannot be blank.", security_code="EMPTY_URL")

    # Parse URL
    try:
        parsed = urlparse(cleaned)
    except Exception as e:
        raise AuditSecurityError(f"Malformed URL structure: {e}", security_code="MALFORMED_URL") from e

    # 1. Scheme Check
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise AuditSecurityError(
            f"Unsupported URL scheme '{scheme}'. Only HTTP and HTTPS are permitted.",
            security_code="UNSUPPORTED_SCHEME",
        )

    # 2. Hostname Check
    hostname = parsed.hostname
    if not hostname:
        raise AuditSecurityError("URL is missing a valid hostname.", security_code="MISSING_HOSTNAME")

    # 3. Credentials Check
    if parsed.username or parsed.password or "@" in (parsed.netloc or ""):
        raise AuditSecurityError(
            "URLs containing embedded credentials (username/password) are strictly prohibited.",
            security_code="CREDENTIALS_PROHIBITED",
        )

    # 4. Port Validation
    try:
        port = parsed.port
    except ValueError as err:
        raise AuditSecurityError(f"Invalid port number: {err}", security_code="INVALID_PORT") from err

    if port is not None and not (1 <= port <= 65535):
        raise AuditSecurityError(f"Invalid port number: {port}", security_code="INVALID_PORT")

    # 5. Prohibited Hostname Labels Check
    host_lower = hostname.lower()
    if host_lower in ("localhost", "localhost.localdomain") or any(
        host_lower.endswith(suffix) for suffix in PROHIBITED_HOST_SUFFIXES
    ):
        raise AuditSecurityError(
            f"Prohibited internal host destination '{hostname}' is not permitted.",
            security_code="PROHIBITED_HOST",
        )

    # 6. Literal IP Validation
    check_ip_str(hostname)

    # 7. DNS Resolution Check (SSRF Prevention)
    if resolve_dns:
        target_port = port or (443 if scheme == "https" else 80)
        try:
            addr_info = socket.getaddrinfo(
                hostname,
                target_port,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as err:
            raise AuditSecurityError(
                f"DNS resolution failed for host '{hostname}': {err}",
                security_code="DNS_RESOLUTION_FAILED",
            ) from err

        if not addr_info:
            raise AuditSecurityError(
                f"No DNS records resolved for host '{hostname}'.",
                security_code="DNS_NO_RECORDS",
            )

        for item in addr_info:
            sockaddr = item[4]
            ip_str = sockaddr[0]
            try:
                ip_obj = ipaddress.ip_address(ip_str)
                if is_prohibited_ip(ip_obj):
                    raise AuditSecurityError(
                        f"Host '{hostname}' resolved to prohibited IP address '{ip_str}'.",
                        security_code="PROHIBITED_RESOLVED_IP",
                    )
            except ValueError:
                continue

    # 8. Normalization
    # Lowercase scheme and host, default path to '/' if empty, preserve query, strip fragment
    norm_path = parsed.path if parsed.path else "/"
    # Include port in netloc only if non-standard
    if port and ((scheme == "http" and port != 80) or (scheme == "https" and port != 443)):
        norm_netloc = f"{host_lower}:{port}"
    else:
        norm_netloc = host_lower

    normalized = urlunparse((
        scheme,
        norm_netloc,
        norm_path,
        parsed.params,
        parsed.query,
        "",  # Fragment is stripped
    ))

    return normalized
