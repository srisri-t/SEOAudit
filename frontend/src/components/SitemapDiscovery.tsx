import { useState, type FormEvent } from 'react';
import { discoverSitemaps, type SitemapDiscoverResponse } from '../services/api';

interface SitemapDiscoveryProps {
  onSendToBatch?: (urls: string[], websiteUrl?: string) => void;
}

export default function SitemapDiscovery({ onSendToBatch }: SitemapDiscoveryProps = {}) {
  const [websiteUrl, setWebsiteUrl] = useState<string>('https://www.holyspace.live');
  const [sitemapUrl, setSitemapUrl] = useState<string>('');
  const [maxUrls, setMaxUrls] = useState<number>(1000);
  const [isDiscovering, setIsDiscovering] = useState<boolean>(false);
  const [discoveryError, setDiscoveryError] = useState<string | null>(null);
  const [discoveryResult, setDiscoveryResult] = useState<SitemapDiscoverResponse | null>(null);

  // Results filtering and pagination
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [copied, setCopied] = useState<boolean>(false);

  const pageSize = 25;

  const handleDiscover = async (e?: FormEvent) => {
    if (e) e.preventDefault();

    const trimmedWebsite = websiteUrl.trim();
    if (!trimmedWebsite) {
      setDiscoveryError('Please enter a target website URL.');
      return;
    }

    if (!trimmedWebsite.startsWith('http://') && !trimmedWebsite.startsWith('https://')) {
      setDiscoveryError('Website URL must begin with http:// or https://');
      return;
    }

    const trimmedSitemap = sitemapUrl.trim();
    if (trimmedSitemap && !trimmedSitemap.startsWith('http://') && !trimmedSitemap.startsWith('https://')) {
      setDiscoveryError('Explicit sitemap URL must begin with http:// or https://');
      return;
    }

    setIsDiscovering(true);
    setDiscoveryError(null);
    setCurrentPage(1);
    setSearchQuery('');

    try {
      const res = await discoverSitemaps(trimmedWebsite, trimmedSitemap || null, maxUrls);
      setDiscoveryResult(res);
    } catch (err) {
      setDiscoveryError(err instanceof Error ? err.message : 'An error occurred during sitemap discovery.');
    } finally {
      setIsDiscovering(false);
    }
  };

  const filteredUrls = discoveryResult
    ? discoveryResult.urls.filter((u) => u.toLowerCase().includes(searchQuery.toLowerCase()))
    : [];

  const totalPages = Math.ceil(filteredUrls.length / pageSize) || 1;
  const paginatedUrls = filteredUrls.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  const handleCopyAll = () => {
    if (!discoveryResult || !discoveryResult.urls.length) return;
    navigator.clipboard.writeText(discoveryResult.urls.join('\n'));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'Sitemap found':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-semibold bg-emerald-950/80 text-emerald-400 border border-emerald-800">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            SITEMAP FOUND
          </span>
        );
      case 'Discovery blocked by security validation':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-semibold bg-rose-950/80 text-rose-400 border border-rose-800">
            <span className="w-2 h-2 rounded-full bg-rose-400" />
            BLOCKED BY SECURITY
          </span>
        );
      case 'Invalid sitemap':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-semibold bg-amber-950/80 text-amber-400 border border-amber-800">
            <span className="w-2 h-2 rounded-full bg-amber-400" />
            INVALID SITEMAP
          </span>
        );
      case 'Sitemap inaccessible':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-semibold bg-orange-950/80 text-orange-400 border border-orange-800">
            <span className="w-2 h-2 rounded-full bg-orange-400" />
            INACCESSIBLE
          </span>
        );
      case 'Sitemap not found':
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-semibold bg-slate-800 text-slate-300 border border-slate-700">
            <span className="w-2 h-2 rounded-full bg-slate-400" />
            NOT FOUND
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      {/* Form Section */}
      <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-6 shadow-xl space-y-4">
        <div>
          <h2 className="text-xl font-bold text-white tracking-tight">
            Discover &amp; Parse Sitemaps
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Automatically discover XML sitemaps via <code className="text-indigo-300">/robots.txt</code> inspection and standard fallback, or provide an explicit sitemap URL.
          </p>
        </div>

        <form onSubmit={handleDiscover} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-12 gap-3">
            {/* Website URL */}
            <div className="md:col-span-6">
              <label htmlFor="website-url-input" className="block text-xs font-medium text-slate-300 mb-1">
                Website URL <span className="text-indigo-400">*</span>
              </label>
              <input
                id="website-url-input"
                type="text"
                value={websiteUrl}
                onChange={(e) => setWebsiteUrl(e.target.value)}
                placeholder="https://example.com/"
                disabled={isDiscovering}
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-slate-700 text-white placeholder-slate-500 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 disabled:opacity-50 transition-all font-mono"
              />
            </div>

            {/* Optional Explicit Sitemap URL */}
            <div className="md:col-span-4">
              <label htmlFor="explicit-sitemap-input" className="block text-xs font-medium text-slate-300 mb-1">
                Explicit Sitemap URL <span className="text-slate-500">(Optional)</span>
              </label>
              <input
                id="explicit-sitemap-input"
                type="text"
                value={sitemapUrl}
                onChange={(e) => setSitemapUrl(e.target.value)}
                placeholder="https://example.com/sitemap.xml"
                disabled={isDiscovering}
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-slate-700 text-white placeholder-slate-500 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 disabled:opacity-50 transition-all font-mono"
              />
            </div>

            {/* URL Limit */}
            <div className="md:col-span-2">
              <label htmlFor="max-urls-input" className="block text-xs font-medium text-slate-300 mb-1">
                Max URLs (1-10k)
              </label>
              <input
                id="max-urls-input"
                type="number"
                min={1}
                max={10000}
                value={maxUrls}
                onChange={(e) => setMaxUrls(Math.max(1, Math.min(10000, Number(e.target.value) || 1000)))}
                disabled={isDiscovering}
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-slate-700 text-white text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 disabled:opacity-50 transition-all font-mono"
              />
            </div>
          </div>

          <div className="flex items-center justify-between pt-1">
            <span className="text-[11px] text-slate-500">
              Strict SSRF protections active: loopback, private ranges, and cloud metadata destinations are blocked.
            </span>
            <button
              type="submit"
              disabled={isDiscovering}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl font-semibold text-xs text-white bg-gradient-to-r from-indigo-500 to-violet-600 hover:from-indigo-600 hover:to-violet-700 disabled:opacity-50 disabled:cursor-not-allowed shadow-md shadow-indigo-500/20 transition-all"
            >
              {isDiscovering ? (
                <>
                  <svg className="animate-spin h-3.5 w-3.5 text-white" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    />
                  </svg>
                  <span>Discovering Sitemaps...</span>
                </>
              ) : (
                <>
                  <span>🔍</span>
                  <span>Discover Sitemaps</span>
                </>
              )}
            </button>
          </div>
        </form>

        {/* Error Banner */}
        {discoveryError && (
          <div className="p-4 rounded-xl bg-rose-950/80 border border-rose-800 text-rose-200 text-xs flex items-start justify-between gap-3 animate-fadeIn">
            <div className="space-y-1">
              <div className="font-semibold text-rose-300">Discovery Error</div>
              <div>{discoveryError}</div>
            </div>
            <button
              type="button"
              onClick={() => handleDiscover()}
              disabled={isDiscovering}
              className="px-3 py-1 rounded-lg bg-rose-900/80 hover:bg-rose-800 text-white font-medium text-[11px] transition-colors shrink-0"
            >
              Retry
            </button>
          </div>
        )}
      </section>

      {/* Discovery Results Section */}
      {discoveryResult ? (
        <div className="space-y-6">
          {/* Summary Overview Card */}
          <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-6 shadow-xl space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800/80 pb-4">
              <div>
                <span className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">
                  Target Website
                </span>
                <h3 className="text-base font-bold text-white break-all font-mono mt-0.5">
                  {discoveryResult.website_url}
                </h3>
              </div>
              <div className="flex items-center gap-3">
                {getStatusBadge(discoveryResult.sitemap_status)}
              </div>
            </div>

            {/* Metric Counters */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="p-3.5 rounded-xl bg-slate-950/60 border border-slate-800 flex items-center justify-between">
                <div>
                  <div className="text-[11px] text-slate-400">Discovered URLs</div>
                  <div className="text-xl font-bold text-indigo-400 mt-0.5">
                    {discoveryResult.discovered_url_count.toLocaleString()}
                  </div>
                </div>
                <div className="text-xl">📄</div>
              </div>

              <div className="p-3.5 rounded-xl bg-slate-950/60 border border-slate-800 flex items-center justify-between">
                <div>
                  <div className="text-[11px] text-slate-400">Sitemaps Processed</div>
                  <div className="text-xl font-bold text-violet-400 mt-0.5">
                    {discoveryResult.discovered_sitemaps.length}
                  </div>
                </div>
                <div className="text-xl">🗺️</div>
              </div>

              <div className="p-3.5 rounded-xl bg-slate-950/60 border border-slate-800 flex items-center justify-between">
                <div>
                  <div className="text-[11px] text-slate-400">Processing Time</div>
                  <div className="text-xl font-bold text-emerald-400 mt-0.5">
                    {discoveryResult.processing_duration_ms} ms
                  </div>
                </div>
                <div className="text-xl">⚡</div>
              </div>
            </div>

            {/* Sitemaps List */}
            {discoveryResult.discovered_sitemaps.length > 0 && (
              <div className="space-y-1.5 pt-2">
                <span className="text-xs font-semibold text-slate-300">
                  Processed Sitemap Files:
                </span>
                <div className="flex flex-wrap gap-2">
                  {discoveryResult.discovered_sitemaps.map((sm, idx) => (
                    <a
                      key={idx}
                      href={sm}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-mono bg-indigo-950/60 text-indigo-300 border border-indigo-800/80 hover:bg-indigo-900/60 transition-colors"
                    >
                      <span>{sm}</span>
                      <span className="text-[10px]">↗</span>
                    </a>
                  ))}
                </div>
              </div>
            )}

            {/* Warnings Alert */}
            {discoveryResult.warnings.length > 0 && (
              <div className="p-4 rounded-xl bg-amber-950/40 border border-amber-800/60 space-y-2">
                <div className="text-xs font-semibold text-amber-300 flex items-center gap-2">
                  <span>⚠️</span>
                  <span>Warnings Encountered ({discoveryResult.warnings.length})</span>
                </div>
                <ul className="text-xs text-amber-200/80 space-y-1 list-disc list-inside">
                  {discoveryResult.warnings.map((w, idx) => (
                    <li key={idx} className="break-all">{w}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Errors Alert */}
            {discoveryResult.errors.length > 0 && (
              <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-800/60 space-y-2">
                <div className="text-xs font-semibold text-rose-300 flex items-center gap-2">
                  <span>🛑</span>
                  <span>Errors Encountered ({discoveryResult.errors.length})</span>
                </div>
                <ul className="text-xs text-rose-200/80 space-y-1 list-disc list-inside">
                  {discoveryResult.errors.map((e, idx) => (
                    <li key={idx} className="break-all">{e}</li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          {/* Discovered URLs List / Table */}
          {discoveryResult.urls.length > 0 ? (
            <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-6 shadow-xl space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <h3 className="text-base font-bold text-white tracking-tight">
                    Discovered Page URLs ({filteredUrls.length})
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Extracted from verified sitemap XML entries.
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => {
                      setSearchQuery(e.target.value);
                      setCurrentPage(1);
                    }}
                    placeholder="Filter URLs..."
                    className="px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-700 text-white placeholder-slate-500 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500 font-mono"
                  />
                  <button
                    type="button"
                    onClick={handleCopyAll}
                    className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-medium text-slate-200 transition-colors flex items-center gap-1.5"
                  >
                    <span>{copied ? '✓ Copied' : '📋 Copy All'}</span>
                  </button>
                  {onSendToBatch && (
                    <button
                      type="button"
                      onClick={() => onSendToBatch(discoveryResult.urls, discoveryResult.website_url)}
                      className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-xs font-semibold text-white shadow-sm transition-colors flex items-center gap-1.5"
                    >
                      <span>🚀 Audit in Batch</span>
                    </button>
                  )}
                </div>
              </div>

              {/* URL List */}
              <div className="rounded-xl border border-slate-800 bg-slate-950/60 divide-y divide-slate-800/80 overflow-hidden font-mono text-xs">
                {paginatedUrls.map((url, index) => {
                  const globalIdx = (currentPage - 1) * pageSize + index + 1;
                  return (
                    <div
                      key={globalIdx}
                      className="px-4 py-2.5 flex items-center justify-between gap-3 hover:bg-slate-900/60 transition-colors group"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <span className="text-slate-500 select-none w-8 text-right shrink-0">
                          {globalIdx}.
                        </span>
                        <span className="text-slate-200 truncate select-all">{url}</span>
                      </div>
                      <a
                        href={url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-slate-500 group-hover:text-indigo-400 transition-colors text-[11px] shrink-0"
                        title="Open in new tab"
                      >
                        ↗
                      </a>
                    </div>
                  );
                })}
              </div>

              {/* Pagination Controls */}
              {totalPages > 1 && (
                <div className="flex items-center justify-between pt-2 text-xs text-slate-400">
                  <span>
                    Showing {(currentPage - 1) * pageSize + 1} to{' '}
                    {Math.min(currentPage * pageSize, filteredUrls.length)} of {filteredUrls.length}
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                      disabled={currentPage <= 1}
                      className="px-3 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                    >
                      Previous
                    </button>
                    <span className="font-mono text-slate-300">
                      {currentPage} / {totalPages}
                    </span>
                    <button
                      type="button"
                      onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                      disabled={currentPage >= totalPages}
                      className="px-3 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                    >
                      Next
                    </button>
                  </div>
                </div>
              )}
            </section>
          ) : (
            <section className="rounded-2xl border border-slate-800/80 bg-slate-900/40 p-6 text-center space-y-2">
              <div className="text-2xl">📭</div>
              <h4 className="text-sm font-semibold text-white">No URLs Extracted</h4>
              <p className="text-xs text-slate-400 max-w-sm mx-auto">
                No valid page URLs were discovered in the target sitemaps. Check the warnings or errors above for details.
              </p>
            </section>
          )}
        </div>
      ) : (
        /* Empty State */
        <section className="rounded-2xl border border-slate-800/80 bg-slate-900/40 p-8 text-center space-y-4">
          <div className="w-12 h-12 rounded-xl bg-slate-800/80 border border-slate-700/60 flex items-center justify-center mx-auto text-indigo-400 text-xl font-bold">
            🗺️
          </div>
          <div className="max-w-md mx-auto space-y-1.5">
            <h3 className="text-base font-semibold text-white">
              Discover Website Sitemaps
            </h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              Enter a website URL above and click &quot;Discover Sitemaps&quot; to inspect robots.txt and sitemap index files. All discovered URLs are verified and deduplicated.
            </p>
          </div>
          <button
            type="button"
            onClick={() => handleDiscover()}
            disabled={isDiscovering}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold text-indigo-300 bg-indigo-950/60 hover:bg-indigo-900/60 border border-indigo-800/60 transition-colors"
          >
            Discover Holy Space Sitemaps
          </button>
        </section>
      )}
    </div>
  );
}
