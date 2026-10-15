import { useState, useEffect, useCallback } from 'react';
import {
  listBatchAudits,
  compareBatchAudits,
  downloadComparisonExport,
  type BatchAuditRunResponse,
  type AuditComparisonResponse,
  type IssueChangeType,
} from '../services/api';

export default function AuditComparison() {
  // Available runs for selection
  const [runs, setRuns] = useState<BatchAuditRunResponse[]>([]);
  const [isLoadingRuns, setIsLoadingRuns] = useState<boolean>(true);
  const [runsError, setRunsError] = useState<string | null>(null);

  // Selected run IDs
  const [baselineRunId, setBaselineRunId] = useState<string>('');
  const [comparisonRunId, setComparisonRunId] = useState<string>('');

  // Comparison execution state
  const [isComparing, setIsComparing] = useState<boolean>(false);
  const [comparisonError, setComparisonError] = useState<string | null>(null);
  const [comparisonResult, setComparisonResult] = useState<AuditComparisonResponse | null>(null);

  // Detailed view tab and filter state
  const [activeDetailTab, setActiveDetailTab] = useState<'issues' | 'metadata' | 'coverage'>('issues');
  const [issueFilter, setIssueFilter] = useState<'all' | IssueChangeType>('all');
  const [isExporting, setIsExporting] = useState<'json' | 'markdown' | null>(null);

  // Load audit history for selection
  const loadRuns = useCallback(async () => {
    setIsLoadingRuns(true);
    setRunsError(null);
    try {
      const res = await listBatchAudits(50, 0);
      setRuns(res.runs);

      // Pre-select the latest two runs if available and compatible
      if (res.runs.length >= 2) {
        setComparisonRunId(res.runs[0].id);
        setBaselineRunId(res.runs[1].id);
      } else if (res.runs.length === 1) {
        setComparisonRunId(res.runs[0].id);
      }
    } catch (err) {
      setRunsError(err instanceof Error ? err.message : 'Failed to load audit history.');
    } finally {
      setIsLoadingRuns(false);
    }
  }, []);

  useEffect(() => {
    loadRuns();
  }, [loadRuns]);

  // Execute Comparison
  const handleCompare = async () => {
    if (!baselineRunId || !comparisonRunId) {
      setComparisonError('Please select both a baseline run and a comparison run.');
      return;
    }
    if (baselineRunId === comparisonRunId) {
      setComparisonError('Baseline and comparison runs must be distinct runs.');
      return;
    }

    setIsComparing(true);
    setComparisonError(null);

    try {
      const result = await compareBatchAudits(baselineRunId, comparisonRunId);
      setComparisonResult(result);
    } catch (err) {
      setComparisonError(err instanceof Error ? err.message : 'An error occurred during comparison.');
      setComparisonResult(null);
    } finally {
      setIsComparing(false);
    }
  };

  // Export handling
  const handleExport = async (format: 'json' | 'markdown') => {
    if (!comparisonResult) return;
    setIsExporting(format);
    try {
      await downloadComparisonExport(baselineRunId, comparisonRunId, format);
    } catch (err) {
      alert(`Export failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setIsExporting(null);
    }
  };

  // Get selected run metadata
  const baselineRunMeta = runs.find((r) => r.id === baselineRunId);
  const comparisonRunMeta = runs.find((r) => r.id === comparisonRunId);

  // Check origin compatibility warning before submission
  const originMismatch =
    baselineRunMeta &&
    comparisonRunMeta &&
    baselineRunMeta.target_origin !== comparisonRunMeta.target_origin &&
    baselineRunMeta.target_origin !== 'unknown' &&
    comparisonRunMeta.target_origin !== 'unknown';

  // Filtered issues
  const filteredIssues = comparisonResult
    ? comparisonResult.issue_changes.filter((item) => {
        if (issueFilter === 'all') return true;
        return item.change_type === issueFilter;
      })
    : [];

  return (
    <div className="space-y-6">
      {/* Run Selection Panel */}
      <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-6 shadow-xl space-y-5">
        <div>
          <div className="flex items-center gap-2">
            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-indigo-950 text-indigo-300 border border-indigo-700">
              M6.1
            </span>
            <h2 className="text-xl font-bold text-white tracking-tight">Audit Run Comparison</h2>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Compare two existing audit runs to identify newly introduced SEO issues, resolved problems,
            persistent issues, and metadata changes across pages.
          </p>
        </div>

        {runsError && (
          <div className="p-3 rounded-xl bg-rose-950/60 border border-rose-800 text-rose-300 text-xs">
            {runsError}
          </div>
        )}

        {isLoadingRuns ? (
          <div className="py-8 text-center text-slate-400 text-xs flex items-center justify-center gap-2">
            <div className="w-4 h-4 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin" />
            Loading audit runs...
          </div>
        ) : runs.length < 2 ? (
          <div className="py-6 px-4 rounded-xl border border-slate-800 bg-slate-950/60 text-center space-y-2">
            <p className="text-sm font-semibold text-slate-300">At least two audit runs are required for comparison.</p>
            <p className="text-xs text-slate-400">
              Run batch audits under the <strong className="text-indigo-400">Batch Auditing</strong> tab first to establish baseline and newer audit runs.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Baseline Run Selector */}
              <div className="space-y-1.5">
                <label htmlFor="baseline-run-select" className="text-xs font-semibold text-slate-300 flex items-center justify-between">
                  <span>1. Reference Baseline Run (Older)</span>
                  {baselineRunMeta && (
                    <span className="text-[10px] text-slate-400 font-mono">
                      {new Date(baselineRunMeta.created_at).toLocaleString()}
                    </span>
                  )}
                </label>
                <select
                  id="baseline-run-select"
                  value={baselineRunId}
                  onChange={(e) => setBaselineRunId(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                >
                  <option value="">Select baseline audit run...</option>
                  {runs.map((r) => (
                    <option key={r.id} value={r.id} disabled={r.id === comparisonRunId}>
                      {r.id.slice(0, 8)} • {r.target_origin} • {r.completed_pages}/{r.total_pages} pages ({r.status})
                    </option>
                  ))}
                </select>
              </div>

              {/* Comparison Run Selector */}
              <div className="space-y-1.5">
                <label htmlFor="comparison-run-select" className="text-xs font-semibold text-slate-300 flex items-center justify-between">
                  <span>2. Comparison Run (Newer)</span>
                  {comparisonRunMeta && (
                    <span className="text-[10px] text-slate-400 font-mono">
                      {new Date(comparisonRunMeta.created_at).toLocaleString()}
                    </span>
                  )}
                </label>
                <select
                  id="comparison-run-select"
                  value={comparisonRunId}
                  onChange={(e) => setComparisonRunId(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                >
                  <option value="">Select newer comparison run...</option>
                  {runs.map((r) => (
                    <option key={r.id} value={r.id} disabled={r.id === baselineRunId}>
                      {r.id.slice(0, 8)} • {r.target_origin} • {r.completed_pages}/{r.total_pages} pages ({r.status})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Incompatible Origin Warning */}
            {originMismatch && (
              <div className="p-3 rounded-xl bg-amber-950/60 border border-amber-800 text-amber-300 text-xs flex items-center gap-2">
                <span>⚠️</span>
                <span>
                  <strong>Website Scope Warning:</strong> Selected runs target different origins ({baselineRunMeta?.target_origin} vs {comparisonRunMeta?.target_origin}). Runs should evaluate the same website.
                </span>
              </div>
            )}

            {/* Comparison Error Banner */}
            {comparisonError && (
              <div className="p-3 rounded-xl bg-rose-950/60 border border-rose-800 text-rose-300 text-xs">
                {comparisonError}
              </div>
            )}

            {/* Action Bar */}
            <div className="flex items-center justify-between pt-2">
              <button
                type="button"
                onClick={loadRuns}
                className="text-xs text-slate-400 hover:text-slate-200 transition-colors"
              >
                🔄 Refresh Runs
              </button>

              <button
                type="button"
                onClick={handleCompare}
                disabled={isComparing || !baselineRunId || !comparisonRunId || baselineRunId === comparisonRunId}
                className={`px-5 py-2.5 rounded-xl font-semibold text-xs transition-all flex items-center gap-2 shadow-lg ${
                  isComparing || !baselineRunId || !comparisonRunId || baselineRunId === comparisonRunId
                    ? 'bg-slate-800 text-slate-500 cursor-not-allowed border border-slate-700'
                    : 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-indigo-600/30'
                }`}
              >
                {isComparing ? (
                  <>
                    <div className="w-3.5 h-3.5 rounded-full border-2 border-white border-t-transparent animate-spin" />
                    <span>Comparing Runs...</span>
                  </>
                ) : (
                  <>
                    <span>📊</span>
                    <span>Compare Audits</span>
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </section>

      {/* Comparison Results Section */}
      {comparisonResult && (
        <section className="space-y-6">
          {/* Executive Assessment Card */}
          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-6 shadow-xl space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-4">
              <div>
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Comparison Verdict
                </span>
                <div className="flex items-center gap-3 mt-1">
                  <span
                    className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-bold border uppercase ${
                      comparisonResult.assessment.verdict === 'improved'
                        ? 'bg-emerald-950/90 text-emerald-300 border-emerald-700'
                        : comparisonResult.assessment.verdict === 'deteriorated'
                        ? 'bg-rose-950/90 text-rose-300 border-rose-700'
                        : comparisonResult.assessment.verdict === 'unchanged'
                        ? 'bg-sky-950/90 text-sky-300 border-sky-700'
                        : comparisonResult.assessment.verdict === 'incomplete'
                        ? 'bg-purple-950/90 text-purple-300 border-purple-700'
                        : 'bg-amber-950/90 text-amber-300 border-amber-700'
                    }`}
                  >
                    <span className="w-2 h-2 rounded-full bg-current" />
                    {comparisonResult.assessment.verdict}
                  </span>
                  <h3 className="text-lg font-bold text-white tracking-tight">
                    {comparisonResult.assessment.headline}
                  </h3>
                </div>
              </div>

              {/* Export Buttons */}
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => handleExport('json')}
                  disabled={isExporting !== null}
                  className="px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-800/80 hover:bg-slate-700 text-xs font-semibold text-slate-200 transition-colors"
                >
                  {isExporting === 'json' ? 'Exporting...' : '📥 Export JSON'}
                </button>
                <button
                  type="button"
                  onClick={() => handleExport('markdown')}
                  disabled={isExporting !== null}
                  className="px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-800/80 hover:bg-slate-700 text-xs font-semibold text-slate-200 transition-colors"
                >
                  {isExporting === 'markdown' ? 'Exporting...' : '📄 Export Markdown'}
                </button>
              </div>
            </div>

            <p className="text-xs text-slate-300 leading-relaxed">
              {comparisonResult.assessment.explanation}
            </p>

            {/* Scope / Metadata details */}
            <div className="flex flex-wrap items-center gap-4 text-[11px] text-slate-400 pt-2 border-t border-slate-800/60">
              <div>
                <span className="text-slate-400">Target Website:</span>{' '}
                <strong className="text-slate-200 font-mono">{comparisonResult.summary.website_scope}</strong>
              </div>
              <div>
                <span className="text-slate-400">Baseline Run:</span>{' '}
                <span className="font-mono text-slate-300">{comparisonResult.summary.baseline_run_id.slice(0, 8)}</span>
              </div>
              <div>
                <span className="text-slate-400">Comparison Run:</span>{' '}
                <span className="font-mono text-slate-300">{comparisonResult.summary.comparison_run_id.slice(0, 8)}</span>
              </div>
              <div>
                <span className="text-slate-400">Completeness:</span>{' '}
                <span className="font-semibold text-indigo-300 uppercase">{comparisonResult.summary.comparison_completeness}</span>
              </div>
            </div>
          </div>

          {/* Metric Cards Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <div className="p-4 rounded-xl border border-rose-900/50 bg-rose-950/20 text-center space-y-1">
              <span className="text-[11px] font-semibold text-rose-400 uppercase">New Issues</span>
              <p className="text-2xl font-bold text-rose-300">{comparisonResult.summary.new_issues_count}</p>
              <span className="text-[10px] text-rose-400/80">Regressions detected</span>
            </div>

            <div className="p-4 rounded-xl border border-emerald-900/50 bg-emerald-950/20 text-center space-y-1">
              <span className="text-[11px] font-semibold text-emerald-400 uppercase">Resolved</span>
              <p className="text-2xl font-bold text-emerald-300">{comparisonResult.summary.resolved_issues_count}</p>
              <span className="text-[10px] text-emerald-400/80">Issues fixed</span>
            </div>

            <div className="p-4 rounded-xl border border-amber-900/50 bg-amber-950/20 text-center space-y-1">
              <span className="text-[11px] font-semibold text-amber-400 uppercase">Persistent</span>
              <p className="text-2xl font-bold text-amber-300">{comparisonResult.summary.persistent_issues_count}</p>
              <span className="text-[10px] text-amber-400/80">Unresolved issues</span>
            </div>

            <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/40 text-center space-y-1">
              <span className="text-[11px] font-semibold text-slate-400 uppercase">Common Pages</span>
              <p className="text-2xl font-bold text-slate-200">{comparisonResult.summary.common_pages_count}</p>
              <span className="text-[10px] text-slate-400">Audited in both</span>
            </div>

            <div className="p-4 rounded-xl border border-indigo-900/50 bg-indigo-950/20 text-center space-y-1">
              <span className="text-[11px] font-semibold text-indigo-400 uppercase">New Pages</span>
              <p className="text-2xl font-bold text-indigo-300">{comparisonResult.summary.new_pages_count}</p>
              <span className="text-[10px] text-indigo-400/80">Discovered pages</span>
            </div>

            <div className="p-4 rounded-xl border border-sky-900/50 bg-sky-950/20 text-center space-y-1">
              <span className="text-[11px] font-semibold text-sky-400 uppercase">Metadata Changes</span>
              <p className="text-2xl font-bold text-sky-300">{comparisonResult.summary.metadata_changes_count}</p>
              <span className="text-[10px] text-sky-400/80">Field modifications</span>
            </div>
          </div>

          {/* Coverage Warnings */}
          {comparisonResult.summary.coverage_warnings.length > 0 && (
            <div className="p-4 rounded-xl border border-amber-800/80 bg-amber-950/30 text-xs text-amber-300 space-y-1.5">
              <div className="font-semibold flex items-center gap-2">
                <span>⚠️</span>
                <span>Coverage & Reliability Notes:</span>
              </div>
              <ul className="list-disc list-inside space-y-1 pl-2 text-amber-300/90">
                {comparisonResult.summary.coverage_warnings.map((w, idx) => (
                  <li key={idx}>{w}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Detail Tabs Section */}
          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-6 shadow-xl space-y-5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setActiveDetailTab('issues')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                    activeDetailTab === 'issues'
                      ? 'bg-indigo-600 text-white'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                  }`}
                >
                  Issue Changes ({comparisonResult.issue_changes.length})
                </button>
                <button
                  type="button"
                  onClick={() => setActiveDetailTab('metadata')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                    activeDetailTab === 'metadata'
                      ? 'bg-indigo-600 text-white'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                  }`}
                >
                  Metadata Changes ({comparisonResult.metadata_changes.length})
                </button>
                <button
                  type="button"
                  onClick={() => setActiveDetailTab('coverage')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                    activeDetailTab === 'coverage'
                      ? 'bg-indigo-600 text-white'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                  }`}
                >
                  Page Coverage ({comparisonResult.page_coverage.length})
                </button>
              </div>

              {/* Sub-filters for Issues Tab */}
              {activeDetailTab === 'issues' && (
                <div className="flex items-center gap-1.5 text-xs">
                  <span className="text-slate-400 text-[11px] mr-1">Filter:</span>
                  {(['all', 'new', 'resolved', 'persistent', 'incomparable'] as const).map((filterKey) => (
                    <button
                      key={filterKey}
                      type="button"
                      onClick={() => setIssueFilter(filterKey)}
                      className={`px-2.5 py-1 rounded-md text-[11px] font-semibold transition-all ${
                        issueFilter === filterKey
                          ? 'bg-slate-700 text-white'
                          : 'text-slate-400 hover:text-slate-200 bg-slate-950/60'
                      }`}
                    >
                      {filterKey.toUpperCase()}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* TAB 1: Issue Changes */}
            {activeDetailTab === 'issues' && (
              <div className="space-y-3">
                {filteredIssues.length === 0 ? (
                  <p className="text-xs text-slate-400 py-6 text-center">
                    No issue findings match the selected filter.
                  </p>
                ) : (
                  <div className="space-y-2.5">
                    {filteredIssues.map((item, idx) => (
                      <div
                        key={idx}
                        className={`p-3.5 rounded-xl border text-xs space-y-2 transition-colors ${
                          item.change_type === 'new'
                            ? 'bg-rose-950/20 border-rose-900/50'
                            : item.change_type === 'resolved'
                            ? 'bg-emerald-950/20 border-emerald-900/50'
                            : item.change_type === 'persistent'
                            ? 'bg-amber-950/20 border-amber-900/50'
                            : 'bg-slate-950/40 border-slate-800'
                        }`}
                      >
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <span
                              className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${
                                item.change_type === 'new'
                                  ? 'bg-rose-950 text-rose-300 border-rose-700'
                                  : item.change_type === 'resolved'
                                  ? 'bg-emerald-950 text-emerald-300 border-emerald-700'
                                  : item.change_type === 'persistent'
                                  ? 'bg-amber-950 text-amber-300 border-amber-700'
                                  : 'bg-slate-800 text-slate-300 border-slate-700'
                              }`}
                            >
                              {item.change_type}
                            </span>
                            <span className="font-semibold text-slate-200">{item.rule_title}</span>
                            <span className="text-[10px] text-slate-400 font-mono">({item.rule_id})</span>
                          </div>

                          <span className="text-[10px] font-mono text-slate-400 truncate max-w-sm">
                            {item.page_url}
                          </span>
                        </div>

                        <p className="text-slate-300 text-[11px]">{item.explanation}</p>

                        {item.recommendation && (
                          <div className="p-2 rounded bg-slate-950/60 border border-slate-800/80 text-[11px] text-indigo-300">
                            <strong>Recommended Action:</strong> {item.recommendation}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* TAB 2: Metadata Changes */}
            {activeDetailTab === 'metadata' && (
              <div>
                {comparisonResult.metadata_changes.length === 0 ? (
                  <p className="text-xs text-slate-400 py-6 text-center">
                    No metadata differences detected across common pages.
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs border-collapse">
                      <thead>
                        <tr className="border-b border-slate-800 text-slate-400 text-[11px]">
                          <th className="py-2.5 px-3">Page URL</th>
                          <th className="py-2.5 px-3">Field</th>
                          <th className="py-2.5 px-3">Baseline Value</th>
                          <th className="py-2.5 px-3">Comparison Value</th>
                          <th className="py-2.5 px-3">Change Type</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60">
                        {comparisonResult.metadata_changes.map((m, idx) => (
                          <tr key={idx} className="hover:bg-slate-800/30">
                            <td className="py-2.5 px-3 font-mono text-[11px] text-slate-300 max-w-xs truncate">
                              {m.page_url}
                            </td>
                            <td className="py-2.5 px-3 font-semibold text-slate-200">
                              {m.field_name}
                            </td>
                            <td className="py-2.5 px-3 text-slate-400 max-w-xs truncate">
                              {m.baseline_value || <span className="text-slate-400 italic">None</span>}
                            </td>
                            <td className="py-2.5 px-3 text-indigo-300 max-w-xs truncate font-medium">
                              {m.comparison_value || <span className="text-slate-400 italic">None</span>}
                            </td>
                            <td className="py-2.5 px-3">
                              <span
                                className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${
                                  m.change_type === 'added'
                                    ? 'bg-emerald-950 text-emerald-300 border-emerald-800'
                                    : m.change_type === 'removed'
                                    ? 'bg-rose-950 text-rose-300 border-rose-800'
                                    : 'bg-sky-950 text-sky-300 border-sky-800'
                                }`}
                              >
                                {m.change_type}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

            {/* TAB 3: Page Coverage */}
            {activeDetailTab === 'coverage' && (
              <div>
                {comparisonResult.page_coverage.length === 0 ? (
                  <p className="text-xs text-slate-400 py-6 text-center">
                    No page coverage data available.
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs border-collapse">
                      <thead>
                        <tr className="border-b border-slate-800 text-slate-400 text-[11px]">
                          <th className="py-2.5 px-3">Page URL</th>
                          <th className="py-2.5 px-3">Coverage Status</th>
                          <th className="py-2.5 px-3">Baseline Run Status</th>
                          <th className="py-2.5 px-3">Comparison Run Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60">
                        {comparisonResult.page_coverage.map((p, idx) => (
                          <tr key={idx} className="hover:bg-slate-800/30">
                            <td className="py-2.5 px-3 font-mono text-[11px] text-slate-300">
                              {p.url}
                            </td>
                            <td className="py-2.5 px-3">
                              <span
                                className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${
                                  p.coverage_status === 'common'
                                    ? 'bg-slate-800 text-slate-300 border-slate-700'
                                    : p.coverage_status === 'new'
                                    ? 'bg-indigo-950 text-indigo-300 border-indigo-700'
                                    : 'bg-amber-950 text-amber-300 border-amber-700'
                                }`}
                              >
                                {p.coverage_status === 'missing_in_comparison'
                                  ? 'Not in Newer Run'
                                  : p.coverage_status}
                              </span>
                            </td>
                            <td className="py-2.5 px-3 text-slate-400 font-mono text-[11px]">
                              {p.baseline_page_status || '—'}
                            </td>
                            <td className="py-2.5 px-3 text-slate-400 font-mono text-[11px]">
                              {p.comparison_page_status || '—'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </div>
        </section>
      )}
    </div>
  );
}
