"""API router for single-URL technical SEO audits."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from app.core.exceptions import (
    AuditFetchError,
    AuditSecurityError,
    ResponseTooLargeError,
)
from app.engine.runner import run_single_url_audit
from app.models.audit import AuditRequest, AuditResponse, BrowserAuditResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/audits", tags=["audits"])


@router.post(
    "/url",
    response_model=AuditResponse,
    status_code=status.HTTP_200_OK,
    summary="Audit Single Web Page URL",
    description=(
        "Executes a comprehensive, real-time technical SEO audit for a single HTTP/HTTPS URL. "
        "Enforces strict SSRF protections against internal, loopback, and private networks."
    ),
)
async def audit_url_endpoint(payload: AuditRequest) -> AuditResponse:
    """Audit single URL endpoint handler."""
    target_url = payload.url.strip() if payload.url else ""

    if not target_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The 'url' parameter cannot be empty.",
        )

    try:
        result = await run_single_url_audit(
            target_url=target_url,
            include_browser=payload.include_browser,
        )
        return result
    except AuditSecurityError as err:
        logger.warning("Audit blocked due to security validation: %s", err.message)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Security check failed: {err.message}",
        ) from err
    except ResponseTooLargeError as err:
        logger.warning("Target URL exceeded maximum size: %s", err.message)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=err.message,
        ) from err
    except AuditFetchError as err:
        logger.info("Audit fetch failed for URL: %s", err.message)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unable to fetch target page: {err.message}",
        ) from err
    except Exception as err:
        # Catch-all to ensure raw stack traces or internal environment details are never leaked
        logger.exception("Unexpected error during audit execution")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while auditing the target page.",
        ) from err


@router.post(
    "/browser",
    response_model=BrowserAuditResult,
    status_code=status.HTTP_200_OK,
    summary="Audit Page in Headless Browser",
    description=(
        "Executes dynamic client-side rendering in headless Chromium, capturing DOM title, "
        "description, canonical URL, robots directives, console errors, and runtime exceptions."
    ),
)
async def audit_browser_endpoint(payload: AuditRequest) -> BrowserAuditResult:
    """Dedicated browser audit endpoint."""
    target_url = payload.url.strip() if payload.url else ""

    if not target_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The 'url' parameter cannot be empty.",
        )

    from app.core.exceptions import BrowserNavigationError, BrowserUnavailableError
    from app.engine.browser.auditor import run_browser_audit

    try:
        result = await run_browser_audit(target_url=target_url)
        return result
    except AuditSecurityError as err:
        logger.warning("Browser audit blocked due to security validation: %s", err.message)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Security check failed: {err.message}",
        ) from err
    except BrowserUnavailableError as err:
        logger.warning("Browser audit unavailable: %s", err.message)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=err.message,
        ) from err
    except BrowserNavigationError as err:
        logger.info("Browser navigation failed: %s", err.message)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=err.message,
        ) from err
    except Exception as err:
        logger.exception("Unexpected error during browser audit execution")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during browser auditing.",
        ) from err
