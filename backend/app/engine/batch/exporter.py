"""Report export engine supporting JSON, CSV (with formula injection mitigation), and Markdown."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from app.models.batch import BatchAuditRunResponse, PageAuditResult

DANGEROUS_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_csv_cell(value: Any) -> str:
    """Sanitize cell value against CSV formula injection (DDE/spreadsheet execution)."""
    if value is None:
        return ""
    text = str(value)
    if text and text.startswith(DANGEROUS_FORMULA_PREFIXES):
        return f"'{text}"
    return text


def export_batch_json(
    run: BatchAuditRunResponse,
    pages: list[PageAuditResult],
) -> str:
    """Export complete batch audit run and page-level results as formatted JSON."""
    data = {
        "run": run.model_dump(),
        "pages": [p.model_dump() for p in pages],
    }
    return json.dumps(data, indent=2)


def export_batch_csv(
    run: BatchAuditRunResponse,
    pages: list[PageAuditResult],
) -> str:
    """Export page-level audit results to CSV with formula injection mitigation."""
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    headers = [
        "run_id",
        "url",
        "final_url",
        "status",
        "status_code",
        "status_text",
        "fetch_duration_ms",
        "title",
        "meta_description",
        "canonical_url",
        "pass_count",
        "warning_count",
        "issue_count",
        "error_count",
        "error_message",
        "audited_at",
    ]
    writer.writerow(headers)

    for page in pages:
        pass_count = sum(1 for f in page.findings if f.status == "pass")
        warning_count = sum(1 for f in page.findings if f.status == "warning")
        issue_count = sum(1 for f in page.findings if f.status == "issue")
        error_count = sum(1 for f in page.findings if f.status == "error")

        row = [
            sanitize_csv_cell(page.run_id),
            sanitize_csv_cell(page.url),
            sanitize_csv_cell(page.final_url),
            sanitize_csv_cell(page.status),
            sanitize_csv_cell(page.status_code),
            sanitize_csv_cell(page.status_text),
            sanitize_csv_cell(page.fetch_duration_ms),
            sanitize_csv_cell(page.title),
            sanitize_csv_cell(page.meta_description),
            sanitize_csv_cell(page.canonical_url),
            sanitize_csv_cell(pass_count),
            sanitize_csv_cell(warning_count),
            sanitize_csv_cell(issue_count),
            sanitize_csv_cell(error_count),
            sanitize_csv_cell(page.error_message),
            sanitize_csv_cell(page.audited_at),
        ]
        writer.writerow(row)

    return output.getvalue()


def escape_markdown_cell(value: Any) -> str:
    """Escape pipe and newline characters within markdown table cells."""
    if value is None:
        return "—"
    text = str(value)
    return text.replace("|", r"\|").replace("\n", " ").replace("\r", "")


def export_batch_markdown(
    run: BatchAuditRunResponse,
    pages: list[PageAuditResult],
) -> str:
    """Generate a readable, deterministic executive markdown report."""
    summary = run.aggregate_summary
    lines: list[str] = []

    lines.append("# Universal SEO Automation Platform — Batch Audit Report\n")
    lines.append(f"**Run ID:** `{run.id}`  ")
    lines.append(f"**Target Origin:** `{run.target_origin}`  ")
    lines.append(f"**Audit Mode:** `{run.mode.upper()}`  ")
    lines.append(f"**Status:** `{run.status.upper()}`  ")
    lines.append(f"**Created At:** {run.created_at}  ")
    if run.completed_at:
        lines.append(f"**Completed At:** {run.completed_at}  ")
    lines.append("")

    # Executive Summary Table
    lines.append("## Executive Summary\n")
    lines.append("| Metric | Count |")
    lines.append("| :--- | :--- |")
    lines.append(f"| Total Pages Discovered | {run.total_pages} |")
    lines.append(f"| Completed Pages | {run.completed_pages} |")
    lines.append(f"| Failed Pages | {run.failed_pages} |")
    lines.append(f"| Skipped Pages | {run.skipped_pages} |")
    if summary:
        lines.append(f"| Missing Titles | {summary.missing_titles_count} |")
        lines.append(f"| Missing Descriptions | {summary.missing_descriptions_count} |")
        lines.append(f"| Duplicate Title Groups | {len(summary.duplicate_titles)} |")
        lines.append(f"| Duplicate Description Groups | {len(summary.duplicate_descriptions)} |")
        lines.append(f"| Confirmed Broken Internal Links | {len(summary.internal_link_analysis.confirmed_broken_links)} |")
        lines.append(f"| External Links Encountered | {summary.internal_link_analysis.external_links_count} |")
    lines.append("")

    # Severity Breakdown
    if summary and summary.findings_by_severity:
        lines.append("## Rule Findings by Severity\n")
        lines.append("| Severity | Total Count |")
        lines.append("| :--- | :--- |")
        for sev in ("pass", "warning", "issue", "error"):
            cnt = summary.findings_by_severity.get(sev, 0)
            lines.append(f"| **{sev.upper()}** | {cnt} |")
        lines.append("")

    # Status Code Breakdown
    if summary and summary.status_code_distribution:
        lines.append("## HTTP Status Distribution\n")
        lines.append("| Status Code | Pages |")
        lines.append("| :--- | :--- |")
        for code, count in sorted(summary.status_code_distribution.items()):
            lines.append(f"| {escape_markdown_cell(code)} | {count} |")
        lines.append("")

    # Duplicate Titles
    if summary and summary.duplicate_titles:
        lines.append("## Duplicate Page Titles\n")
        for group in summary.duplicate_titles:
            lines.append(f"### Title: \"{group.title}\" ({group.count} pages)")
            for u in group.urls:
                lines.append(f"- {u}")
            lines.append("")

    # Duplicate Descriptions
    if summary and summary.duplicate_descriptions:
        lines.append("## Duplicate Meta Descriptions\n")
        for group in summary.duplicate_descriptions:
            lines.append(f"### Description: \"{group.description}\" ({group.count} pages)")
            for u in group.urls:
                lines.append(f"- {u}")
            lines.append("")

    # Broken Internal Links
    if summary and summary.internal_link_analysis.confirmed_broken_links:
        lines.append("## Confirmed Broken Internal Links\n")
        lines.append("| Source URL | Broken Target URL | Target Status |")
        lines.append("| :--- | :--- | :--- |")
        for bl in summary.internal_link_analysis.confirmed_broken_links:
            status_text = str(bl.status_code) if bl.status_code is not None else "Failed"
            lines.append(f"| {escape_markdown_cell(bl.source_url)} | {escape_markdown_cell(bl.target_url)} | {escape_markdown_cell(status_text)} |")
        lines.append("")

    # Page-by-Page Summary
    lines.append("## Page Results Summary\n")
    lines.append("| URL | Status | Code | Duration | Title | Issues |")
    lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
    for page in pages:
        clean_title = (page.title[:40] + "...") if page.title and len(page.title) > 40 else (page.title or "—")
        issues = sum(1 for f in page.findings if f.status in ("issue", "error"))
        duration = f"{page.fetch_duration_ms}ms" if page.fetch_duration_ms is not None else "—"
        code = str(page.status_code) if page.status_code is not None else "ERR"
        lines.append(
            f"| {escape_markdown_cell(page.url)} "
            f"| {escape_markdown_cell(page.status.upper())} "
            f"| {escape_markdown_cell(code)} "
            f"| {escape_markdown_cell(duration)} "
            f"| {escape_markdown_cell(clean_title)} "
            f"| {issues} |"
        )
    lines.append("")

    return "\n".join(lines)
