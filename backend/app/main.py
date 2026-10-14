"""Universal SEO Automation & Maintenance Platform - Backend Application.

Security & Network Binding:
    During local development, this server MUST bind exclusively to loopback
    (127.0.0.1), NEVER 0.0.0.0, to prevent exposing the local service across
    untrusted networks.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.audit import router as audit_router
from app.api.health import router as health_router

app = FastAPI(
    title="Universal SEO Automation & Maintenance Platform API",
    description=(
        "Local API service providing technical SEO audits, findings tracking, "
        "and AI-ready report generation."
    ),
    version="0.1.0",
)

# Allow local frontend development origins
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(audit_router)


@app.get("/", tags=["root"], summary="Root service info")
def root():
    """Root info endpoint pointing to documentation and health status."""
    return {
        "message": "Universal SEO Automation Platform API is running.",
        "docs_url": "/docs",
        "health_url": "/api/health",
    }
