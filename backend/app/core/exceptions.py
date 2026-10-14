"""Custom exceptions for URL validation, security, and HTTP fetching."""


class AuditSecurityError(Exception):
    """Raised when a URL fails security validation (SSRF, prohibited IP, malformed)."""

    def __init__(self, message: str, security_code: str = "SECURITY_VIOLATION"):
        super().__init__(message)
        self.message = message
        self.security_code = security_code


class AuditFetchError(Exception):
    """Raised when an HTTP request fails during the audit (timeout, connection, DNS)."""

    def __init__(self, message: str, error_type: str = "FETCH_ERROR"):
        super().__init__(message)
        self.message = message
        self.error_type = error_type


class ResponseTooLargeError(AuditFetchError):
    """Raised when the target response body exceeds the maximum permitted size."""

    def __init__(self, max_bytes: int):
        super().__init__(
            f"Response body exceeded maximum allowed limit of {max_bytes} bytes.",
            error_type="RESPONSE_TOO_LARGE",
        )
