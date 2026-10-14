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

### Security Architecture & SSRF Defenses
- **Scheme Filtering**: Strictly restricts input to `http://` and `https://`.
- **Credentials Blocking**: Rejects embedded user/pass authentication in URLs.
- **Literal IP & Range Blacklisting**: Automatically rejects RFC 1918 private IPs (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), loopback (`127.0.0.0/8`, `::1`), link-local / cloud metadata services (`169.254.0.0/16`, `169.254.169.254`), and IPv6 ULA/multicast/reserved networks.
- **DNS Resolution Pre-flight**: Resolves hostnames to IP addresses prior to connecting, preventing DNS rebinding attacks to internal infrastructure.
- **Manual Redirects with Per-hop Re-validation**: Automatic redirects are disabled. Every redirect destination is re-validated through the full SSRF and IP filter before the next request is initiated.
- **Response Size Capping**: Streaming body reads strictly limit incoming responses to 2MB to prevent memory exhaustion / denial of service.
- **Time-Of-Check to Time-Of-Use (TOCTOU) Note**: In standard socket environments, there remains an inherent brief window between DNS resolution and socket connection. This is mitigated by per-hop redirect resolution checks and safe loopback server binding.

---

## Known Limitations of Current Implementation
- **Single-URL Scope**: Batch URL processing and sitemap (`sitemap.xml`) automated crawling are deferred to subsequent milestones.
- **No Database Persistence**: Runs execute in real-time memory without local SQLite history.
- **No Headless Browser**: Dynamic client-side JavaScript rendering (SPA hydration) and browser console error logging will be added in Milestone 4 via Playwright.

