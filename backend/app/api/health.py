from datetime import datetime, timezone
from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api", tags=["health"])


class HealthResponse(BaseModel):
    """Documented response schema for the health check endpoint."""

    status: str = Field(
        default="ok",
        description="Current health status of the backend API service",
        examples=["ok"],
    )
    app: str = Field(
        default="Universal SEO Platform",
        description="Application name",
        examples=["Universal SEO Platform"],
    )
    version: str = Field(
        default="0.1.0",
        description="Platform release version for Milestone 1",
        examples=["0.1.0"],
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Current UTC timestamp in ISO 8601 format",
    )


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health Check",
    description="Returns the operational health status and application metadata. Used for local connectivity verification.",
)
def get_health() -> HealthResponse:
    """Return application health status."""
    return HealthResponse()
