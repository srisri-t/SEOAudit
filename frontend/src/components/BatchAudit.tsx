import { useState, useEffect, useCallback, type FormEvent } from 'react';
import {
  createBatchAudit,
  getBatchAudit,
  getBatchPages,
  cancelBatchAudit,
  listBatchAudits,
  downloadBatchExport,
  type BatchAuditRunResponse,
  type PageAuditResult,
  type RunStatus,
  type PageStatus,
} from '../services/api';

interface BatchAuditProps {
  initialUrls?: string[];
  initialWebsiteUrl?: string;
}

export default function BatchAudit({ initialUrls, initialWebsiteUrl }: BatchAuditProps) {
  // Input form state
  const [urlsText, setUrlsText] = useState<string>(
    initialUrls && initialUrls.length > 0
      ? initialUrls.join('\n')
      : 'https://www.holyspace.live\nhttps://www.holyspace.live/about\nhttps://www.holyspace.live/terms',
  );
  const [websiteUrl, setWebsiteUrl] = useState<string>(initialWebsiteUrl || '');
  const [sitemapUrl, setSitemapUrl] = useState<string>('');
  const [maxPages, setMaxPages] = useState<number>(25);
  const [concurrency, setConcurrency] = useState<number>(3);
  const [includeBrowser, setIncludeBrowser] = useState<boolean>(false);

  // Active run state
  const [isStarting, setIsStarting] = useState<boolean>(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [activeRun, setActiveRun] = useState<BatchAuditRunResponse | null>(null);
  const [pages, setPages] = useState<PageAuditResult[]>([]);
  const [pageStatusFilter, setPageStatusFilter] = useState<'all' | PageStatus>('all');
  const [selectedPage, setSelectedPage] = useState<PageAuditResult | null>(null);
  const [activeDetailTab, setActiveDetailTab] = useState<'pages' | 'duplicates' | 'links'>('pages');

  // History state
  const [historyRuns, setHistoryRuns] = useState<BatchAuditRunResponse[]>([]);
  const [isExporting, setIsExporting] = useState<boolean>(false);

  // Update text when props change
  useEffect(() => {
    if (initialUrls && initialUrls.length > 0) {
      setUrlsText(initialUrls.join('\n'));
    }
    if (initialWebsiteUrl) {
      setWebsiteUrl(initialWebsiteUrl);
    }
  }, [initialUrls, initialWebsiteUrl]);

  // Load audit history
  const loadHistory = useCallback(async () => {
    try {
      const res = await listBatchAudits(15, 0);
      setHistoryRuns(res.runs);
    } catch {
      // Best effort load history
    }
  }, []);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  // Polling for active run progress
  useEffect(() => {
    if (!activeRun) return;
    const isTerminal =
      activeRun.status === 'completed' ||
      activeRun.status === 'partial' ||
      activeRun.status === 'failed' ||
      activeRun.status === 'cancelled';

    if (isTerminal) return;

    const interval = setInterval(async () => {
      try {
        const updated = await getBatchAudit(activeRun.id);
        setActiveRun(updated);

        // Also fetch latest pages
        const pagesRes = await getBatchPages(activeRun.id, undefined, 100, 0);
        setPages(pagesRes.pages);

        if (
          updated.status === 'completed' ||
          updated.status === 'partial' ||
          updated.status === 'failed' ||
          updated.status === 'cancelled'
        ) {
          loadHistory();
        }
      } catch {
        // Network polling error; will retry next interval
      }
    }, 1500);

    return () => clearInterval(interval);
  }, [activeRun, loadHistory]);

  const handleStartAudit = async (e?: FormEvent) => {
    if (e) e.preventDefault();
    setStartError(null);

    const rawList = urlsText
      .split('\n')
      .map((u) => u.trim())
      .filter((u) => u.length > 0);

    const cleanWebsite = websiteUrl.trim();
    const cleanSitemap = sitemapUrl.trim();

    if (rawList.length === 0 && !cleanWebsite && !cleanSitemap) {
      setStartError('Please provide at least one URL or a website URL for sitemap discovery.');
      return;
    }

    setIsStarting(true);
    try {
      const newRun = await createBatchAudit({
        urls: rawList.length > 0 ? rawList : undefined,
        website_url: cleanWebsite || undefined,
        sitemap_url: cleanSitemap || undefined,
        config: {
          max_pages: maxPages,
          concurrency: concurrency,
          include_browser: includeBrowser,
          page_timeout_seconds: 15.0,
        },
      });

      setActiveRun(newRun);
      setPages([]);
      setSelectedPage(null);
      loadHistory();
    } catch (err) {
      setStartError(err instanceof Error ? err.message : 'Failed to launch batch audit.');
    } finally {
      setIsStarting(false);
    }
  };

  const handleCancelAudit = async () => {
    if (!activeRun) return;
    try {
      const cancelledRun = await cancelBatchAudit(activeRun.id);
      setActiveRun(cancelledRun);
      loadHistory();
    } catch (err) {
      setStartError(err instanceof Error ? err.message : 'Failed to cancel audit run.');
    }
  };

  const handleLoadRun = async (runId: string) => {
    setStartError(null);
    try {
      const loaded = await getBatchAudit(runId);
      setActiveRun(loaded);
      const pagesRes = await getBatchPages(runId, undefined, 100, 0);
      setPages(pagesRes.pages);
      setSelectedPage(null);
    } catch (err) {
      setStartError(err instanceof Error ? err.message : 'Failed to load past audit run.');
    }
  };

  const handleExport = async (format: 'json' | 'csv' | 'markdown') => {
    if (!activeRun) return;
    setIsExporting(true);
    try {
      await downloadBatchExport(activeRun.id, format);
    } catch (err) {
      setStartError(err instanceof Error ? err.message : `Failed to export as ${format}.`);
    } finally {
      setIsExporting(false);
    }
  };

  const getStatusBadge = (status: RunStatus | PageStatus) => {
    switch (status) {
      case 'completed':
      case 'success':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-emerald-950/80 text-emerald-400 border border-emerald-800">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            {status.toUpperCase()}
          </span>
        );
      case 'running':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-blue-950/80 text-blue-400 border border-blue-800 animate-pulse">
            <span className="w-1.5 h-1.5 rounded-full bg-blue-400" />
            RUNNING
          </span>
        );
      case 'queued':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-amber-950/80 text-amber-400 border border-amber-800">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
            QUEUED
          </span>
        );
      case 'partial':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-yellow-950/80 text-yellow-400 border border-yellow-800">
            <span className="w-1.5 h-1.5 rounded-full bg-yellow-400" />
            PARTIAL
          </span>
        );
      case 'failed':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-rose-950/80 text-rose-400 border border-rose-800">
            <span className="w-1.5 h-1.5 rounded-full bg-rose-400" />
            FAILED
          </span>
        );
      case 'cancelled':
      case 'skipped':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-slate-800 text-slate-400 border border-slate-700">
            <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
            {status.toUpperCase()}
          </span>
        );
      default:
        return null;
    }
  };

  const filteredPages = pages.filter((p) => {
    if (pageStatusFilter === 'all') return true;
    return p.status === pageStatusFilter;
  });

  const progressPercent =
    activeRun && activeRun.total_pages > 0
      ? Math.min(
          100,
          Math.round(
            ((activeRun.completed_pages + activeRun.failed_pages + activeRun.skipped_pages) /
              activeRun.total_pages) *
              100,
          ),
        )
      : 0;

  const summary = activeRun?.aggregate_summary;

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold text-white tracking-tight">
          Batch Auditing & Website Health Engine
        </h2>
        <p className="text-sm text-slate-400 mt-1">
          Audit multiple URLs concurrently with bounded concurrency, detect duplicate content, verify internal links, and export executive reports.
        </p>
      </div>

      {/* Error alert */}
      {startError && (
        <div className="p-4 rounded-xl bg-rose-950/50 border border-rose-800 text-rose-300 text-sm flex items-start gap-3">
          <span className="text-lg">⚠️</span>
          <div className="flex-1">
            <div className="font-semibold">Batch Audit Error</div>
            <div>{startError}</div>
          </div>
        </div>
      )}

      {/* Configuration & Launch Card */}
      <div className="p-6 rounded-2xl bg-slate-900/80 border border-slate-800 shadow-xl backdrop-blur-sm space-y-6">
        <form onSubmit={handleStartAudit} className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Direct URL list */}
            <div className="space-y-2">
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400">
                Target URLs to Audit (One URL per line)
              </label>
              <textarea
                value={urlsText}
                onChange={(e) => setUrlsText(e.target.value)}
                rows={6}
                placeholder="https://example.com/page1&#10;https://example.com/page2"
                className="w-full px-4 py-3 rounded-xl bg-slate-950 border border-slate-800 text-slate-100 placeholder-slate-600 focus:outline-none focus:border-cyan-500 font-mono text-xs transition-colors"
              />
              <p className="text-xs text-slate-500">
                Enter multiple pages to audit, or paste URLs discovered from sitemaps.
              </p>
            </div>

            {/* Sitemap Discovery options */}
            <div className="space-y-4">
              <div className="space-y-2">
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Or Discover From Website Root
                </label>
                <input
                  type="text"
                  value={websiteUrl}
                  onChange={(e) => setWebsiteUrl(e.target.value)}
                  placeholder="https://example.com"
                  className="w-full px-4 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-slate-100 placeholder-slate-600 focus:outline-none focus:border-cyan-500 text-sm font-mono transition-colors"
                />
              </div>

              <div className="space-y-2">
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Explicit Sitemap XML (Optional)
                </label>
                <input
                  type="text"
                  value={sitemapUrl}
                  onChange={(e) => setSitemapUrl(e.target.value)}
                  placeholder="https://example.com/sitemap.xml"
                  className="w-full px-4 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-slate-100 placeholder-slate-600 focus:outline-none focus:border-cyan-500 text-sm font-mono transition-colors"
                />
              </div>

              {/* Execution limits */}
              <div className="grid grid-cols-2 gap-4 pt-1">
                <div>
                  <label className="block text-xs text-slate-400 font-medium mb-1">
                    Max Pages Limit: <span className="text-cyan-400 font-semibold">{maxPages}</span>
                  </label>
                  <input
                    type="range"
                    min={1}
                    max={100}
                    value={maxPages}
                    onChange={(e) => setMaxPages(parseInt(e.target.value, 10))}
                    className="w-full accent-cyan-500 cursor-pointer"
                  />
                </div>

                <div>
                  <label className="block text-xs text-slate-400 font-medium mb-1">
                    Concurrency: <span className="text-cyan-400 font-semibold">{concurrency}</span>
                  </label>
                  <input
                    type="range"
                    min={1}
                    max={10}
                    value={concurrency}
                    onChange={(e) => setConcurrency(parseInt(e.target.value, 10))}
                    className="w-full accent-cyan-500 cursor-pointer"
                  />
                </div>
              </div>

              {/* Browser audit toggle */}
              <label className="flex items-center gap-3 pt-1 cursor-pointer">
                <input
                  type="checkbox"
                  checked={includeBrowser}
                  onChange={(e) => setIncludeBrowser(e.target.checked)}
                  className="w-4 h-4 rounded bg-slate-950 border-slate-700 text-cyan-500 focus:ring-cyan-500"
                />
                <span className="text-xs text-slate-300">
                  Include Headless Browser Rendering (Chromium DOM, Hydration & Diagnostics)
                </span>
              </label>
            </div>
          </div>

          <div className="flex items-center justify-between pt-2 border-t border-slate-800/80">
            <div className="text-xs text-slate-500">
              Bounded concurrency &amp; SSRF protections enforced on every request.
            </div>
            <button
              type="submit"
              disabled={isStarting}
              className="px-6 py-2.5 rounded-xl font-semibold text-sm bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white shadow-lg shadow-cyan-950/50 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
            >
              {isStarting ? 'Launching Batch...' : 'Start Batch Audit'}
            </button>
          </div>
        </form>
      </div>

      {/* Active Run Dashboard */}
      {activeRun && (
        <div className="space-y-6 p-6 rounded-2xl bg-slate-900/90 border border-slate-800 shadow-2xl backdrop-blur-md">
          {/* Top Status & Controls */}
          <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-slate-800">
            <div>
              <div className="flex items-center gap-3">
                <h3 className="text-lg font-bold text-white">
                  Audit Run: <span className="font-mono text-cyan-400">{activeRun.id.slice(0, 8)}</span>
                </h3>
                {getStatusBadge(activeRun.status)}
                <span className="text-xs text-slate-400 px-2.5 py-0.5 rounded bg-slate-800 font-mono">
                  {activeRun.mode.toUpperCase()}
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-1 font-mono truncate max-w-xl">
                Origin: {activeRun.target_origin}
              </p>
            </div>

            <div className="flex items-center gap-3">
              {(activeRun.status === 'running' || activeRun.status === 'queued') && (
                <button
                  type="button"
                  onClick={handleCancelAudit}
                  className="px-4 py-1.5 rounded-lg text-xs font-semibold bg-rose-950/80 text-rose-300 border border-rose-800 hover:bg-rose-900 transition-colors"
                >
                  Cancel Run
                </button>
              )}

              {/* Export Buttons */}
              <div className="flex items-center gap-1.5 bg-slate-950 p-1 rounded-xl border border-slate-800">
                <span className="text-[11px] font-semibold text-slate-500 px-2 uppercase tracking-wider">
                  Export:
                </span>
                <button
                  type="button"
                  disabled={isExporting}
                  onClick={() => handleExport('json')}
                  className="px-2.5 py-1 rounded-lg text-xs font-medium text-slate-300 hover:text-white hover:bg-slate-800 transition-colors"
                >
                  JSON
                </button>
                <button
                  type="button"
                  disabled={isExporting}
                  onClick={() => handleExport('csv')}
                  className="px-2.5 py-1 rounded-lg text-xs font-medium text-slate-300 hover:text-white hover:bg-slate-800 transition-colors"
                >
                  CSV
                </button>
                <button
                  type="button"
                  disabled={isExporting}
                  onClick={() => handleExport('markdown')}
                  className="px-2.5 py-1 rounded-lg text-xs font-medium text-slate-300 hover:text-white hover:bg-slate-800 transition-colors"
                >
                  Markdown
                </button>
              </div>
            </div>
          </div>

          {/* Progress Bar */}
          <div className="space-y-2">
            <div className="flex justify-between text-xs font-medium">
              <span className="text-slate-400">
                Progress: {activeRun.completed_pages + activeRun.failed_pages + activeRun.skipped_pages} / {activeRun.total_pages} Pages
              </span>
              <span className="text-cyan-400 font-bold">{progressPercent}%</span>
            </div>
            <div className="w-full h-2.5 rounded-full bg-slate-950 overflow-hidden border border-slate-800">
              <div
                className="h-full bg-gradient-to-r from-cyan-500 to-blue-500 transition-all duration-500 ease-out"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </div>

          {/* High-Level Stat Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800">
              <div className="text-xs font-medium text-slate-400">Total In Scope</div>
              <div className="text-2xl font-bold text-white mt-1">{activeRun.total_pages}</div>
            </div>
            <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800">
              <div className="text-xs font-medium text-emerald-400">Completed (Success)</div>
              <div className="text-2xl font-bold text-emerald-400 mt-1">{activeRun.completed_pages}</div>
            </div>
            <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800">
              <div className="text-xs font-medium text-rose-400">Failed / Errors</div>
              <div className="text-2xl font-bold text-rose-400 mt-1">{activeRun.failed_pages}</div>
            </div>
            <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800">
              <div className="text-xs font-medium text-slate-400">Skipped</div>
              <div className="text-2xl font-bold text-slate-400 mt-1">{activeRun.skipped_pages}</div>
            </div>
          </div>

          {/* Aggregate SEO Findings Overview */}
          {summary && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2">
              <div className="p-4 rounded-xl bg-amber-950/20 border border-amber-900/40">
                <div className="text-xs font-semibold uppercase tracking-wider text-amber-400">
                  Duplicate Content
                </div>
                <div className="text-xl font-bold text-amber-300 mt-1">
                  {summary.duplicate_titles.length} Titles / {summary.duplicate_descriptions.length} Descriptions
                </div>
                <div className="text-xs text-amber-400/80 mt-1">
                  Missing: {summary.missing_titles_count} titles, {summary.missing_descriptions_count} descriptions
                </div>
              </div>

              <div className="p-4 rounded-xl bg-rose-950/20 border border-rose-900/40">
                <div className="text-xs font-semibold uppercase tracking-wider text-rose-400">
                  Internal Link Health
                </div>
                <div className="text-xl font-bold text-rose-300 mt-1">
                  {summary.internal_link_analysis.confirmed_broken_links.length} Confirmed Broken
                </div>
                <div className="text-xs text-rose-400/80 mt-1">
                  Checked: {summary.internal_link_analysis.total_internal_links_checked} internal, {summary.internal_link_analysis.external_links_count} external
                </div>
              </div>

              <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800">
                <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  HTTP Status Breakdown
                </div>
                <div className="flex flex-wrap gap-2 mt-2">
                  {Object.entries(summary.status_code_distribution).map(([code, count]) => (
                    <span
                      key={code}
                      className="px-2 py-0.5 rounded text-xs font-mono font-semibold bg-slate-800 text-slate-200 border border-slate-700"
                    >
                      {code}: {count}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Details Section Tabs */}
          <div className="space-y-4 pt-4 border-t border-slate-800">
            <div className="flex items-center gap-2 border-b border-slate-800 pb-3">
              <button
                type="button"
                onClick={() => setActiveDetailTab('pages')}
                className={`px-4 py-2 rounded-xl text-xs font-semibold transition-all ${
                  activeDetailTab === 'pages'
                    ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                Audited Pages ({filteredPages.length})
              </button>
              <button
                type="button"
                onClick={() => setActiveDetailTab('duplicates')}
                className={`px-4 py-2 rounded-xl text-xs font-semibold transition-all ${
                  activeDetailTab === 'duplicates'
                    ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                Duplicate Content ({summary ? summary.duplicate_titles.length + summary.duplicate_descriptions.length : 0})
              </button>
              <button
                type="button"
                onClick={() => setActiveDetailTab('links')}
                className={`px-4 py-2 rounded-xl text-xs font-semibold transition-all ${
                  activeDetailTab === 'links'
                    ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                Link Health ({summary ? summary.internal_link_analysis.confirmed_broken_links.length : 0} Issues)
              </button>
            </div>

            {/* TAB: Audited Pages */}
            {activeDetailTab === 'pages' && (
              <div className="space-y-3">
                {/* Status filter pills */}
                <div className="flex items-center gap-2">
                  <span className="text-xs text-slate-500 font-medium">Filter:</span>
                  {(['all', 'success', 'failed', 'skipped'] as const).map((st) => (
                    <button
                      key={st}
                      type="button"
                      onClick={() => setPageStatusFilter(st)}
                      className={`px-3 py-1 rounded-lg text-xs font-medium capitalize transition-colors ${
                        pageStatusFilter === st
                          ? 'bg-slate-800 text-white font-semibold'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      {st}
                    </button>
                  ))}
                </div>

                {/* Table */}
                <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/60">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-900/80 text-slate-400 border-b border-slate-800 uppercase tracking-wider font-semibold">
                      <tr>
                        <th className="py-3 px-4">URL</th>
                        <th className="py-3 px-3">Status</th>
                        <th className="py-3 px-3">HTTP</th>
                        <th className="py-3 px-3">Duration</th>
                        <th className="py-3 px-4">Page Title</th>
                        <th className="py-3 px-3 text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60">
                      {filteredPages.length === 0 ? (
                        <tr>
                          <td colSpan={6} className="py-8 text-center text-slate-500">
                            No audited pages matching filter.
                          </td>
                        </tr>
                      ) : (
                        filteredPages.map((page) => (
                          <tr key={page.id || page.url} className="hover:bg-slate-900/50 transition-colors">
                            <td className="py-3 px-4 font-mono text-cyan-300 max-w-xs truncate" title={page.url}>
                              {page.url}
                            </td>
                            <td className="py-3 px-3">{getStatusBadge(page.status)}</td>
                            <td className="py-3 px-3 font-mono text-slate-300">
                              {page.status_code || (page.status === 'failed' ? 'ERR' : '—')}
                            </td>
                            <td className="py-3 px-3 font-mono text-slate-400">
                              {page.fetch_duration_ms ? `${page.fetch_duration_ms}ms` : '—'}
                            </td>
                            <td className="py-3 px-4 text-slate-300 max-w-sm truncate" title={page.title || ''}>
                              {page.title || (
                                <span className="text-slate-600 italic">
                                  {page.status === 'failed' ? page.error_message || 'Failed' : 'No title'}
                                </span>
                              )}
                            </td>
                            <td className="py-3 px-3 text-right">
                              <button
                                type="button"
                                onClick={() => setSelectedPage(page)}
                                className="px-3 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs transition-colors"
                              >
                                View
                              </button>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* TAB: Duplicate Content */}
            {activeDetailTab === 'duplicates' && (
              <div className="space-y-6">
                {summary && summary.duplicate_titles.length > 0 && (
                  <div className="space-y-3">
                    <h4 className="text-sm font-bold text-amber-300">
                      Duplicate Page Titles ({summary.duplicate_titles.length} groups)
                    </h4>
                    <div className="space-y-3">
                      {summary.duplicate_titles.map((group, idx) => (
                        <div key={idx} className="p-4 rounded-xl bg-slate-950 border border-amber-900/30 space-y-2">
                          <div className="text-sm font-semibold text-white">
                            &ldquo;{group.title}&rdquo; <span className="text-xs text-amber-400 font-mono">({group.count} pages)</span>
                          </div>
                          <ul className="text-xs font-mono text-slate-400 space-y-1 pl-4 list-disc">
                            {group.urls.map((u) => (
                              <li key={u}>{u}</li>
                            ))}
                          </ul>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {summary && summary.duplicate_descriptions.length > 0 && (
                  <div className="space-y-3">
                    <h4 className="text-sm font-bold text-amber-300">
                      Duplicate Meta Descriptions ({summary.duplicate_descriptions.length} groups)
                    </h4>
                    <div className="space-y-3">
                      {summary.duplicate_descriptions.map((group, idx) => (
                        <div key={idx} className="p-4 rounded-xl bg-slate-950 border border-amber-900/30 space-y-2">
                          <div className="text-sm font-semibold text-white">
                            &ldquo;{group.description}&rdquo; <span className="text-xs text-amber-400 font-mono">({group.count} pages)</span>
                          </div>
                          <ul className="text-xs font-mono text-slate-400 space-y-1 pl-4 list-disc">
                            {group.urls.map((u) => (
                              <li key={u}>{u}</li>
                            ))}
                          </ul>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {summary &&
                  summary.duplicate_titles.length === 0 &&
                  summary.duplicate_descriptions.length === 0 && (
                    <div className="p-8 text-center text-slate-500 rounded-xl border border-slate-800">
                      No duplicate titles or descriptions detected across the audited batch.
                    </div>
                  )}
              </div>
            )}

            {/* TAB: Link Health */}
            {activeDetailTab === 'links' && (
              <div className="space-y-6">
                {summary && summary.internal_link_analysis.confirmed_broken_links.length > 0 ? (
                  <div className="space-y-3">
                    <h4 className="text-sm font-bold text-rose-400">
                      Confirmed Broken Internal Links ({summary.internal_link_analysis.confirmed_broken_links.length})
                    </h4>
                    <div className="overflow-x-auto rounded-xl border border-rose-900/30 bg-slate-950">
                      <table className="w-full text-left text-xs">
                        <thead className="bg-rose-950/30 text-rose-300 border-b border-rose-900/40 uppercase font-semibold">
                          <tr>
                            <th className="py-2.5 px-4">Origin / Source Page</th>
                            <th className="py-2.5 px-4">Broken Target Link</th>
                            <th className="py-2.5 px-3">Target HTTP Status</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/60">
                          {summary.internal_link_analysis.confirmed_broken_links.map((link, idx) => (
                            <tr key={idx} className="hover:bg-slate-900/40">
                              <td className="py-2.5 px-4 font-mono text-slate-300">{link.source_url}</td>
                              <td className="py-2.5 px-4 font-mono text-rose-400">{link.target_url}</td>
                              <td className="py-2.5 px-3 font-mono text-rose-300 font-bold">
                                {link.status_code || 'Failed'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : (
                  <div className="p-8 text-center text-slate-500 rounded-xl border border-slate-800">
                    No confirmed broken internal links detected within the audited scope.
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Page Findings Modal */}
      {selectedPage && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-3xl w-full max-h-[85vh] overflow-y-auto p-6 space-y-4 shadow-2xl">
            <div className="flex items-start justify-between">
              <div>
                <h4 className="text-lg font-bold text-white">Page Audit Details</h4>
                <p className="text-xs text-cyan-400 font-mono mt-0.5 break-all">{selectedPage.url}</p>
              </div>
              <button
                type="button"
                onClick={() => setSelectedPage(null)}
                className="px-3 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold"
              >
                Close
              </button>
            </div>

            <div className="grid grid-cols-2 gap-4 text-xs font-mono p-4 rounded-xl bg-slate-950 border border-slate-800">
              <div>
                <span className="text-slate-500">Status: </span>
                <span className="text-slate-200">{selectedPage.status}</span>
              </div>
              <div>
                <span className="text-slate-500">HTTP Status: </span>
                <span className="text-slate-200">{selectedPage.status_code || '—'}</span>
              </div>
              <div>
                <span className="text-slate-500">Duration: </span>
                <span className="text-slate-200">{selectedPage.fetch_duration_ms ? `${selectedPage.fetch_duration_ms}ms` : '—'}</span>
              </div>
              <div>
                <span className="text-slate-500">Audited At: </span>
                <span className="text-slate-200">{selectedPage.audited_at}</span>
              </div>
            </div>

            {selectedPage.title && (
              <div className="text-xs space-y-1">
                <div className="text-slate-500 font-semibold uppercase tracking-wider">Page Title:</div>
                <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 text-slate-200 font-mono">
                  {selectedPage.title}
                </div>
              </div>
            )}

            {selectedPage.meta_description && (
              <div className="text-xs space-y-1">
                <div className="text-slate-500 font-semibold uppercase tracking-wider">Meta Description:</div>
                <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 text-slate-200 font-mono">
                  {selectedPage.meta_description}
                </div>
              </div>
            )}

            {selectedPage.error_message && (
              <div className="text-xs p-3 rounded-lg bg-rose-950/50 border border-rose-800 text-rose-300">
                <div className="font-semibold">Error Message:</div>
                <div>{selectedPage.error_message}</div>
              </div>
            )}

            {/* Findings list */}
            {selectedPage.findings && selectedPage.findings.length > 0 && (
              <div className="space-y-2 pt-2">
                <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  Rule Findings ({selectedPage.findings.length})
                </div>
                <div className="space-y-2">
                  {selectedPage.findings.map((f, idx) => (
                    <div key={idx} className="p-3 rounded-lg bg-slate-950 border border-slate-800 text-xs space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-white">{f.title}</span>
                        {getStatusBadge(f.status as any)}
                      </div>
                      <p className="text-slate-300">{f.explanation}</p>
                      {f.recommendation && (
                        <p className="text-cyan-400/90 text-[11px]">Recommendation: {f.recommendation}</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Audit History Card */}
      <div className="p-6 rounded-2xl bg-slate-900/60 border border-slate-800 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-bold text-white">Recent Audit History (SQLite)</h3>
          <button
            type="button"
            onClick={loadHistory}
            className="text-xs text-cyan-400 hover:text-cyan-300"
          >
            Refresh History
          </button>
        </div>

        <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/40">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-900/80 text-slate-400 border-b border-slate-800 uppercase font-semibold">
              <tr>
                <th className="py-2.5 px-4">Run ID</th>
                <th className="py-2.5 px-4">Origin / Target</th>
                <th className="py-2.5 px-3">Mode</th>
                <th className="py-2.5 px-3">Status</th>
                <th className="py-2.5 px-3">Pages (Total / Done / Failed)</th>
                <th className="py-2.5 px-3">Created</th>
                <th className="py-2.5 px-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {historyRuns.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-6 text-center text-slate-500">
                    No past batch audit runs recorded.
                  </td>
                </tr>
              ) : (
                historyRuns.map((r) => (
                  <tr key={r.id} className="hover:bg-slate-900/40 transition-colors">
                    <td className="py-2.5 px-4 font-mono text-cyan-400">{r.id.slice(0, 8)}</td>
                    <td className="py-2.5 px-4 font-mono text-slate-300 truncate max-w-xs">{r.target_origin}</td>
                    <td className="py-2.5 px-3 font-mono text-slate-400">{r.mode}</td>
                    <td className="py-2.5 px-3">{getStatusBadge(r.status)}</td>
                    <td className="py-2.5 px-3 font-mono text-slate-300">
                      {r.total_pages} / {r.completed_pages} / {r.failed_pages}
                    </td>
                    <td className="py-2.5 px-3 text-slate-400 font-mono">
                      {r.created_at ? new Date(r.created_at).toLocaleTimeString() : '—'}
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      <button
                        type="button"
                        onClick={() => handleLoadRun(r.id)}
                        className="px-3 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs transition-colors"
                      >
                        Load
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
