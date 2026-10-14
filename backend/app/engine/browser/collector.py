"""Event listeners and collectors for browser console messages, page errors, and failed requests."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging

from app.models.audit import ConsoleMessage, PageException

logger = logging.getLogger(__name__)


MAX_CONSOLE_ERRORS = 50
MAX_PAGE_EXCEPTIONS = 20
MAX_FAILED_SUBRESOURCES = 50
MAX_STRING_LENGTH = 1000
MAX_STACK_LENGTH = 2000


@dataclass
class BrowserCollector:
    """Accumulates console errors, page exceptions, and subresource failures during page execution.

    Enforces deterministic size and count limits to prevent memory bloat or denial of service
    from noisy or malicious target pages.
    """

    console_errors: list[ConsoleMessage] = field(default_factory=list)
    page_exceptions: list[PageException] = field(default_factory=list)
    failed_subresources: list[str] = field(default_factory=list)
    blocked_security_requests: list[str] = field(default_factory=list)

    def attach_to_page(self, page) -> None:
        """Register diagnostic event listeners on a Playwright Page."""
        page.on("console", self._handle_console)
        page.on("pageerror", self._handle_page_error)
        page.on("requestfailed", self._handle_request_failed)

    def _handle_console(self, msg) -> None:
        if len(self.console_errors) >= MAX_CONSOLE_ERRORS:
            return

        msg_type = (msg.type or "").lower()
        if msg_type in ("error", "warning"):
            location_str = None
            try:
                loc = msg.location
                if loc and loc.get("url"):
                    raw_loc = f"{loc.get('url')}:{loc.get('lineNumber', 0)}"
                    location_str = raw_loc[:MAX_STRING_LENGTH]
            except Exception:
                location_str = None

            raw_text = msg.text or ""
            bounded_text = raw_text[:MAX_STRING_LENGTH] if len(raw_text) > MAX_STRING_LENGTH else raw_text

            self.console_errors.append(
                ConsoleMessage(
                    level=msg_type,
                    text=bounded_text,
                    location=location_str,
                )
            )

    def _handle_page_error(self, exc: Exception) -> None:
        if len(self.page_exceptions) >= MAX_PAGE_EXCEPTIONS:
            return

        raw_message = str(exc)
        bounded_message = raw_message[:MAX_STRING_LENGTH] if len(raw_message) > MAX_STRING_LENGTH else raw_message
        raw_stack = getattr(exc, "stack", None)
        bounded_stack = raw_stack[:MAX_STACK_LENGTH] if raw_stack and len(raw_stack) > MAX_STACK_LENGTH else raw_stack

        self.page_exceptions.append(
            PageException(
                message=bounded_message,
                stack=bounded_stack,
            )
        )
        logger.debug("Captured uncaught browser page error: %s", bounded_message)

    def _handle_request_failed(self, request) -> None:
        if len(self.failed_subresources) >= MAX_FAILED_SUBRESOURCES:
            return

        failure = request.failure or "Failed"
        req_url = request.url
        # Ignore requests that were aborted intentionally by client/security route handler
        if "blockedbyclient" in str(failure).lower():
            return
        entry = f"{req_url} ({failure})"
        self.failed_subresources.append(entry[:MAX_STRING_LENGTH])
