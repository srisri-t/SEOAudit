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

export async function auditUrl(targetUrl: string): Promise<AuditResponse> {
  const url = `${API_BASE}/api/audits/url`;
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify({ url: targetUrl }),
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
