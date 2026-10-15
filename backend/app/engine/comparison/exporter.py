"""Report exporters for audit run comparisons (JSON and Markdown)."""

from __future__ import annotations

import json
from app.models.comparison import AuditComparisonResponse


def export_comparison_json(comparison: AuditComparisonResponse) -> str:
    """Export comparison result as pretty-printed JSON."""
    return json.dumps(comparison.model_dump(mode="json"), indent=2)


def export_comparison_markdown(comparison: AuditComparisonResponse) -> str:
    """Export comparison result as clean, structured, sanitized Markdown."""
    lines: list[str] = []

    def sanitize(text: str | None) -> str:
        if not text:
            return "—"
        return str(text).replace("|", "\\|").replace("\n", " ").strip()

    # 1. Header
    lines.append("# Universal SEO Automation Platform — Audit Run Comparison")
    lines.append("")
    lines.append(f"**Website Scope:** `{comparison.summary.website_scope}`  ")
    lines.append(f"**Baseline Run:** `{comparison.summary.baseline_run_id}` ({comparison.summary.baseline_created_at})  ")
    lines.append(f"**Comparison Run:** `{comparison.summary.comparison_run_id}` ({comparison.summary.comparison_created_at})  ")
    lines.append(f"**Completeness:** `{comparison.summary.comparison_completeness.upper()}`")
    lines.append("")

    # 2. Executive Assessment
    lines.append("## Executive Assessment")
    lines.append("")
    verdict_badge = comparison.assessment.verdict.upper()
    lines.append(f"> **Verdict: {verdict_badge}** — *{comparison.assessment.headline}*")
    lines.append(">")
    lines.append(f"> {comparison.assessment.explanation}")
    lines.append("")

    # 3. Summary Metrics
    lines.append("## Summary Metrics")
    lines.append("")
    lines.append("| Metric | Count |")
    lines.append("| :--- | :--- |")
    lines.append(f"| **New Issues Detected** | {comparison.summary.new_issues_count} |")
    lines.append(f"| **Resolved Issues** | {comparison.summary.resolved_issues_count} |")
    lines.append(f"| **Persistent Issues** | {comparison.summary.persistent_issues_count} |")
    lines.append(f"| **Incomparable Findings** | {comparison.summary.incomparable_findings_count} |")
    lines.append(f"| **Common Audited Pages** | {comparison.summary.common_pages_count} |")
    lines.append(f"| **Newly Discovered Pages** | {comparison.summary.new_pages_count} |")
    lines.append(f"| **Pages Not in Newer Audit** | {comparison.summary.missing_pages_count} |")
    lines.append(f"| **Metadata Fields Modified** | {comparison.summary.metadata_changes_count} |")
    lines.append(f"| **Page Retrieval Failures** | {comparison.summary.page_retrieval_failures} |")
    lines.append("")

    # 4. Coverage Warnings
    if comparison.summary.coverage_warnings:
        lines.append("## Coverage & Reliability Warnings")
        lines.append("")
        for w in comparison.summary.coverage_warnings:
            lines.append(f"- ⚠️ {w}")
        lines.append("")

    # 5. Issue Changes
    lines.append("## Issue Changes")
    lines.append("")
    if comparison.issue_changes:
        lines.append("| URL | Rule | Change Type | Status | Explanation |")
        lines.append("| :--- | :--- | :--- | :--- | :--- |")
        for item in comparison.issue_changes:
            u = sanitize(item.page_url)
            r = sanitize(item.rule_id)
            c = sanitize(item.change_type.upper())
            s = sanitize(item.status.upper())
            e = sanitize(item.explanation)
            lines.append(f"| `{u}` | `{r}` | **{c}** | {s} | {e} |")
    else:
        lines.append("*No issue changes detected between the two audit runs.*")
    lines.append("")

    # 6. SEO Metadata Changes
    lines.append("## SEO Metadata Changes")
    lines.append("")
    if comparison.metadata_changes:
        lines.append("| URL | Field | Baseline Value | Comparison Value | Change Type |")
        lines.append("| :--- | :--- | :--- | :--- | :--- |")
        for m in comparison.metadata_changes:
            u = sanitize(m.page_url)
            f = sanitize(m.field_name)
            b = sanitize(m.baseline_value)
            c = sanitize(m.comparison_value)
            t = sanitize(m.change_type.upper())
            lines.append(f"| `{u}` | `{f}` | {b} | {c} | **{t}** |")
    else:
        lines.append("*No metadata changes detected across common pages.*")
    lines.append("")

    # 7. Page Coverage
    lines.append("## Page Coverage Details")
    lines.append("")
    if comparison.page_coverage:
        lines.append("| URL | Coverage Status | Baseline Page Status | Comparison Page Status |")
        lines.append("| :--- | :--- | :--- | :--- |")
        for p in comparison.page_coverage:
            u = sanitize(p.url)
            s = sanitize(p.coverage_status)
            b = sanitize(p.baseline_page_status)
            c = sanitize(p.comparison_page_status)
            lines.append(f"| `{u}` | **{s}** | {b} | {c} |")
    else:
        lines.append("*No page coverage data available.*")
    lines.append("")

    return "\n".join(lines)
