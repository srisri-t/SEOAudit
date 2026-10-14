"""Repository layer for SQLite persistence of audit runs and pages."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.db.connection import get_db
from app.models.audit import Finding
from app.models.batch import (
    AggregateSummary,
    BatchAuditConfig,
    BatchAuditRunResponse,
    PageAuditResult,
    PageStatus,
    RunStatus,
)


class BatchAuditRepository:
    """Encapsulates all database operations for audit runs and page results."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = db_path

    def create_run(
        self,
        run_id: str,
        target_origin: str,
        status: RunStatus,
        mode: str,
        config: BatchAuditConfig,
        total_pages: int,
        created_at: str | None = None,
    ) -> BatchAuditRunResponse:
        """Create a new batch audit run record."""
        ts = created_at or datetime.now(timezone.utc).isoformat()
        config_json = config.model_dump_json()

        with get_db(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO audit_runs (
                    id, target_origin, status, mode, config_json,
                    total_pages, completed_pages, failed_pages, skipped_pages,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0, ?)
                """,
                (run_id, target_origin, status, mode, config_json, total_pages, ts),
            )

        return BatchAuditRunResponse(
            id=run_id,
            target_origin=target_origin,
            status=status,
            mode=mode,  # type: ignore[arg-type]
            config=config,
            total_pages=total_pages,
            completed_pages=0,
            failed_pages=0,
            skipped_pages=0,
            created_at=ts,
            started_at=None,
            completed_at=None,
            error_message=None,
            aggregate_summary=None,
        )

    def update_run_status(
        self,
        run_id: str,
        status: RunStatus,
        started_at: str | None = None,
        completed_at: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Update run status, timestamps, and error message."""
        updates: list[str] = ["status = ?"]
        params: list[Any] = [status]

        if started_at is not None:
            updates.append("started_at = ?")
            params.append(started_at)
        if completed_at is not None:
            updates.append("completed_at = ?")
            params.append(completed_at)
        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)

        params.append(run_id)
        query = f"UPDATE audit_runs SET {', '.join(updates)} WHERE id = ?"

        with get_db(self.db_path) as conn:
            conn.execute(query, params)

    def update_run_progress(
        self,
        run_id: str,
        completed_pages: int,
        failed_pages: int,
        skipped_pages: int,
        aggregate_summary: AggregateSummary | None = None,
        completed_at: str | None = None,
        status: RunStatus | None = None,
    ) -> None:
        """Update execution counts, aggregate summary JSON, and optional completion state."""
        updates = [
            "completed_pages = ?",
            "failed_pages = ?",
            "skipped_pages = ?",
        ]
        params: list[Any] = [completed_pages, failed_pages, skipped_pages]

        if aggregate_summary is not None:
            updates.append("aggregate_summary_json = ?")
            params.append(aggregate_summary.model_dump_json())

        if completed_at is not None:
            updates.append("completed_at = ?")
            params.append(completed_at)

        if status is not None:
            updates.append("status = ?")
            params.append(status)

        params.append(run_id)
        query = f"UPDATE audit_runs SET {', '.join(updates)} WHERE id = ?"

        with get_db(self.db_path) as conn:
            conn.execute(query, params)

    def get_run(self, run_id: str) -> BatchAuditRunResponse | None:
        """Fetch a single audit run by ID."""
        with get_db(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT id, target_origin, status, mode, config_json,
                       total_pages, completed_pages, failed_pages, skipped_pages,
                       aggregate_summary_json, error_message,
                       created_at, started_at, completed_at
                FROM audit_runs
                WHERE id = ?
                """,
                (run_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_run(row)

    def list_runs(self, limit: int = 50, offset: int = 0) -> list[BatchAuditRunResponse]:
        """Fetch recent audit runs with pagination."""
        with get_db(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT id, target_origin, status, mode, config_json,
                       total_pages, completed_pages, failed_pages, skipped_pages,
                       aggregate_summary_json, error_message,
                       created_at, started_at, completed_at
                FROM audit_runs
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            )
            return [self._row_to_run(r) for r in cursor.fetchall()]

    def count_runs(self) -> int:
        """Count total recorded audit runs."""
        with get_db(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM audit_runs")
            return int(cursor.fetchone()[0])

    def insert_page_result(self, page: PageAuditResult) -> int:
        """Record an individual page audit result."""
        findings_json = json.dumps([f.model_dump() for f in page.findings])
        outgoing_links_json = json.dumps(page.outgoing_links)

        with get_db(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO audit_pages (
                    run_id, url, final_url, status, status_code, status_text,
                    fetch_duration_ms, title, meta_description, canonical_url,
                    findings_json, outgoing_links_json, error_message, audited_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    page.run_id,
                    page.url,
                    page.final_url,
                    page.status,
                    page.status_code,
                    page.status_text,
                    page.fetch_duration_ms,
                    page.title,
                    page.meta_description,
                    page.canonical_url,
                    findings_json,
                    outgoing_links_json,
                    page.error_message,
                    page.audited_at,
                ),
            )
            return int(cursor.lastrowid or 0)

    def get_pages_for_run(
        self,
        run_id: str,
        status: PageStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PageAuditResult]:
        """Fetch paginated page-level results for a run, with optional status filter."""
        with get_db(self.db_path) as conn:
            if status:
                cursor = conn.execute(
                    """
                    SELECT id, run_id, url, final_url, status, status_code, status_text,
                           fetch_duration_ms, title, meta_description, canonical_url,
                           findings_json, outgoing_links_json, error_message, audited_at
                    FROM audit_pages
                    WHERE run_id = ? AND status = ?
                    ORDER BY id ASC
                    LIMIT ? OFFSET ?
                    """,
                    (run_id, status, limit, offset),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT id, run_id, url, final_url, status, status_code, status_text,
                           fetch_duration_ms, title, meta_description, canonical_url,
                           findings_json, outgoing_links_json, error_message, audited_at
                    FROM audit_pages
                    WHERE run_id = ?
                    ORDER BY id ASC
                    LIMIT ? OFFSET ?
                    """,
                    (run_id, limit, offset),
                )
            return [self._row_to_page(r) for r in cursor.fetchall()]

    def count_pages_for_run(self, run_id: str, status: PageStatus | None = None) -> int:
        """Count total pages recorded for a run."""
        with get_db(self.db_path) as conn:
            if status:
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM audit_pages WHERE run_id = ? AND status = ?",
                    (run_id, status),
                )
            else:
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM audit_pages WHERE run_id = ?",
                    (run_id,),
                )
            return int(cursor.fetchone()[0])

    def get_all_pages_for_run(self, run_id: str) -> list[PageAuditResult]:
        """Retrieve all page results for an audit run (used for analysis and export)."""
        with get_db(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT id, run_id, url, final_url, status, status_code, status_text,
                       fetch_duration_ms, title, meta_description, canonical_url,
                       findings_json, outgoing_links_json, error_message, audited_at
                FROM audit_pages
                WHERE run_id = ?
                ORDER BY id ASC
                """,
                (run_id,),
            )
            return [self._row_to_page(r) for r in cursor.fetchall()]

    def _row_to_run(self, row: Any) -> BatchAuditRunResponse:
        """Convert a database row into a BatchAuditRunResponse model."""
        config_data = json.loads(row["config_json"])
        summary_data = (
            json.loads(row["aggregate_summary_json"])
            if row["aggregate_summary_json"]
            else None
        )

        return BatchAuditRunResponse(
            id=row["id"],
            target_origin=row["target_origin"],
            status=row["status"],
            mode=row["mode"],
            config=BatchAuditConfig(**config_data),
            total_pages=row["total_pages"],
            completed_pages=row["completed_pages"],
            failed_pages=row["failed_pages"],
            skipped_pages=row["skipped_pages"],
            aggregate_summary=AggregateSummary(**summary_data) if summary_data else None,
            error_message=row["error_message"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
        )

    def _row_to_page(self, row: Any) -> PageAuditResult:
        """Convert a database row into a PageAuditResult model."""
        findings_data = (
            json.loads(row["findings_json"]) if row["findings_json"] else []
        )
        outgoing_links_data = (
            json.loads(row["outgoing_links_json"]) if row["outgoing_links_json"] else []
        )

        return PageAuditResult(
            id=row["id"],
            run_id=row["run_id"],
            url=row["url"],
            final_url=row["final_url"],
            status=row["status"],
            status_code=row["status_code"],
            status_text=row["status_text"],
            fetch_duration_ms=row["fetch_duration_ms"],
            title=row["title"],
            meta_description=row["meta_description"],
            canonical_url=row["canonical_url"],
            findings=[Finding(**f) for f in findings_data],
            outgoing_links=outgoing_links_data,
            error_message=row["error_message"],
            audited_at=row["audited_at"],
        )
