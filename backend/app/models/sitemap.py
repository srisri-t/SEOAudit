"""Pydantic models for Sitemap discovery and parsing."""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, ConfigDict, Field


class SitemapStatus(str, Enum):
    """Sitemap discovery status indicator."""

    FOUND = "Sitemap found"
    NOT_FOUND = "Sitemap not found"
    INACCESSIBLE = "Sitemap inaccessible"
    INVALID = "Invalid sitemap"
    BLOCKED = "Discovery blocked by security validation"


class SitemapDiscoverRequest(BaseModel):
    """Request payload for discovering and parsing website sitemaps."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    website_url: str = Field(
        ...,
        description="The target website URL (e.g. https://example.com/)",
        examples=["https://example.com/"],
    )
    sitemap_url: str | None = Field(
        default=None,
        description="Optional explicit URL of the sitemap or sitemap index to process",
        examples=["https://example.com/sitemap.xml"],
    )
    max_urls: int = Field(
        default=1000,
        ge=1,
        le=10000,
        description="Maximum number of URLs to discover and return (1 to 10000). Unlimited requests are prohibited.",
    )


class SitemapDiscoverResponse(BaseModel):
    """Response payload containing discovered sitemaps and extracted URLs."""

    model_config = ConfigDict(extra="forbid")

    website_url: str = Field(..., description="The audited target website URL")
    sitemap_status: str = Field(
        ...,
        description="Discovery status: 'Sitemap found', 'Sitemap not found', 'Sitemap inaccessible', 'Invalid sitemap', or 'Discovery blocked by security validation'",
    )
    discovered_sitemaps: list[str] = Field(
        default_factory=list,
        description="List of sitemap URLs discovered and processed",
    )
    discovered_url_count: int = Field(
        default=0,
        description="Total number of unique, valid URLs discovered",
    )
    urls: list[str] = Field(
        default_factory=list,
        description="List of discovered unique, valid, normalized page URLs",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal warnings encountered during sitemap parsing",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Sanitized error messages explaining failures or inaccessibility",
    )
    processing_duration_ms: float = Field(
        default=0.0,
        description="Total elapsed processing duration in milliseconds",
    )
