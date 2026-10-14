import { useState, useEffect, useCallback, type FormEvent } from 'react';
import {
  fetchHealth,
  auditUrl,
  type HealthStatus,
  type AuditResponse,
  type Finding,
  type FindingStatus,
} from './services/api';

type ConnectionState = 'loading' | 'connected' | 'error';
type FilterOption = 'all' | FindingStatus;

export default function App() {
  // Backend health state
  const [connectionState, setConnectionState] = useState<ConnectionState>('loading');
  const [healthData, setHealthData] = useState<HealthStatus | null>(null);

  // Audit form state
  const [targetUrl, setTargetUrl] = useState<string>('https://www.holyspace.live');
  const [isAuditing, setIsAuditing] = useState<boolean>(false);
  const [auditError, setAuditError] = useState<string | null>(null);
  const [auditResult, setAuditResult] = useState<AuditResponse | null>(null);
  const [activeFilter, setActiveFilter] = useState<FilterOption>('all');

  const checkBackendHealth = useCallback(async () => {
    setConnectionState('loading');
    try {
      const data = await fetchHealth();
      setHealthData(data);
      setConnectionState('connected');
    } catch {
      setConnectionState('error');
    }
  }, []);

  useEffect(() => {
    checkBackendHealth();
  }, [checkBackendHealth]);

  const handleRunAudit = async (e?: FormEvent) => {
    if (e) e.preventDefault();

    const trimmed = targetUrl.trim();
    if (!trimmed) {
      setAuditError('Please enter a target web page URL.');
      return;
    }

    if (!trimmed.startsWith('http://') && !trimmed.startsWith('https://')) {
      setAuditError('URL must begin with http:// or https://');
      return;
    }

    setIsAuditing(true);
    setAuditError(null);

    try {
      const result = await auditUrl(trimmed);
      setAuditResult(result);
    } catch (err) {
      setAuditError(err instanceof Error ? err.message : 'An error occurred during audit.');
    } finally {
      setIsAuditing(false);
    }
  };

  const filteredFindings = auditResult
    ? auditResult.findings.filter((f) => {
        if (activeFilter === 'all') return true;
        return f.status === activeFilter;
      })
    : [];

  const getStatusBadge = (status: FindingStatus) => {
    switch (status) {
      case 'pass':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-emerald-950/80 text-emerald-400 border border-emerald-800">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            PASS
          </span>
        );
      case 'warning':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-amber-950/80 text-amber-400 border border-amber-800">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
            WARNING
          </span>
        );
      case 'issue':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-orange-950/80 text-orange-400 border border-orange-800">
            <span className="w-1.5 h-1.5 rounded-full bg-orange-400" />
            ISSUE
          </span>
        );
      case 'error':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-rose-950/80 text-rose-400 border border-rose-800">
            <span className="w-1.5 h-1.5 rounded-full bg-rose-400" />
            ERROR
          </span>
        );
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-indigo-500 selection:text-white">
      {/* Top Header */}
      <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur-md sticky top-0 z-20 px-6 py-3.5">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center font-bold text-white shadow-md shadow-indigo-500/20">
              SEO
            </div>
            <div>
              <h1 className="text-base font-semibold text-white tracking-tight">
                Universal SEO Platform
              </h1>
              <p className="text-[11px] text-slate-400">
                Single-URL Technical Audit Engine
              </p>
            </div>
          </div>

          {/* Connection Status Indicator */}
          <div className="flex items-center gap-3">
            <div
              className={`flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium border ${
                connectionState === 'connected'
                  ? 'bg-emerald-950/60 text-emerald-400 border-emerald-800/80'
                  : connectionState === 'loading'
                  ? 'bg-amber-950/60 text-amber-400 border-amber-800/80'
                  : 'bg-rose-950/60 text-rose-400 border-rose-800/80'
              }`}
            >
              <span
                className={`w-2 h-2 rounded-full ${
                  connectionState === 'connected'
                    ? 'bg-emerald-400 animate-pulse'
                    : connectionState === 'loading'
                    ? 'bg-amber-400 animate-ping'
                    : 'bg-rose-400'
                }`}
              />
              <span>
                {connectionState === 'connected' && `Backend Online (v${healthData?.version || '0.1.0'})`}
                {connectionState === 'loading' && 'Checking API...'}
                {connectionState === 'error' && 'Backend Offline'}
              </span>
            </div>

            <button
              onClick={checkBackendHealth}
              disabled={connectionState === 'loading'}
              className="px-2.5 py-1 text-xs font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 disabled:opacity-50 rounded-lg transition-colors border border-slate-700"
              title="Refresh backend status"
            >
              Refresh
            </button>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="flex-1 max-w-6xl w-full mx-auto p-6 md:p-8 space-y-6">
        {/* Audit Form Section */}
        <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-6 shadow-xl space-y-4">
          <div>
            <h2 className="text-xl font-bold text-white tracking-tight">
              Audit Web Page
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              Enter any public HTTP or HTTPS web address to inspect HTTP status, redirects, title, meta description, canonical link, and robots indexing directives.
            </p>
          </div>

          <form onSubmit={handleRunAudit} className="space-y-3">
            <div className="flex flex-col sm:flex-row gap-3">
              <div className="relative flex-1">
                <input
                  type="url"
                  value={targetUrl}
                  onChange={(e) => {
                    setTargetUrl(e.target.value);
                    if (auditError) setAuditError(null);
                  }}
                  placeholder="https://www.example.com"
                  disabled={isAuditing}
                  className="w-full px-4 py-2.5 rounded-xl bg-slate-950 border border-slate-700 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 text-sm text-white placeholder-slate-500 outline-none transition-all disabled:opacity-60 font-mono"
                  required
                />
              </div>

              <button
                type="submit"
                disabled={isAuditing || !targetUrl.trim()}
                className="px-6 py-2.5 rounded-xl font-semibold text-sm text-white bg-indigo-600 hover:bg-indigo-500 active:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg shadow-indigo-600/20 flex items-center justify-center gap-2"
              >
                {isAuditing ? (
                  <>
                    <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    <span>Auditing...</span>
                  </>
                ) : (
                  <span>Run Audit</span>
                )}
              </button>
            </div>

            {/* Quick Target URL Selection */}
            <div className="flex items-center gap-2 text-xs text-slate-400 flex-wrap">
              <span>Quick Target:</span>
              <button
                type="button"
                onClick={() => setTargetUrl('https://www.holyspace.live')}
                className="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-indigo-300 font-mono text-[11px] border border-slate-700 transition-colors"
              >
                https://www.holyspace.live
              </button>
              <button
                type="button"
                onClick={() => setTargetUrl('https://example.com')}
                className="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-indigo-300 font-mono text-[11px] border border-slate-700 transition-colors"
              >
                https://example.com
              </button>
            </div>
          </form>

          {/* Error Banner with Retry */}
          {auditError && (
            <div className="p-4 rounded-xl bg-rose-950/50 border border-rose-800/80 flex items-start justify-between gap-3 animate-fadeIn">
              <div className="space-y-1">
                <h4 className="text-xs font-semibold text-rose-300 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-rose-400" />
                  Audit Execution Blocked or Failed
                </h4>
                <p className="text-xs text-rose-200/90 leading-relaxed">
                  {auditError}
                </p>
              </div>
              <button
                type="button"
                onClick={() => handleRunAudit()}
                disabled={isAuditing}
                className="shrink-0 px-3 py-1.5 text-xs font-medium text-rose-200 bg-rose-900/60 hover:bg-rose-800/80 rounded-lg border border-rose-700 transition-colors"
              >
                Retry
              </button>
            </div>
          )}
        </section>

        {/* Audit Results View */}
        {auditResult ? (
          <div className="space-y-6">
            {/* High-Level Metrics Summary */}
            <section className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div className="p-4 rounded-xl border border-emerald-900/50 bg-emerald-950/20 flex flex-col justify-between">
                <span className="text-xs font-medium text-emerald-400 uppercase tracking-wider">Passed</span>
                <span className="text-3xl font-bold text-white mt-2">{auditResult.summary.passed}</span>
                <span className="text-[11px] text-slate-400 mt-1">Checks passing standard</span>
              </div>

              <div className="p-4 rounded-xl border border-amber-900/50 bg-amber-950/20 flex flex-col justify-between">
                <span className="text-xs font-medium text-amber-400 uppercase tracking-wider">Warnings</span>
                <span className="text-3xl font-bold text-white mt-2">{auditResult.summary.warnings}</span>
                <span className="text-[11px] text-slate-400 mt-1">Advisory recommendations</span>
              </div>

              <div className="p-4 rounded-xl border border-orange-900/50 bg-orange-950/20 flex flex-col justify-between">
                <span className="text-xs font-medium text-orange-400 uppercase tracking-wider">Issues</span>
                <span className="text-3xl font-bold text-white mt-2">{auditResult.summary.issues}</span>
                <span className="text-[11px] text-slate-400 mt-1">SEO issues found</span>
              </div>

              <div className="p-4 rounded-xl border border-rose-900/50 bg-rose-950/20 flex flex-col justify-between">
                <span className="text-xs font-medium text-rose-400 uppercase tracking-wider">Errors</span>
                <span className="text-3xl font-bold text-white mt-2">{auditResult.summary.errors}</span>
                <span className="text-[11px] text-slate-400 mt-1">Fetch or server failures</span>
              </div>
            </section>

            {/* Target Overview Card */}
            <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 space-y-3">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-800 gap-2">
                <div className="space-y-0.5">
                  <div className="text-xs text-slate-400">Audited Endpoint:</div>
                  <div className="font-mono text-sm text-indigo-300 break-all font-semibold">
                    {auditResult.url}
                  </div>
                </div>
                <div className="flex items-center gap-3 text-xs">
                  <span className="px-2.5 py-1 rounded-md bg-slate-800 text-slate-300 font-mono">
                    HTTP {auditResult.status_code} {auditResult.status_text}
                  </span>
                  <span className="px-2.5 py-1 rounded-md bg-slate-800 text-slate-300 font-mono">
                    {auditResult.fetch_duration_ms} ms
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs pt-1">
                <div>
                  <span className="text-slate-500">Final Resolved URL:</span>
                  <div className="font-mono text-slate-300 break-all">{auditResult.final_url}</div>
                </div>
                <div>
                  <span className="text-slate-500">MIME Content Type:</span>
                  <div className="font-mono text-slate-300">{auditResult.content_type || 'None'}</div>
                </div>
                {auditResult.redirect_count > 0 && (
                  <div className="md:col-span-2 p-2.5 rounded bg-slate-950 border border-slate-800 space-y-1">
                    <span className="text-amber-400 font-medium">
                      Redirect Chain ({auditResult.redirect_count} hops followed):
                    </span>
                    <ul className="space-y-1 font-mono text-[11px] text-slate-400">
                      {auditResult.redirect_chain.map((h, i) => (
                        <li key={i}>
                          Hop {i + 1}: {h.url} (HTTP {h.status_code}) &rarr; {h.location}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </section>

            {/* Findings Filter Bar & List */}
            <section className="space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <h3 className="text-base font-bold text-white">
                  Technical SEO Rule Findings ({filteredFindings.length} of {auditResult.findings.length})
                </h3>

                {/* Filter Tabs */}
                <div className="flex items-center gap-1.5 p-1 rounded-xl bg-slate-900 border border-slate-800 text-xs">
                  <button
                    onClick={() => setActiveFilter('all')}
                    className={`px-3 py-1 rounded-lg transition-colors ${
                      activeFilter === 'all'
                        ? 'bg-slate-800 text-white font-medium shadow-sm'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    All ({auditResult.findings.length})
                  </button>
                  <button
                    onClick={() => setActiveFilter('pass')}
                    className={`px-3 py-1 rounded-lg transition-colors ${
                      activeFilter === 'pass'
                        ? 'bg-emerald-950 text-emerald-300 font-medium shadow-sm border border-emerald-800/60'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    Pass ({auditResult.summary.passed})
                  </button>
                  <button
                    onClick={() => setActiveFilter('warning')}
                    className={`px-3 py-1 rounded-lg transition-colors ${
                      activeFilter === 'warning'
                        ? 'bg-amber-950 text-amber-300 font-medium shadow-sm border border-amber-800/60'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    Warnings ({auditResult.summary.warnings})
                  </button>
                  <button
                    onClick={() => setActiveFilter('issue')}
                    className={`px-3 py-1 rounded-lg transition-colors ${
                      activeFilter === 'issue'
                        ? 'bg-orange-950 text-orange-300 font-medium shadow-sm border border-orange-800/60'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    Issues ({auditResult.summary.issues})
                  </button>
                </div>
              </div>

              {/* Findings Cards */}
              <div className="space-y-3">
                {filteredFindings.map((finding: Finding) => (
                  <article
                    key={finding.rule_id}
                    className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 space-y-2.5 transition-colors hover:border-slate-700"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2.5">
                        {getStatusBadge(finding.status)}
                        <h4 className="text-sm font-semibold text-white">
                          {finding.title}
                        </h4>
                      </div>
                      <span className="text-[11px] font-mono text-slate-500">
                        {finding.rule_id}
                      </span>
                    </div>

                    <p className="text-xs text-slate-300 leading-relaxed">
                      {finding.explanation}
                    </p>

                    {finding.recommendation && (
                      <div className="p-2.5 rounded-lg bg-indigo-950/30 border border-indigo-900/40 text-xs text-indigo-300 space-y-1">
                        <span className="font-semibold text-indigo-200">Recommended Action:</span>
                        <p className="text-[11px] leading-relaxed text-indigo-200/90">{finding.recommendation}</p>
                      </div>
                    )}

                    {finding.evidence && (
                      <div className="p-2 rounded bg-slate-950 border border-slate-800 font-mono text-[11px] text-slate-400 break-all">
                        <span className="text-slate-500 select-none">Evidence: </span>
                        {finding.evidence}
                      </div>
                    )}
                  </article>
                ))}
              </div>
            </section>
          </div>
        ) : (
          /* Empty State Before Audit */
          <section className="rounded-2xl border border-slate-800/80 bg-slate-900/40 p-8 text-center space-y-4">
            <div className="w-12 h-12 rounded-xl bg-slate-800/80 border border-slate-700/60 flex items-center justify-center mx-auto text-indigo-400 text-xl font-bold">
              🔍
            </div>
            <div className="max-w-md mx-auto space-y-1.5">
              <h3 className="text-base font-semibold text-white">
                No Active Audit Results Yet
              </h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Enter a target URL above (for example, <code className="text-indigo-300">https://www.holyspace.live</code>) and click &quot;Run Audit&quot; to inspect technical SEO health in real time.
              </p>
            </div>
            <button
              type="button"
              onClick={() => handleRunAudit()}
              disabled={isAuditing}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold text-indigo-300 bg-indigo-950/60 hover:bg-indigo-900/60 border border-indigo-800/60 transition-colors"
            >
              Audit Holy Space Now
            </button>
          </section>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800 bg-slate-900/40 px-6 py-4 mt-auto">
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between text-xs text-slate-500 gap-2">
          <span>Universal SEO Automation &amp; Maintenance Platform • Milestone 2 Engine</span>
          <div className="flex items-center gap-4">
            <a
              href="http://127.0.0.1:8000/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="text-slate-400 hover:text-indigo-400 transition-colors"
            >
              OpenAPI Swagger Docs
            </a>
            <span className="text-slate-700">•</span>
            <a
              href="http://127.0.0.1:8000/api/health"
              target="_blank"
              rel="noopener noreferrer"
              className="text-slate-400 hover:text-indigo-400 transition-colors"
            >
              Direct Health Check
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
