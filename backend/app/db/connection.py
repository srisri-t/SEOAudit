"""SQLite connection manager and schema initialization."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

DEFAULT_DB_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "data" / "seo_audit.db"
)


def get_db_path() -> Path:
    """Retrieve the configured database path."""
    env_path = os.environ.get("SEO_AUDIT_DB_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_DB_PATH


def create_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Create a new SQLite connection with recommended performance and concurrency pragmas."""
    target_path = Path(db_path) if db_path else get_db_path()

    # Ensure parent directory exists for file-based DBs
    if str(target_path) != ":memory:" and not str(target_path).startswith("file:"):
        target_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(
        str(target_path),
        timeout=10.0,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row

    # Execute pragmas for safe concurrent execution and data integrity
    if str(target_path) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")

    return conn


@contextmanager
def get_db(db_path: Path | str | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for SQLite connections with transaction management."""
    conn = create_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path | str | None = None) -> None:
    """Initialize database tables and indexes idempotently."""
    with get_db(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS audit_runs (
                id TEXT PRIMARY KEY,
                target_origin TEXT NOT NULL,
                status TEXT NOT NULL,
                mode TEXT NOT NULL,
                config_json TEXT NOT NULL,
                total_pages INTEGER NOT NULL DEFAULT 0,
                completed_pages INTEGER NOT NULL DEFAULT 0,
                failed_pages INTEGER NOT NULL DEFAULT 0,
                skipped_pages INTEGER NOT NULL DEFAULT 0,
                aggregate_summary_json TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_audit_runs_created_at
                ON audit_runs(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_audit_runs_status
                ON audit_runs(status);

            CREATE TABLE IF NOT EXISTS audit_pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE,
                url TEXT NOT NULL,
                final_url TEXT,
                status TEXT NOT NULL,
                status_code INTEGER,
                status_text TEXT,
                fetch_duration_ms INTEGER,
                title TEXT,
                meta_description TEXT,
                canonical_url TEXT,
                findings_json TEXT,
                outgoing_links_json TEXT,
                error_message TEXT,
                audited_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_audit_pages_run_id
                ON audit_pages(run_id);
            CREATE INDEX IF NOT EXISTS idx_audit_pages_url
                ON audit_pages(url);
            CREATE INDEX IF NOT EXISTS idx_audit_pages_status
                ON audit_pages(status);
            """
        )


def reconcile_stale_runs(db_path: Path | str | None = None) -> None:
    """Reconcile stale in-flight runs left from a previous process termination."""
    with get_db(db_path) as conn:
        conn.execute(
            """
            UPDATE audit_runs
            SET status = CASE
                    WHEN completed_pages > 0 THEN 'partial'
                    ELSE 'failed'
                END,
                error_message = 'Process terminated before batch completion.'
            WHERE status IN ('running', 'queued')
            """
        )
