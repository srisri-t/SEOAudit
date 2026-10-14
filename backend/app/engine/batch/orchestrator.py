"""Batch audit orchestrator with bounded concurrency, failure isolation, and SQLite persistence."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from app.core.exceptions import (
    AuditFetchError,
    AuditSecurityError,
    ResponseTooLargeError,
)
from app.core.url_validator import validate_and_normalize_url
from app.db.repository import BatchAuditRepository
from app.engine.batch.analyzer import calculate_aggregate_summary
from app.engine.runner import run_single_url_audit
from app.engine.sitemap.discovery import discover_sitemaps
from app.models.batch import (
    BatchAuditConfig,
    BatchAuditCreateRequest,
    BatchAuditRunResponse,
    PageAuditResult,
    RunStatus,
)

logger = logging.getLogger(__name__)

# Active background tasks keyed by run_id for cancellation support
_ACTIVE_TASKS: dict[str, asyncio.Task[None]] = {}
_CANCELLATION_FLAGS: dict[str, bool] = {}


class BatchOrchestrator:
    """Coordinates batch audit execution, bounded concurrency, and persistence."""

    def __init__(self, repository: BatchAuditRepository) -> None:
        self.repo = repository

    async def prepare_urls(
        self,
        payload: BatchAuditCreateRequest,
    ) -> tuple[str, list[str]]:
        """Resolve, deduplicate, and bound candidate URLs from direct input and sitemaps."""
        raw_urls: list[str] = []

        # 1. Sitemap Discovery if requested
        target_origin = ""
        if payload.website_url or payload.sitemap_url:
            discovery_site = payload.website_url or payload.sitemap_url or ""
            target_origin = discovery_site
            try:
                sitemap_res = await discover_sitemaps(
                    website_url=discovery_site,
                    explicit_sitemap_url=payload.sitemap_url,
                    max_urls=payload.config.max_pages,
                )
                raw_urls.extend(sitemap_res.urls)
            except Exception as err:
                logger.warning("Sitemap discovery failed during batch preparation: %s", err)

        # 2. Add explicit URLs
        if payload.urls:
            raw_urls.extend(payload.urls)
            if not target_origin and payload.urls:
                target_origin = payload.urls[0]

        # 3. Deduplicate preserving order
        deduped: list[str] = []
        seen: set[str] = set()
        for u in raw_urls:
            cleaned = u.strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                deduped.append(cleaned)

        # 4. Limit to configured max_pages
        bounded = deduped[: payload.config.max_pages]
        return target_origin, bounded

    async def run_batch(
        self,
        run_id: str,
        urls: list[str],
        config: BatchAuditConfig,
        target_origin: str,
    ) -> None:
        """Asynchronous worker that executes the batch audit with bounded concurrency."""
        _CANCELLATION_FLAGS[run_id] = False
        start_ts = datetime.now(timezone.utc).isoformat()
        self.repo.update_run_status(
            run_id=run_id,
            status="running",
            started_at=start_ts,
        )

        semaphore = asyncio.Semaphore(config.concurrency)
        completed_count = 0
        failed_count = 0
        skipped_count = 0

        async def audit_worker(url: str) -> None:
            nonlocal completed_count, failed_count, skipped_count

            if _CANCELLATION_FLAGS.get(run_id, False):
                skipped_count += 1
                self.repo.insert_page_result(
                    PageAuditResult(
                        run_id=run_id,
                        url=url,
                        status="skipped",
                        error_message="Batch audit was cancelled.",
                    )
                )
                self.repo.update_run_progress(
                    run_id=run_id,
                    completed_pages=completed_count,
                    failed_pages=failed_count,
                    skipped_pages=skipped_count,
                )
                return

            async with semaphore:
                # Check cancellation again after waiting on semaphore
                if _CANCELLATION_FLAGS.get(run_id, False):
                    skipped_count += 1
                    self.repo.insert_page_result(
                        PageAuditResult(
                            run_id=run_id,
                            url=url,
                            status="skipped",
                            error_message="Batch audit was cancelled.",
                        )
                    )
                    self.repo.update_run_progress(
                        run_id=run_id,
                        completed_pages=completed_count,
                        failed_pages=failed_count,
                        skipped_pages=skipped_count,
                    )
                    return

                # Validate URL before making any network request
                try:
                    validate_and_normalize_url(url, resolve_dns=True)
                except AuditSecurityError as sec_err:
                    failed_count += 1
                    self.repo.insert_page_result(
                        PageAuditResult(
                            run_id=run_id,
                            url=url,
                            status="failed",
                            error_message=f"Security check failed: {sec_err.message}",
                        )
                    )
                    self.repo.update_run_progress(
                        run_id=run_id,
                        completed_pages=completed_count,
                        failed_pages=failed_count,
                        skipped_pages=skipped_count,
                    )
                    return
                except Exception as val_err:
                    failed_count += 1
                    self.repo.insert_page_result(
                        PageAuditResult(
                            run_id=run_id,
                            url=url,
                            status="failed",
                            error_message=f"Invalid URL: {val_err}",
                        )
                    )
                    self.repo.update_run_progress(
                        run_id=run_id,
                        completed_pages=completed_count,
                        failed_pages=failed_count,
                        skipped_pages=skipped_count,
                    )
                    return

                # Execute page audit with timeout and failure isolation
                try:
                    audit_res = await asyncio.wait_for(
                        run_single_url_audit(
                            target_url=url,
                            include_browser=config.include_browser,
                        ),
                        timeout=config.page_timeout_seconds,
                    )

                    completed_count += 1
                    page_result = PageAuditResult(
                        run_id=run_id,
                        url=audit_res.url,
                        final_url=audit_res.final_url,
                        status="success",
                        status_code=audit_res.status_code,
                        status_text=audit_res.status_text,
                        fetch_duration_ms=audit_res.fetch_duration_ms,
                        title=audit_res.title,
                        meta_description=audit_res.meta_description,
                        canonical_url=audit_res.canonical_url,
                        findings=audit_res.findings,
                        outgoing_links=audit_res.outgoing_links,
                        error_message=None,
                    )
                    self.repo.insert_page_result(page_result)

                except asyncio.TimeoutError:
                    failed_count += 1
                    self.repo.insert_page_result(
                        PageAuditResult(
                            run_id=run_id,
                            url=url,
                            status="failed",
                            error_message=f"Page audit timed out after {config.page_timeout_seconds}s.",
                        )
                    )
                except (AuditFetchError, ResponseTooLargeError) as known_err:
                    failed_count += 1
                    self.repo.insert_page_result(
                        PageAuditResult(
                            run_id=run_id,
                            url=url,
                            status="failed",
                            error_message=known_err.message,
                        )
                    )
                except Exception as exc:
                    failed_count += 1
                    logger.warning("Error auditing page %s: %s", url, exc)
                    self.repo.insert_page_result(
                        PageAuditResult(
                            run_id=run_id,
                            url=url,
                            status="failed",
                            error_message="Unexpected error during page audit.",
                        )
                    )

                self.repo.update_run_progress(
                    run_id=run_id,
                    completed_pages=completed_count,
                    failed_pages=failed_count,
                    skipped_pages=skipped_count,
                )

        # Launch all workers with bounded concurrency via Semaphore
        try:
            tasks = [asyncio.create_task(audit_worker(u)) for u in urls]
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            _ACTIVE_TASKS.pop(run_id, None)
            _CANCELLATION_FLAGS.pop(run_id, None)

        # Finalize run state and aggregate analysis
        end_ts = datetime.now(timezone.utc).isoformat()
        all_pages = self.repo.get_all_pages_for_run(run_id)
        agg_summary = calculate_aggregate_summary(
            pages=all_pages,
            total_discovered=len(urls),
            target_origin=target_origin,
        )

        # Determine terminal status
        current_run = self.repo.get_run(run_id)
        if current_run and current_run.status == "cancelled":
            final_status: RunStatus = "cancelled"
        elif completed_count > 0 and (failed_count > 0 or skipped_count > 0):
            final_status = "partial"
        elif completed_count == 0 and failed_count > 0:
            final_status = "failed"
        elif completed_count > 0 and failed_count == 0:
            final_status = "completed"
        else:
            final_status = "completed"

        self.repo.update_run_progress(
            run_id=run_id,
            completed_pages=completed_count,
            failed_pages=failed_count,
            skipped_pages=skipped_count,
            aggregate_summary=agg_summary,
            completed_at=end_ts,
            status=final_status,
        )

    def cancel_batch(self, run_id: str) -> bool:
        """Request cooperative cancellation of an active batch audit."""
        if run_id in _CANCELLATION_FLAGS:
            _CANCELLATION_FLAGS[run_id] = True
            self.repo.update_run_status(run_id=run_id, status="cancelled")
            return True
        return False
