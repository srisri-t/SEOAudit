"""URL and website origin normalization utilities for audit run comparison."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def normalize_url_for_matching(raw_url: str) -> str:
    """Normalize a web page URL for deterministic matching across audit runs.

    Rules applied:
    1. Trims leading and trailing whitespace.
    2. Lowercases scheme and network location (hostname and port).
    3. Removes standard default ports (80 for http, 443 for https).
    4. Strips URL fragments completely (#section does not represent a separate page).
    5. Normalizes trailing slashes:
       - Root path stays "/" (e.g. "https://example.com/" and "https://example.com" -> "https://example.com/")
       - Non-root paths have trailing slashes removed (e.g. "https://example.com/about/" -> "https://example.com/about")
    6. Preserves query parameters while sorting keys deterministically for consistent matching.
    """
    if not raw_url or not raw_url.strip():
        return ""

    url = raw_url.strip()
    parts = urlsplit(url)

    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()

    # Normalize default ports in netloc
    if ":" in netloc:
        host, _, port_str = netloc.rpartition(":")
        try:
            port = int(port_str)
            if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
                netloc = host
        except ValueError:
            pass

    # Normalize path
    path = parts.path
    if not path or path == "/":
        path = "/"
    else:
        # Strip trailing slash for non-root paths
        path = path.rstrip("/")

    # Normalize query string (sort keys deterministically while preserving parameter pairs)
    query = parts.query
    if query:
        query_pairs = parse_qsl(query, keep_blank_values=True)
        query_pairs.sort(key=lambda pair: (pair[0], pair[1]))
        query = urlencode(query_pairs)
    else:
        query = ""

    # Fragment is stripped (empty string)
    return urlunsplit((scheme, netloc, path, query, ""))


def normalize_origin(origin_or_url: str) -> str:
    """Extract and normalize the scheme and authority (host:port) of an origin or URL.

    Used to compare the website scope of two audit runs.
    """
    if not origin_or_url or not origin_or_url.strip():
        return ""

    val = origin_or_url.strip()
    # Add dummy scheme if bare hostname provided
    if "://" not in val:
        val = f"https://{val}"

    parts = urlsplit(val)
    scheme = parts.scheme.lower() or "https"
    netloc = parts.netloc.lower()

    # Strip default ports
    if ":" in netloc:
        host, _, port_str = netloc.rpartition(":")
        try:
            port = int(port_str)
            if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
                netloc = host
        except ValueError:
            pass

    return f"{scheme}://{netloc}"


def are_origins_compatible(origin_a: str, origin_b: str) -> bool:
    """Determine whether two target origins represent the same website scope."""
    norm_a = normalize_origin(origin_a)
    norm_b = normalize_origin(origin_b)

    if not norm_a or not norm_b:
        return False

    return norm_a == norm_b
