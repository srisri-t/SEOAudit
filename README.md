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

## Known Limitations of Current Implementation
- **Batch Auditing Decoupled**: Sitemap discovery extracts and previews URLs; batch auditing of all discovered URLs is planned for a subsequent milestone.
- **No Database Persistence**: Sitemaps and audit results run in real-time memory without local SQLite persistence.
- **TOCTOU DNS Rebinding Window**: Standard Python socket environments have a microsecond window between DNS pre-flight verification and connection establishment.
- **No Headless Browser**: Dynamic client-side JavaScript rendering (SPA hydration) will be added in Milestone 4 via Playwright.


