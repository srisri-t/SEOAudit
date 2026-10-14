import socket
from unittest.mock import patch

import pytest

from app.core.exceptions import AuditSecurityError
from app.core.url_validator import validate_and_normalize_url


class TestUrlValidation:
    """Unit tests for URL syntax, scheme, and normalization."""

    def test_valid_https_url_normalized(self):
        url = "https://WWW.Example.COM/path/to/page?q=test#heading"
        normalized = validate_and_normalize_url(url, resolve_dns=False)
        assert normalized == "https://www.example.com/path/to/page?q=test"
        # Fragment is stripped
        assert "#" not in normalized

    def test_valid_http_url(self):
        url = "http://example.com"
        normalized = validate_and_normalize_url(url, resolve_dns=False)
        assert normalized == "http://example.com/"

    def test_empty_and_blank_urls_rejected(self):
        with pytest.raises(AuditSecurityError, match="non-empty string"):
            validate_and_normalize_url("", resolve_dns=False)
        with pytest.raises(AuditSecurityError, match="cannot be blank"):
            validate_and_normalize_url("   ", resolve_dns=False)

    def test_unsupported_schemes_rejected(self):
        for bad_url in [
            "ftp://example.com/file.txt",
            "javascript:alert(1)",
            "file:///etc/passwd",
            "data:text/html,<h1>Hello</h1>",
            "gopher://example.com",
        ]:
            with pytest.raises(AuditSecurityError, match="Unsupported URL scheme"):
                validate_and_normalize_url(bad_url, resolve_dns=False)

    def test_embedded_credentials_rejected(self):
        bad_urls = [
            "http://user:pass@example.com",
            "https://admin@example.com/login",
            "https://user:password@target.org",
        ]
        for url in bad_urls:
            with pytest.raises(AuditSecurityError, match="embedded credentials"):
                validate_and_normalize_url(url, resolve_dns=False)

    def test_missing_hostname_rejected(self):
        with pytest.raises(AuditSecurityError, match="missing a valid hostname"):
            validate_and_normalize_url("http:///path", resolve_dns=False)

    def test_invalid_port_rejected(self):
        with pytest.raises(AuditSecurityError, match="Invalid port number"):
            validate_and_normalize_url("http://example.com:70000", resolve_dns=False)


class TestSsrfProhibitedDestinations:
    """Security tests verifying rejection of loopback, private, and internal addresses."""

    @pytest.mark.parametrize(
        "prohibited_url",
        [
            # Localhost names
            "http://localhost",
            "http://localhost:8000",
            "http://sub.localhost",
            "http://myhost.local",
            "http://server.internal",
            "http://router.lan",
            # Loopback IPv4
            "http://127.0.0.1",
            "http://127.0.0.1:8080/admin",
            "http://127.1.2.3",
            "http://0.0.0.0",
            # Private RFC 1918 IPv4
            "http://10.0.0.1",
            "http://10.254.254.254",
            "http://172.16.0.1",
            "http://172.31.255.255",
            "http://192.168.1.1",
            "http://192.168.0.100",
            # Link-Local and Cloud Metadata (AWS/GCP/Azure)
            "http://169.254.169.254/latest/meta-data/",
            "http://169.254.1.1",
            # Shared address space & Test nets
            "http://100.64.0.1",
            "http://192.0.2.1",
            "http://198.51.100.1",
            "http://203.0.113.1",
            # Numeric integer representations of 127.0.0.1
            "http://2130706433",
            # Loopback IPv6
            "http://[::1]",
            "http://[::]",
            # Unique Local & Link-local IPv6
            "http://[fc00::1]",
            "http://[fe80::1]",
            # IPv4-mapped IPv6
            "http://[::ffff:127.0.0.1]",
            "http://[::ffff:10.0.0.1]",
            "http://[::ffff:169.254.169.254]",
        ],
    )
    def test_prohibited_literal_ips_and_hosts(self, prohibited_url):
        with pytest.raises(AuditSecurityError):
            validate_and_normalize_url(prohibited_url, resolve_dns=False)

    def test_dns_resolving_to_private_ip_is_blocked(self):
        """Simulate a public domain name resolving to an internal private IP (DNS rebinding / SSRF)."""
        mock_addr_info = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.50", 80))
        ]
        with patch("socket.getaddrinfo", return_value=mock_addr_info):
            with pytest.raises(AuditSecurityError, match="resolved to prohibited IP"):
                validate_and_normalize_url("http://malicious-internal-rebinding.com", resolve_dns=True)

    def test_dns_resolving_to_loopback_is_blocked(self):
        mock_addr_info = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))
        ]
        with patch("socket.getaddrinfo", return_value=mock_addr_info):
            with pytest.raises(AuditSecurityError, match="resolved to prohibited IP"):
                validate_and_normalize_url("http://spoofed-local.com", resolve_dns=True)

    def test_dns_resolving_to_valid_public_ip_succeeds(self):
        mock_addr_info = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ]
        with patch("socket.getaddrinfo", return_value=mock_addr_info):
            res = validate_and_normalize_url("https://example.com/test", resolve_dns=True)
            assert res == "https://example.com/test"

    def test_dns_resolution_failure_raises_security_error(self):
        with patch("socket.getaddrinfo", side_effect=socket.gaierror("Name or service not known")):
            with pytest.raises(AuditSecurityError, match="DNS resolution failed"):
                validate_and_normalize_url("https://non-existent-domain-xyz123.com", resolve_dns=True)
