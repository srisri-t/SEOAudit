"""Tests for SQLite persistence, schema initialization, and repository operations."""

from __future__ import annotations

import tempfile
from pathlib import Path

from app.db.connection import create_connection, get_db, init_db
from app.db.repository import BatchAuditRepository
from app.models.audit import Finding
from app.models.batch import (
    AggregateSummary,
    BatchAuditConfig,
    PageAuditResult,
)


def test_init_db_idempotency():
    """Verify schema initialization can run multiple times without error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_seo.db"
        # First initialization
        init_db(db_path)
        assert db_path.exists()

        # Second initialization (idempotent)
        init_db(db_path)

        with get_db(db_path) as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row["name"] for row in cursor.fetchall()}
            assert "audit_runs" in tables
            assert "audit_pages" in tables


def test_sqlite_pragmas():
    """Verify that WAL mode and foreign key constraints are applied."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_pragmas.db"
        init_db(db_path)

        conn = create_connection(db_path)
        try:
            fk_cursor = conn.execute("PRAGMA foreign_keys;")
            assert fk_cursor.fetchone()[0] == 1

            journal_cursor = conn.execute("PRAGMA journal_mode;")
            assert journal_cursor.fetchone()[0].lower() == "wal"
        finally:
            conn.close()


def test_repository_run_lifecycle_and_restart():
    """Verify runs and pages persist across repository and connection restarts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_lifecycle.db"
        init_db(db_path)

        # 1. Create run using first repo instance
        repo1 = BatchAuditRepository(db_path)
        config = BatchAuditConfig(max_pages=20, concurrency=2, include_browser=False)
        created = repo1.create_run(
            run_id="run-101",
            target_origin="https://example.com",
            status="queued",
            mode="static",
            config=config,
            total_pages=5,
        )
        assert created.id == "run-101"
        assert created.status == "queued"
        assert created.total_pages == 5

        # Update status to running
        repo1.update_run_status(run_id="run-101", status="running", started_at="2026-10-14T10:00:00Z")

        # Insert page results
        page1 = PageAuditResult(
            run_id="run-101",
            url="https://example.com/p1",
            status="success",
            status_code=200,
            status_text="OK",
            fetch_duration_ms=120,
            title="Page 1",
            meta_description="Desc 1",
            findings=[
                Finding(
                    rule_id="page-title",
                    title="Page Title Presence",
                    status="pass",
                    explanation="Title present",
                )
            ],
            outgoing_links=["https://example.com/p2"],
        )
        repo1.insert_page_result(page1)

        # 2. Simulate server restart: create new repo instance pointing to same file
        repo2 = BatchAuditRepository(db_path)
        run = repo2.get_run("run-101")
        assert run is not None
        assert run.id == "run-101"
        assert run.status == "running"
        assert run.started_at == "2026-10-14T10:00:00Z"
        assert run.config.max_pages == 20

        # Verify pages retrieved from restarted repo
        pages = repo2.get_pages_for_run("run-101")
        assert len(pages) == 1
        assert pages[0].url == "https://example.com/p1"
        assert pages[0].title == "Page 1"
        assert len(pages[0].findings) == 1
        assert pages[0].findings[0].rule_id == "page-title"
        assert pages[0].outgoing_links == ["https://example.com/p2"]

        # Complete run with aggregate summary
        summary = AggregateSummary(
            total_pages_discovered=5,
            total_pages_audited=1,
            successful_pages=1,
            failed_pages=0,
            skipped_pages=0,
        )
        repo2.update_run_progress(
            run_id="run-101",
            completed_pages=1,
            failed_pages=0,
            skipped_pages=0,
            aggregate_summary=summary,
            completed_at="2026-10-14T10:01:00Z",
            status="completed",
        )

        completed_run = repo2.get_run("run-101")
        assert completed_run is not None
        assert completed_run.status == "completed"
        assert completed_run.completed_pages == 1
        assert completed_run.completed_at == "2026-10-14T10:01:00Z"
        assert completed_run.aggregate_summary is not None
        assert completed_run.aggregate_summary.total_pages_audited == 1


def test_repository_pagination_and_filtering():
    """Verify page filtering by status and limit/offset pagination."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_pagination.db"
        init_db(db_path)
        repo = BatchAuditRepository(db_path)

        repo.create_run(
            run_id="run-page-test",
            target_origin="https://example.com",
            status="running",
            mode="static",
            config=BatchAuditConfig(),
            total_pages=4,
        )

        for i in range(1, 4):
            repo.insert_page_result(
                PageAuditResult(
                    run_id="run-page-test",
                    url=f"https://example.com/success/{i}",
                    status="success",
                    status_code=200,
                )
            )

        repo.insert_page_result(
            PageAuditResult(
                run_id="run-page-test",
                url="https://example.com/failed/1",
                status="failed",
                error_message="Connection timed out",
            )
        )

        # Count total
        assert repo.count_pages_for_run("run-page-test") == 4
        assert repo.count_pages_for_run("run-page-test", status="success") == 3
        assert repo.count_pages_for_run("run-page-test", status="failed") == 1

        # Pagination
        first_two = repo.get_pages_for_run("run-page-test", limit=2, offset=0)
        assert len(first_two) == 2
        next_two = repo.get_pages_for_run("run-page-test", limit=2, offset=2)
        assert len(next_two) == 2
        assert first_two[0].url != next_two[0].url


def test_reconcile_stale_runs():
    """Verify that stale queued and running tasks are transitioned on startup."""
    from app.db.connection import reconcile_stale_runs

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_stale.db"
        init_db(db_path)
        repo = BatchAuditRepository(db_path)

        # 1. Stale run with 0 completed pages
        repo.create_run(
            run_id="stale-queued",
            target_origin="https://example.com",
            status="queued",
            mode="static",
            config=BatchAuditConfig(),
            total_pages=5,
        )

        # 2. Stale run with 2 completed pages
        repo.create_run(
            run_id="stale-running",
            target_origin="https://example.com",
            status="running",
            mode="static",
            config=BatchAuditConfig(),
            total_pages=5,
        )
        repo.update_run_progress(
            run_id="stale-running",
            completed_pages=2,
            failed_pages=0,
            skipped_pages=0,
        )

        # Run reconciliation
        reconcile_stale_runs(db_path)

        run1 = repo.get_run("stale-queued")
        assert run1.status == "failed"
        assert "Process terminated" in (run1.error_message or "")

        run2 = repo.get_run("stale-running")
        assert run2.status == "partial"
        assert "Process terminated" in (run2.error_message or "")
