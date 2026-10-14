"""API router for Sitemap discovery and parsing."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from app.core.exceptions import AuditSecurityError
from app.core.url_validator import validate_and_normalize_url
from app.engine.sitemap.discovery import discover_sitemaps
from app.models.sitemap import SitemapDiscoverRequest, SitemapDiscoverResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sitemaps", tags=["sitemaps"])


@router.post(
    "/discover",
    response_model=SitemapDiscoverResponse,
    status_code=status.HTTP_200_OK,
    summary="Discover and Parse Website Sitemaps",
    description=(
        "Discovers XML sitemaps for a website using robots.txt inspection, standard /sitemap.xml fallback, "
        "or an explicit sitemap URL. Safely parses XML sitemaps and indexes while enforcing strict SSRF "
        "and recursion boundaries."
    ),
)
async def discover_sitemap_endpoint(payload: SitemapDiscoverRequest) -> SitemapDiscoverResponse:
    """Endpoint handler for sitemap discovery."""
    website_url = payload.website_url.strip() if payload.website_url else ""
    if not website_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The 'website_url' parameter cannot be empty.",
        )

    # Initial scheme and SSRF validation for input URLs
    try:
        validate_and_normalize_url(website_url, resolve_dns=True)
    except AuditSecurityError as err:
        logger.warning("Website URL security check failed: %s", err.message)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Security check failed: {err.message}",
        ) from err
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid website URL: {err}",
        ) from err

    explicit_sitemap = payload.sitemap_url.strip() if payload.sitemap_url else None
    if explicit_sitemap:
        try:
            validate_and_normalize_url(explicit_sitemap, resolve_dns=True)
        except AuditSecurityError as err:
            logger.warning("Explicit sitemap URL security check failed: %s", err.message)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Security check failed: {err.message}",
            ) from err
        except Exception as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid explicit sitemap URL: {err}",
            ) from err

    try:
        response = await discover_sitemaps(
            website_url=website_url,
            explicit_sitemap_url=explicit_sitemap,
            max_urls=payload.max_urls,
        )
        return response
    except Exception as err:
        logger.exception("Unexpected error during sitemap discovery")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during sitemap discovery.",
        ) from err
