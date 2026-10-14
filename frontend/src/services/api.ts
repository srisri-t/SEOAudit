/**
 * API client service for communicating with the backend API.
 * Uses configurable base URL with fallback to relative paths (supported by Vite proxy in dev).
 */

export interface HealthStatus {
  status: string;
  app: string;
  version: string;
  timestamp: string;
}

export type FindingStatus = 'pass' | 'warning' | 'issue' | 'error';

export interface Finding {
  rule_id: string;
  title: string;
  status: FindingStatus;
  explanation: string;
  recommendation: string | null;
  evidence: string | null;
}

export interface AuditSummary {
  total_checks: number;
  passed: number;
  warnings: number;
  issues: number;
  errors: number;
}

export interface RedirectHop {
  url: string;
  status_code: number;
  location: string;
}

export interface ConsoleMessage {
  level: string;
  text: string;
  location: string | null;
}

export interface PageException {
  message: string;
  stack: string | null;
}

export interface BrowserAuditResult {
  final_rendered_url: string;
  browser_status_code: number | null;
  rendered_title: string | null;
  rendered_meta_description: string | null;
  rendered_canonical_url: string | null;
  rendered_meta_robots: string[];
  console_errors: ConsoleMessage[];
  page_exceptions: PageException[];
  failed_subresources: string[];
  render_duration_ms: number;
  hydration_mismatch: boolean;
  mismatch_details: string[];
}

export interface AuditResponse {
  url: string;
  final_url: string;
  status_code: number;
  status_text: string;
  content_type: string;
  fetch_duration_ms: number;
  redirect_count: number;
  redirect_chain: RedirectHop[];
  title: string | null;
  meta_description: string | null;
  canonical_url: string | null;
  meta_robots: string[];
  x_robots_tag: string[];
  summary: AuditSummary;
  findings: Finding[];
  browser_audit?: BrowserAuditResult | null;
  timestamp: string;
}

const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

export async function fetchHealth(): Promise<HealthStatus> {
  const url = `${API_BASE}/api/health`;
  const response = await fetch(url, {
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Backend responded with HTTP ${response.status}: ${response.statusText}`);
  }

  return response.json();
}

export async function auditUrl(targetUrl: string, includeBrowser: boolean = false): Promise<AuditResponse> {
  const url = `${API_BASE}/api/audits/url`;
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify({ url: targetUrl, include_browser: includeBrowser }),
  });

  if (!response.ok) {
    let errorDetail = `HTTP ${response.status}: ${response.statusText}`;
    try {
      const errorJson = await response.json();
      if (errorJson && errorJson.detail) {
        errorDetail = errorJson.detail;
      }
    } catch {
      // Fallback to HTTP status text if response is not JSON
    }
    throw new Error(errorDetail);
  }

  return response.json();
}

export interface SitemapDiscoverResponse {
  website_url: string;
  sitemap_status: string;
  discovered_sitemaps: string[];
  discovered_url_count: number;
  urls: string[];
  warnings: string[];
  errors: string[];
  processing_duration_ms: number;
}

export async function discoverSitemaps(
  websiteUrl: string,
  sitemapUrl?: string | null,
  maxUrls: number = 1000,
): Promise<SitemapDiscoverResponse> {
  const url = `${API_BASE}/api/sitemaps/discover`;
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify({
      website_url: websiteUrl,
      sitemap_url: sitemapUrl && sitemapUrl.trim() ? sitemapUrl.trim() : null,
      max_urls: maxUrls,
    }),
  });

  if (!response.ok) {
    let errorDetail = `HTTP ${response.status}: ${response.statusText}`;
    try {
      const errorJson = await response.json();
      if (errorJson && errorJson.detail) {
        errorDetail = errorJson.detail;
      }
    } catch {
      // Fallback to HTTP status text if response is not JSON
    }
    throw new Error(errorDetail);
  }

  return response.json();
}

// ==========================================
// Milestone 5: Batch Auditing & Export Engine
// ==========================================

export type RunStatus = 'queued' | 'running' | 'completed' | 'partial' | 'failed' | 'cancelled';
export type PageStatus = 'success' | 'failed' | 'skipped';

export interface BatchAuditConfig {
  max_pages: number;
  concurrency: number;
  page_timeout_seconds: number;
  include_browser: boolean;
}

export interface DuplicateTitleGroup {
  title: string;
  count: number;
  urls: string[];
}

export interface DuplicateDescriptionGroup {
  description: string;
  count: number;
  urls: string[];
}

export interface BrokenLinkFinding {
  source_url: string;
  target_url: string;
  status_code: number | null;
  reason: 'confirmed_broken' | 'unverified' | 'error';
}

export interface InternalLinkSummary {
  total_internal_links_checked: number;
  confirmed_broken_links: BrokenLinkFinding[];
  unverified_internal_links: BrokenLinkFinding[];
  external_links_count: number;
}

export interface AggregateSummary {
  total_pages_discovered: number;
  total_pages_audited: number;
  successful_pages: number;
  failed_pages: number;
  skipped_pages: number;
  status_code_distribution: Record<string, number>;
  findings_by_severity: Record<string, number>;
  duplicate_titles: DuplicateTitleGroup[];
  duplicate_descriptions: DuplicateDescriptionGroup[];
  missing_titles_count: number;
  missing_descriptions_count: number;
  internal_link_analysis: InternalLinkSummary;
}

export interface PageAuditResult {
  id?: number | null;
  run_id: string;
  url: string;
  final_url?: string | null;
  status: PageStatus;
  status_code?: number | null;
  status_text?: string | null;
  fetch_duration_ms?: number | null;
  title?: string | null;
  meta_description?: string | null;
  canonical_url?: string | null;
  findings: Finding[];
  outgoing_links: string[];
  error_message?: string | null;
  audited_at: string;
}

export interface BatchAuditRunResponse {
  id: string;
  target_origin: string;
  status: RunStatus;
  mode: 'static' | 'browser';
  config: BatchAuditConfig;
  total_pages: number;
  completed_pages: number;
  failed_pages: number;
  skipped_pages: number;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  error_message?: string | null;
  aggregate_summary?: AggregateSummary | null;
}

export interface BatchPagesResponse {
  run_id: string;
  total: number;
  limit: number;
  offset: number;
  pages: PageAuditResult[];
}

export interface BatchAuditListResponse {
  total: number;
  runs: BatchAuditRunResponse[];
}

export async function createBatchAudit(payload: {
  urls?: string[];
  website_url?: string | null;
  sitemap_url?: string | null;
  config?: Partial<BatchAuditConfig>;
}): Promise<BatchAuditRunResponse> {
  const url = `${API_BASE}/api/batch-audits`;
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    let errorDetail = `HTTP ${response.status}: ${response.statusText}`;
    try {
      const errorJson = await response.json();
      if (errorJson && errorJson.detail) {
        errorDetail = errorJson.detail;
      }
    } catch {
      // Fallback
    }
    throw new Error(errorDetail);
  }

  return response.json();
}

export async function getBatchAudit(runId: string): Promise<BatchAuditRunResponse> {
  const url = `${API_BASE}/api/batch-audits/${runId}`;
  const response = await fetch(url, {
    headers: { Accept: 'application/json' },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch audit run: HTTP ${response.status}`);
  }

  return response.json();
}

export async function getBatchPages(
  runId: string,
  statusFilter?: PageStatus,
  limit: number = 50,
  offset: number = 0,
): Promise<BatchPagesResponse> {
  const params = new URLSearchParams({
    limit: limit.toString(),
    offset: offset.toString(),
  });
  if (statusFilter) {
    params.set('status', statusFilter);
  }

  const url = `${API_BASE}/api/batch-audits/${runId}/pages?${params.toString()}`;
  const response = await fetch(url, {
    headers: { Accept: 'application/json' },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch audit pages: HTTP ${response.status}`);
  }

  return response.json();
}

export async function cancelBatchAudit(runId: string): Promise<BatchAuditRunResponse> {
  const url = `${API_BASE}/api/batch-audits/${runId}/cancel`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { Accept: 'application/json' },
  });

  if (!response.ok) {
    throw new Error(`Failed to cancel audit: HTTP ${response.status}`);
  }

  return response.json();
}

export async function listBatchAudits(
  limit: number = 20,
  offset: number = 0,
): Promise<BatchAuditListResponse> {
  const url = `${API_BASE}/api/batch-audits?limit=${limit}&offset=${offset}`;
  const response = await fetch(url, {
    headers: { Accept: 'application/json' },
  });

  if (!response.ok) {
    throw new Error(`Failed to list audits: HTTP ${response.status}`);
  }

  return response.json();
}

export function getBatchExportUrl(runId: string, format: 'json' | 'csv' | 'markdown'): string {
  return `${API_BASE}/api/batch-audits/${runId}/export?format=${format}`;
}

export async function downloadBatchExport(
  runId: string,
  format: 'json' | 'csv' | 'markdown',
): Promise<void> {
  const url = getBatchExportUrl(runId, format);
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to export report: HTTP ${response.status}`);
  }

  const blob = await response.blob();
  const ext = format === 'markdown' ? 'md' : format;
  const filename = `seo_audit_${runId}.${ext}`;

  const downloadUrl = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = downloadUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  window.URL.revokeObjectURL(downloadUrl);
  document.body.removeChild(a);
}
