"""Tests for batch orchestrator concurrency, failure isolation, and cancellation."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.core.exceptions import AuditFetchError
from app.db.connection import init_db
from app.db.repository import BatchAuditRepository
from app.engine.batch.orchestrator import BatchOrchestrator
from app.models.audit import AuditResponse, AuditSummary, Finding
from app.models.batch import BatchAuditConfig, BatchAuditCreateRequest


@pytest.fixture
def test_repo_and_orchestrator():
    """Provides a temporary repository and orchestrator instance."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_orch.db"
        init_db(db_path)
        repo = BatchAuditRepository(db_path)
        orchestrator = BatchOrchestrator(repo)
        yield repo, orchestrator


@pytest.mark.anyio
async def test_prepare_urls_deduplication_and_limit(test_repo_and_orchestrator):
    """Verify URL deduplication preserves order and respects max_pages."""
    repo, orchestrator = test_repo_and_orchestrator

    req = BatchAuditCreateRequest(
        urls=[
            "https://example.com/p1",
            "https://example.com/p2",
            "https://example.com/p1",  # duplicate
            "https://example.com/p3",
            "https://example.com/p4",
            "https://example.com/p5",
        ],
        config=BatchAuditConfig(max_pages=3),
    )

    origin, urls = await orchestrator.prepare_urls(req)
    assert origin == "https://example.com/p1"
    # Deduplicated and capped to 3
    assert urls == [
        "https://example.com/p1",
        "https://example.com/p2",
        "https://example.com/p3",
    ]


@pytest.mark.anyio
async def test_failure_isolation_and_partial_status(test_repo_and_orchestrator):
    """Verify that a failing URL does not halt processing of other URLs."""
    repo, orchestrator = test_repo_and_orchestrator

    # Mock single url audit: p1 succeeds, p2 raises AuditFetchError, p3 succeeds
    async def mock_run_audit(target_url: str, **kwargs) -> AuditResponse:
        if "p2" in target_url:
            raise AuditFetchError("Server returned 502 Bad Gateway")
        return AuditResponse(
            url=target_url,
            final_url=target_url,
            status_code=200,
            status_text="OK",
            content_type="text/html",
            fetch_duration_ms=50,
            redirect_count=0,
            title="Success Page",
            summary=AuditSummary(
                total_checks=1, passed=1, warnings=0, issues=0, errors=0
            ),
            findings=[],
        )

    urls = [
        "https://example.com/p1",
        "https://example.com/p2",
        "https://example.com/p3",
    ]
    repo.create_run(
        run_id="run-iso",
        target_origin="https://example.com",
        status="queued",
        mode="static",
        config=BatchAuditConfig(max_pages=5, concurrency=2),
        total_pages=3,
    )

    with patch("app.engine.batch.orchestrator.run_single_url_audit", side_effect=mock_run_audit):
        with patch("app.engine.batch.orchestrator.validate_and_normalize_url", return_value=""):
            await orchestrator.run_batch(
                run_id="run-iso",
                urls=urls,
                config=BatchAuditConfig(max_pages=5, concurrency=2),
                target_origin="https://example.com",
            )

    run = repo.get_run("run-iso")
    assert run is not None
    assert run.status == "partial"
    assert run.completed_pages == 2
    assert run.failed_pages == 1
    assert run.skipped_pages == 0

    pages = repo.get_all_pages_for_run("run-iso")
    status_map = {p.url: p.status for p in pages}
    assert status_map["https://example.com/p1"] == "success"
    assert status_map["https://example.com/p2"] == "failed"
    assert status_map["https://example.com/p3"] == "success"


@pytest.mark.anyio
async def test_bounded_concurrency_limit(test_repo_and_orchestrator):
    """Verify maximum concurrent requests do not exceed the configured limit."""
    repo, orchestrator = test_repo_and_orchestrator

    active_count = 0
    max_observed_concurrency = 0

    async def mock_run_audit(target_url: str, **kwargs) -> AuditResponse:
        nonlocal active_count, max_observed_concurrency
        active_count += 1
        if active_count > max_observed_concurrency:
            max_observed_concurrency = active_count
        await asyncio.sleep(0.05)
        active_count -= 1
        return AuditResponse(
            url=target_url,
            final_url=target_url,
            status_code=200,
            status_text="OK",
            content_type="text/html",
            fetch_duration_ms=50,
            redirect_count=0,
            summary=AuditSummary(total_checks=0, passed=0, warnings=0, issues=0, errors=0),
            findings=[],
        )

    urls = [f"https://example.com/{i}" for i in range(8)]
    repo.create_run(
        run_id="run-conc",
        target_origin="https://example.com",
        status="queued",
        mode="static",
        config=BatchAuditConfig(concurrency=2),
        total_pages=len(urls),
    )

    with patch("app.engine.batch.orchestrator.run_single_url_audit", side_effect=mock_run_audit):
        with patch("app.engine.batch.orchestrator.validate_and_normalize_url", return_value=""):
            await orchestrator.run_batch(
                run_id="run-conc",
                urls=urls,
                config=BatchAuditConfig(concurrency=2),
                target_origin="https://example.com",
            )

    assert max_observed_concurrency <= 2


@pytest.mark.anyio
async def test_cooperative_cancellation(test_repo_and_orchestrator):
    """Verify cancellation marks remaining pages as skipped and sets run status to cancelled."""
    repo, orchestrator = test_repo_and_orchestrator

    async def slow_audit(target_url: str, **kwargs):
        await asyncio.sleep(0.2)
        return AuditResponse(
            url=target_url,
            final_url=target_url,
            status_code=200,
            status_text="OK",
            content_type="text/html",
            fetch_duration_ms=200,
            redirect_count=0,
            summary=AuditSummary(total_checks=0, passed=0, warnings=0, issues=0, errors=0),
            findings=[],
        )

    urls = [f"https://example.com/p{i}" for i in range(5)]
    repo.create_run(
        run_id="run-cancel",
        target_origin="https://example.com",
        status="queued",
        mode="static",
        config=BatchAuditConfig(concurrency=1),
        total_pages=5,
    )

    with patch("app.engine.batch.orchestrator.run_single_url_audit", side_effect=slow_audit):
        with patch("app.engine.batch.orchestrator.validate_and_normalize_url", return_value=""):
            batch_task = asyncio.create_task(
                orchestrator.run_batch(
                    run_id="run-cancel",
                    urls=urls,
                    config=BatchAuditConfig(concurrency=1),
                    target_origin="https://example.com",
                )
            )
            # Allow first page to begin, then cancel
            await asyncio.sleep(0.05)
            orchestrator.cancel_batch("run-cancel")
            await batch_task

    run = repo.get_run("run-cancel")
    assert run is not None
    assert run.status == "cancelled"
    assert run.skipped_pages > 0


@pytest.mark.anyio
async def test_ssrf_protection_in_batch(test_repo_and_orchestrator):
    """Verify private/internal URLs in batch fail security validation without crashing the batch."""
    repo, orchestrator = test_repo_and_orchestrator

    urls = [
        "http://127.0.0.1:8000/admin",
        "http://169.254.169.254/latest/meta-data",
    ]
    repo.create_run(
        run_id="run-ssrf",
        target_origin="http://127.0.0.1:8000",
        status="queued",
        mode="static",
        config=BatchAuditConfig(concurrency=2),
        total_pages=2,
    )

    await orchestrator.run_batch(
        run_id="run-ssrf",
        urls=urls,
        config=BatchAuditConfig(concurrency=2),
        target_origin="http://127.0.0.1:8000",
    )

    run = repo.get_run("run-ssrf")
    assert run is not None
    assert run.status == "failed"
    assert run.failed_pages == 2
    assert run.completed_pages == 0

    pages = repo.get_all_pages_for_run("run-ssrf")
    for p in pages:
        assert p.status == "failed"
        assert "Security check failed" in (p.error_message or "")
