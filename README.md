# Universal SEO Automation & Maintenance Platform

## Project Purpose
The **Universal SEO Automation & Maintenance Platform** is an independent, local-first technical SEO auditing and maintenance application. It audits web properties, monitors technical health, maintains historical execution logs, and exports structured reports formatted specifically for developers and AI assistants (such as ChatGPT and Antigravity).

While its first testing target is [Holy Space](https://www.holyspace.live), this platform is engineered completely decoupled and independent from any target website source code.

---

## Workspace Structure
```text
SEOAudit/
├── .claude/                                      # Preserved IDE configuration (ignored by git)
│   └── settings.json
├── Universal_SEO_Platform_Project_Handover.md   # Architectural charter & specifications
├── .gitignore                                   # Standard ignores (.venv, node_modules, secrets, artifacts)
├── README.md                                    # This project documentation and local runbook
├── backend/                                     # Python 3.13 / FastAPI service
│   ├── .venv/                                   # Dedicated Python virtual environment (ignored)
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                              # FastAPI application entrypoint (loopback binding)
│   │   └── api/
│   │       ├── __init__.py
│   │       └── health.py                        # GET /api/health endpoint & response schema
│   ├── tests/
│   │   ├── __init__.py
│   │   └── test_health.py                       # Automated test suite using FastAPI TestClient
│   ├── pytest.ini                               # Pytest configuration
│   └── requirements.txt                         # Minimal production & test dependencies
└── frontend/                                    # React 19 + TypeScript + Tailwind CSS UI
    ├── package.json
    ├── vite.config.ts                           # Vite configuration with Tailwind & /api proxy
    ├── index.html
    └── src/
        ├── App.tsx                              # Foundation dashboard & connection indicator
        ├── index.css                            # Base stylesheet with Tailwind CSS
        └── services/
            └── api.ts                           # API client with health check logic
```

---

## Prerequisites
- **Python**: Version `3.13.4` (or 3.11+)
- **Node.js**: Version `22.23.2` (or 20+)
- **npm**: Version `10.9.8`
- **Git**: Version `2.45.1`

---

## Backend Environment Setup

### 1. Create Virtual Environment (if not already created)
From the project root:
```powershell
python -m venv backend/.venv
```

### 2. Activate Virtual Environment & Install Dependencies
```powershell
.\backend\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
```

### 3. Run Automated Tests
```powershell
cd backend
.\.venv\Scripts\pytest.exe -v
```

### 4. Start Backend Server
> **IMPORTANT SECURITY NOTE:** During local development, the development server **must bind exclusively to loopback (`127.0.0.1`)**, never `0.0.0.0`. This prevents exposing internal endpoints across untrusted local networks.

```powershell
cd backend
.\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000 --reload
```
- API Health Endpoint: `http://127.0.0.1:8000/api/health`
- Single-URL Audit Endpoint: `POST http://127.0.0.1:8000/api/audits/url`
- Sitemap Discovery Endpoint: `POST http://127.0.0.1:8000/api/sitemaps/discover`
- Interactive OpenAPI / Swagger UI: `http://127.0.0.1:8000/docs`

---

## Frontend Setup & Startup Commands

### 1. Install Dependencies
```powershell
cd frontend
npm install
```

### 2. Start Development Server
```powershell
cd frontend
npm run dev
```
The application will launch on `http://localhost:5173`.

### 3. Verify Production Build
```powershell
cd frontend
npm run build
```

---

## Technical SEO Audit Engine & Security Architecture

### Technical SEO Checks (8 Rules)
1. **HTTP Response Status (`http-status`)**: Verifies HTTP 200 OK delivery; flags 3xx redirects, 4xx client errors, and 5xx server faults.
2. **Redirect Behavior & Final URL (`redirect-chain`)**: Follows redirects manually; alerts on redirect chains (>1 hop) or temporary 302/307 redirects.
3. **Page Title Presence & Length (`page-title`)**: Checks `<title>` presence, whitespace-only titles, multiple title tags, and length thresholds (15-65 chars recommended).
4. **Meta Description Presence & Length (`meta-description`)**: Checks `<meta name="description">`, multiple tags, and recommended length (50-160 chars).
5. **Canonical URL Presence & Validity (`canonical-url`)**: Checks `<link rel="canonical">`, resolving relative paths, validating self-referential status vs external canonicals.
6. **Meta Robots Indexing Directives (`meta-robots`)**: Detects `noindex` or `none` directives blocking search engine indexing.
7. **X-Robots-Tag Header Directives (`x-robots-tag`)**: Detects `noindex` or `none` directives in HTTP response headers.
8. **Content-Type & HTML Validity (`content-type`)**: Verifies `text/html` or `application/xhtml+xml` MIME types.

---

## Milestone 3: Sitemap Discovery & XML Parsing

### Discovery Workflow
The platform offers a multi-strategy discovery engine:
1. **Robots.txt Inspection**: Queries `/robots.txt` for `Sitemap:` directives and extracts candidate URLs.
2. **Standard Fallback**: If no sitemaps are declared in `robots.txt` (or robots.txt is 404), falls back to testing standard candidate `/sitemap.xml`.
3. **Explicit Sitemap URL**: Allows users to specify a direct sitemap URL (e.g. `https://example.com/sitemap_index.xml`), bypassing discovery.
4. **Sitemap Index Recursion**: Automatically recurses into child sitemaps with strict depth and count limits.

### Supported Sitemap Formats
- Standard XML URL sets (`<urlset><url><loc>...</loc></url></urlset>`)
- Namespaced XML (e.g. `http://www.sitemaps.org/schemas/sitemap/0.9`, Google Image/Video/News extensions)
- Sitemap index files (`<sitemapindex><sitemap><loc>...</loc></sitemap></sitemapindex>`)

### Configurable Limits & Thresholds
- **Maximum Discovered URLs (`max_urls`)**: Default `1,000`, hard maximum `10,000`. Unlimited discovery requests are rejected.
- **Maximum Child Sitemaps**: Default `50` child sitemaps per index.
- **Index Recursion Depth**: Capped at `1 level` (a sitemap index cannot contain nested sitemap indexes).
- **Download Size Limit**: `5 MB` per sitemap file; oversized downloads are aborted.
- **Processing Timeout**: Overall run timeout of `30 seconds`.

### Security Protections
- **XML External Entity (XXE) & DTD Bomb Protection**: Built with `defusedxml` to block entity expansion, billion-laughs attacks, and external DTD injection.
- **SSRF Defense-in-Depth**: Every target URL, robots.txt directive, and child sitemap URL in an index is validated against SSRF before requests are issued. Prohibits RFC 1918 private IPs, loopback, link-local / cloud metadata (e.g. `169.254.169.254`), and multicast.
- **Per-Hop Redirect Re-Validation**: Prevents open redirect SSRF attacks.
- **No Credential Leakage**: Never forwards browser cookies or auth tokens to target destinations.

### API Specifications: `POST /api/sitemaps/discover`

#### Example Request:
```json
{
  "website_url": "https://example.com/",
  "sitemap_url": null,
  "max_urls": 1000
}
```

#### Example Response:
```json
{
  "website_url": "https://example.com/",
  "sitemap_status": "Sitemap found",
  "discovered_sitemaps": [
    "https://example.com/sitemap.xml"
  ],
  "discovered_url_count": 2,
  "urls": [
    "https://example.com/page1",
    "https://example.com/page2"
  ],
  "warnings": [],
  "errors": [],
  "processing_duration_ms": 142.5
}
```

#### Discovery Status Values:
- `Sitemap found`: Valid sitemap discovered and parsed successfully.
- `Sitemap not found`: Neither `robots.txt` nor `/sitemap.xml` yielded an accessible sitemap (e.g. HTTP 404).
- `Sitemap inaccessible`: Network timeout, connection refused, or 5xx server error.
- `Invalid sitemap`: Document was fetched (HTTP 200) but was corrupted XML, HTML error page, empty, or contained no valid URLs.
- `Discovery blocked by security validation`: Destination or child sitemap attempted access to a prohibited IP/host.

---

## Milestone 4: Playwright Browser-Based SEO Auditing

Milestone 4 introduces dynamic browser-rendered SEO checks powered by headless Chromium via Playwright, complementing the fast HTTPX static engine.

### Key Capabilities
- **DOM Hydration Extraction**: Extracts live rendered `<title>`, `<meta name="description">`, `<link rel="canonical">`, and `<meta name="robots">`.
- **Hydration Drift Detection**: Compares server-delivered HTML with client-rendered DOM to detect discrepancy in titles, meta descriptions, canonical links, and dynamically injected `noindex` directives.
- **JavaScript & Console Diagnostics**: Captures unhandled runtime page exceptions (`pageerror`), console errors, and failed subresources.
- **Dedicated & Combined Endpoints**:
  - `POST /api/audits/url` with `"include_browser": true` (runs HTTPX audit + browser audit in one unified response).
  - `POST /api/audits/browser` (dedicated direct browser audit).

### Browser Installation (Windows / Local Machine)
To enable browser rendering locally, install Chromium:
```powershell
.\backend\.venv\Scripts\python.exe -m playwright install chromium
```
*(Only Chromium is downloaded, minimizing memory and disk footprint for 16 GB RAM laptops with no dedicated GPU).*

### Subresource SSRF Security & Resource Boundaries
- **Route Interception (`context.route("**/*")`)**: Every top-level and subresource network request (scripts, stylesheets, images, fonts, iframes, fetch/XHR) is intercepted before dispatch. Prohibits loopback (`127.0.0.1`, `::1`), RFC 1918 private networks, link-local / cloud metadata (`169.254.169.254`, `fe80::/10`), IPv4-mapped IPv6 ranges, and unsafe URL schemes (`file:`, `chrome:`, `javascript:`, `about:`). Safe inline data URIs (`data:image/`, `data:font/`) are permitted.
- **Operating System Sandboxing**: Native OS process sandboxing is preserved and kept active on Windows (omitting `--no-sandbox`).
- **Feature Restrictions**: Downloads disabled (`accept_downloads=False`), permissions cleared (`permissions=[]`), and service workers blocked (`service_workers="block"`) to prevent persistent background caching or out-of-band requests.
- **Popup & Redirect Control**: Auxiliary pages and popups created via `window.open` are automatically closed. Client-side frame navigations (`framenavigated`) to prohibited destination IPs trigger immediate page termination.
- **Bounded Concurrency & Memory**: Uses an `asyncio.Semaphore(1)` to limit concurrent browser instances, ensuring safe operation on 16 GB RAM laptops with no dedicated GPU.
- **Bounded Diagnostic Storage**: Caps console errors (max 50), page exceptions (max 20), and failed subresources (max 50), truncating excessive string lengths to prevent memory bloat from malicious loops.
- **Deterministic Process Teardown**: Chromium process and context lifecycles are wrapped in strict `try ... finally` blocks to ensure cleanup under all outcomes (success, timeout, navigation error, or cancellation).
- **Graceful Browser Unavailable Fallback**: When Chromium is not installed, `/api/audits/url` with `include_browser=true` returns the complete static HTTPX audit with an advisory finding rather than failing the audit; `/api/audits/browser` returns a clean `503 Service Unavailable`.

---

## Milestone 5: Batch Auditing & Export Engine

Milestone 5 transforms the single-URL SEO auditor into a local-first website auditing platform. It audits multiple URLs concurrently, persists execution history in SQLite, calculates website-wide aggregate findings, and exports reports for developers and AI assistants.

### Key Capabilities
- **Batch Orchestration**: Accepts direct lists of URLs or auto-discovers URLs from sitemaps, deduplicating while preserving input ordering.
- **Bounded Concurrency & Timeouts**: Runs asynchronous workers with bounded concurrency (`asyncio.Semaphore`, configurable from 1 to 10, default 3) and execution timeouts (per-page and per-run).
- **Failure Isolation**: An individual URL failure (e.g. 502 Bad Gateway, network timeout, SSL error) is isolated and recorded as a failed page without crashing or stopping the rest of the batch.
- **Cooperative Cancellation**: Active batch runs can be cancelled at runtime; in-flight tasks finish safely, remaining pages are marked as skipped, and the run status transitions to `cancelled`.
- **Local SQLite Persistence**: Uses standard library `sqlite3` configured with WAL (Write-Ahead Logging) mode, synchronous `NORMAL`, foreign key enforcement, and a 5-second busy timeout. Preserves run history across server restarts in `data/seo_audit.db` (gitignored).
- **Website-Wide SEO Analysis**:
  - **Duplicate Title Detection**: Normalizes whitespace and groups pages sharing identical titles.
  - **Duplicate Description Detection**: Identifies duplicate meta descriptions across distinct URLs.
  - **Missing Metadata Counters**: Accurately counts missing titles and missing meta descriptions.
  - **HTTP Status Code Breakdown**: Aggregates distribution across 2xx, 3xx, 4xx, 5xx, and network errors.
  - **Internal Link Health Verification**: Checks outgoing `<a href>` links within the audited domain scope without uncontrolled external crawling. Clearly separates confirmed broken links (target audited and returned >= 400 or failed) from unverified links (target outside the audited batch limit).
- **Multi-Format Report Exports**:
  - **JSON**: Complete serialized run configuration, aggregate metrics, and per-page audit findings.
  - **CSV (with Formula Injection Mitigation)**: Tabular per-page results. Cells starting with dangerous spreadsheet formula characters (`=`, `+`, `-`, `@`, `\t`, `\r`) are automatically prefixed with a single quote (`'`) to neutralize CSV injection / DDE attacks.
  - **Markdown**: Formatted executive report with summary tables, severity counts, duplicate content groups, and broken link listings.

---

### Batch Audit API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/batch-audits` | Create and trigger an asynchronous batch audit run |
| `GET` | `/api/batch-audits` | List recent batch audit runs (supports pagination: `limit`, `offset`) |
| `GET` | `/api/batch-audits/{run_id}` | Retrieve run status, progress counts, and summary |
| `GET` | `/api/batch-audits/{run_id}/pages` | Retrieve paginated page results (filterable by `status=success\|failed\|skipped`) |
| `GET` | `/api/batch-audits/{run_id}/summary` | Retrieve aggregate SEO summary and duplicate content analysis |
| `POST` | `/api/batch-audits/{run_id}/cancel` | Cooperatively cancel an active batch audit |
| `GET` | `/api/batch-audits/{run_id}/export` | Export report as `json`, `csv`, or `markdown` (query param `format`) |

#### Example: Create Batch Audit Request
```json
POST /api/batch-audits
{
  "urls": [
    "https://www.holyspace.live",
    "https://www.holyspace.live/about",
    "https://www.holyspace.live/terms"
  ],
  "config": {
    "max_pages": 25,
    "concurrency": 3,
    "page_timeout_seconds": 15.0,
    "include_browser": false
  }
}
```

#### Example: Export Report
```text
GET /api/batch-audits/{run_id}/export?format=csv
Content-Disposition: attachment; filename="seo_audit_{run_id}.csv"
```

---

---

### Milestone 6.1: Audit Run Comparison

The **Audit Run Comparison** engine compares two existing, persisted batch audit runs to evaluate how a website's technical SEO posture has progressed over time.

#### Core Capabilities:
- **Baseline vs. Comparison Semantics**:
  - **Baseline Run**: The older or reference audit run.
  - **Comparison Run**: The newer audit run being evaluated against the baseline.
  - Answers: *"Compared with the baseline, what new issues emerged, what was resolved, and what metadata changed?"*
- **Issue Classification & Fingerprinting**:
  - **New Issues**: SEO findings present in the newer run but absent in the baseline.
  - **Resolved Issues**: Issues present in the baseline that were verified as passing in the newer run on successfully audited pages.
  - **Persistent Issues**: Issues present across both audit runs.
  - **Incomparable Findings**: Issues that cannot be verified as resolved because a page failed to load or was not included due to partial run coverage. The engine strictly avoids false positives by never assuming an issue is resolved when coverage is incomplete.
- **Page Coverage Differencing**:
  - Distinguishes **Common pages**, **Newly discovered pages**, and **Pages not present in the newer audit** (safely distinguished from deletion).
- **SEO Metadata Tracking**:
  - Compares `<title>`, `<meta name="description">`, canonical links, and HTTP status codes, categorizing changes as `added`, `removed`, or `changed`.
- **Evidence-Based Overall Assessment**:
  - Categorizes overall trajectory as `Improved`, `Deteriorated`, `Mixed Changes`, `No Detected Changes`, or `Incomplete Comparison`, with a concise explanation of the underlying metrics.
- **Report Exports**:
  - Downloadable comparisons in formatted **JSON** or sanitized **Markdown** (with table cell pipe character escaping).

#### Comparison API Endpoints:

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/batch-audits/compare` | Compare two runs: `{"baseline_run_id": "...", "comparison_run_id": "..."}` |
| `GET` | `/api/batch-audits/compare/export` | Download comparison report (`?baseline_run_id=...&comparison_run_id=...&format=json\|markdown`) |

#### Running Tests:
```powershell
# Run comparison engine and API test suites
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_comparison_engine.py backend/tests/test_comparison_api.py -v

# Run full backend regression suite (190 passed)
backend\.venv\Scripts\python.exe -m pytest backend/ -q

# Run frontend production build
npm run --prefix frontend build
```

---

## Known Limitations & Production Recommendations
- **In-Process Background Tasks**: The batch orchestrator currently manages concurrency in-process using Python's `asyncio` event loop and SQLite. This is ideal for lightweight, local-first deployments. If deploying to a distributed, multi-server cloud environment, migrating the background runner to a durable distributed worker (e.g. Celery / RQ) with Redis/PostgreSQL is recommended.
- **TOCTOU DNS Rebinding Window**: Pre-flight URL validation checks host IP addresses against loopback, RFC 1918, link-local, and cloud metadata ranges before HTTP request dispatch. In standard host OS environments without network-level egress proxies, an inherent microsecond Time-Of-Check to Time-Of-Use (TOCTOU) window exists if an attacker controls a public DNS server configured for sub-millisecond DNS rebinding. For enterprise production deployments, configure operating system firewall egress rules or an egress filtering proxy.
- **Browser Memory Utilization**: Running Playwright Chromium rendering on batch audits consumes significantly higher CPU/memory than standard HTTPX static auditing. Concurrency for browser-enabled audits should be constrained to 1–2 workers on resource-constrained environments.
- **Scope Compatibility**: Comparisons require both runs to target the same website origin (`target_origin`). Runs targeting disparate domains are safely rejected with HTTP 400.
