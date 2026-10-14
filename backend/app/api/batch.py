"""API router for batch technical SEO auditing, run history, and report exports."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.db.connection import init_db
from app.db.repository import BatchAuditRepository
from app.engine.batch.analyzer import calculate_aggregate_summary
from app.engine.batch.exporter import (
    export_batch_csv,
    export_batch_json,
    export_batch_markdown,
)
from app.engine.batch.orchestrator import _ACTIVE_TASKS, BatchOrchestrator
from app.models.batch import (
    AggregateSummary,
    BatchAuditCreateRequest,
    BatchAuditListResponse,
    BatchAuditRunResponse,
    BatchPagesResponse,
    PageStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/batch-audits", tags=["batch-audits"])

# Singleton repository and orchestrator
_repository: BatchAuditRepository | None = None
_orchestrator: BatchOrchestrator | None = None


def get_repository() -> BatchAuditRepository:
    """Retrieve or initialize the batch audit repository."""
    global _repository
    if _repository is None:
        init_db()
        _repository = BatchAuditRepository()
    return _repository


def get_orchestrator() -> BatchOrchestrator:
    """Retrieve or initialize the batch orchestrator."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = BatchOrchestrator(get_repository())
    return _orchestrator


@router.post(
    "",
    response_model=BatchAuditRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create & Launch Batch Audit",
    description="Initializes and runs a bounded, local-first batch technical SEO audit over multiple URLs.",
)
async def create_batch_audit_endpoint(
    payload: BatchAuditCreateRequest,
) -> BatchAuditRunResponse:
    """Create and start a batch audit run."""
    orchestrator = get_orchestrator()
    repo = get_repository()

    try:
        target_origin, urls = await orchestrator.prepare_urls(payload)
    except Exception as err:
        logger.exception("Failed to prepare batch URLs")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to prepare URLs for batch auditing: {err}",
        ) from err

    if not urls:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid URLs found to audit. Please provide at least one reachable web URL.",
        )

    run_id = str(uuid.uuid4())
    mode = "browser" if payload.config.include_browser else "static"

    # Persist initial queued run state
    run_response = repo.create_run(
        run_id=run_id,
        target_origin=target_origin or (urls[0] if urls else "unknown"),
        status="queued",
        mode=mode,
        config=payload.config,
        total_pages=len(urls),
    )

    # Launch background orchestration task
    task = asyncio.create_task(
        orchestrator.run_batch(
            run_id=run_id,
            urls=urls,
            config=payload.config,
            target_origin=target_origin,
        )
    )
    _ACTIVE_TASKS[run_id] = task

    return run_response


@router.get(
    "",
    response_model=BatchAuditListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Batch Audit Runs",
    description="Returns recent audit runs sorted by creation time descending.",
)
def list_batch_audits_endpoint(
    limit: int = Query(default=20, ge=1, le=100, description="Page size"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
) -> BatchAuditListResponse:
    """List recent batch audit runs."""
    repo = get_repository()
    runs = repo.list_runs(limit=limit, offset=offset)
    total = repo.count_runs()
    return BatchAuditListResponse(total=total, runs=runs)


@router.get(
    "/{run_id}",
    response_model=BatchAuditRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Batch Audit Status & Summary",
    description="Retrieves the current execution progress, counts, and aggregate findings for a batch run.",
)
def get_batch_audit_endpoint(run_id: str) -> BatchAuditRunResponse:
    """Retrieve audit run by ID."""
    repo = get_repository()
    run = repo.get_run(run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit run '{run_id}' not found.",
        )
    return run


@router.get(
    "/{run_id}/pages",
    response_model=BatchPagesResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Paginated Page-Level Results",
    description="Retrieves detailed page audit results for a specific batch run.",
)
def get_batch_pages_endpoint(
    run_id: str,
    status_filter: PageStatus | None = Query(
        default=None, alias="status", description="Filter by page status"
    ),
    limit: int = Query(default=50, ge=1, le=200, description="Page limit"),
    offset: int = Query(default=0, ge=0, description="Page offset"),
) -> BatchPagesResponse:
    """Fetch paginated page-level audit results."""
    repo = get_repository()
    run = repo.get_run(run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit run '{run_id}' not found.",
        )

    pages = repo.get_pages_for_run(
        run_id=run_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    total = repo.count_pages_for_run(run_id=run_id, status=status_filter)

    return BatchPagesResponse(
        run_id=run_id,
        total=total,
        limit=limit,
        offset=offset,
        pages=pages,
    )


@router.get(
    "/{run_id}/summary",
    response_model=AggregateSummary,
    status_code=status.HTTP_200_OK,
    summary="Get Aggregate SEO Summary",
    description="Returns aggregate metrics, duplicate content analysis, and internal link health.",
)
def get_batch_summary_endpoint(run_id: str) -> AggregateSummary:
    """Retrieve aggregate summary for a batch run."""
    repo = get_repository()
    run = repo.get_run(run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit run '{run_id}' not found.",
        )

    if run.aggregate_summary:
        return run.aggregate_summary

    # If in-progress or summary not yet stored, calculate dynamically from recorded pages
    pages = repo.get_all_pages_for_run(run_id)
    return calculate_aggregate_summary(
        pages=pages,
        total_discovered=run.total_pages,
        target_origin=run.target_origin,
    )


@router.post(
    "/{run_id}/cancel",
    response_model=BatchAuditRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel Running Batch Audit",
    description="Gracefully cancels an active batch audit and marks remaining pages as skipped.",
)
def cancel_batch_audit_endpoint(run_id: str) -> BatchAuditRunResponse:
    """Request cooperative cancellation of a batch audit run."""
    orchestrator = get_orchestrator()
    repo = get_repository()
    run = repo.get_run(run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit run '{run_id}' not found.",
        )

    if run.status in ("completed", "failed", "cancelled"):
        return run

    cancelled = orchestrator.cancel_batch(run_id)
    if not cancelled:
        # If task not in memory (e.g. after restart), directly mark as cancelled
        repo.update_run_status(run_id=run_id, status="cancelled")

    updated_run = repo.get_run(run_id)
    return updated_run or run


@router.get(
    "/{run_id}/export",
    summary="Export Batch Audit Report",
    description="Exports the batch audit report in JSON, CSV (with formula injection mitigation), or Markdown format.",
)
def export_batch_audit_endpoint(
    run_id: str,
    export_format: Literal["json", "csv", "markdown"] = Query(
        default="json",
        alias="format",
        description="Desired export format: json, csv, or markdown",
    ),
) -> Response:
    """Export batch audit results in selected format."""
    repo = get_repository()
    run = repo.get_run(run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit run '{run_id}' not found.",
        )

    pages = repo.get_all_pages_for_run(run_id)
    # Ensure aggregate summary exists for export
    if not run.aggregate_summary and pages:
        run.aggregate_summary = calculate_aggregate_summary(
            pages=pages,
            total_discovered=run.total_pages,
            target_origin=run.target_origin,
        )

    if export_format == "json":
        json_content = export_batch_json(run, pages)
        return Response(
            content=json_content,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="seo_audit_{run_id}.json"',
            },
        )
    elif export_format == "csv":
        csv_content = export_batch_csv(run, pages)
        return Response(
            content=csv_content,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="seo_audit_{run_id}.csv"',
            },
        )
    elif export_format == "markdown":
        md_content = export_batch_markdown(run, pages)
        return Response(
            content=md_content,
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="seo_audit_{run_id}.md"',
            },
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported export format '{export_format}'. Supported formats are: json, csv, markdown.",
        )
