# Universal SEO Automation Platform — Project Handover

## Purpose
Use this document to continue the project in a new ChatGPT session or AI IDE. The goal is to build a simple, useful local-first SEO audit web app that can grow into a larger product. Do not restart product discovery from scratch.

## 1. Product vision
Build an independent **Universal SEO Automation & Maintenance Platform** that audits websites, shows execution progress and findings, and exports AI-friendly reports users can share with ChatGPT, Antigravity, or another AI coding assistant.

First target: **Holy Space** (`https://www.holyspace.live`). The platform must remain independent of the Holy Space application/repository and later support unrelated websites and client projects.

Long-term, this may become a professional/commercial product for technical SEO audits, maintenance checks, repeat audits, and client reporting. For now, optimize for the smallest version that is genuinely useful.

## 2. Core workflow
1. Open the local web app.
2. Log in with username/email and password.
3. View a dashboard.
4. Enter a website URL or import its sitemap.
5. Choose SEO checks and start an audit.
6. Watch live progress and see URLs processed/remaining.
7. Review PASS/FAIL/WARNING/ERROR results, search/filter them, and inspect evidence.
8. Export reports for normal review or AI handoff.
9. Save execution history locally.

The UI is a control panel; the audit engine initially runs on the user's own computer.

## 3. First-version scope

### Must have
- Local web UI with login.
- Dashboard counts for discovered, attempted, completed, skipped, remaining, passed, failed, warnings, and errors.
- Website URL input and sitemap import.
- Initial HTTP-based SEO checks.
- Background execution that does not block the UI.
- Live or frequently refreshed progress.
- Results table with search/filter and finding details.
- Local execution history.
- Export **JSON, Markdown, and CSV**.
- AI-ready audit summary and prompt for ChatGPT/AI IDE handoff.
- Automated tests for the app and checks.

### Add after the first working version
- Playwright browser checks for selected pages: rendered content, browser console errors, JavaScript-dependent metadata, and desktop/mobile viewport checks.
- AI handoff ZIP containing `README.md`, `audit-summary.md`, `audit-results.json`, `issues.csv`, `affected-urls.csv`, `recommendations.md`, and `ai-analysis-prompt.md`.
- Before/after audit comparison.
- Failed-URL reruns and filtered exports if not in the first pass.

### Future, not MVP
- Multiple users/client accounts.
- Public hosted SaaS and registration.
- Scheduled recurring audits.
- Official Google Search Console API integration.
- Physical Android testing/local device agent.
- Billing/subscriptions.
- Direct AI integration and automatic code modifications.
- Backlink/keyword research or broad AI-agent features.

Do not make the MVP depend on paid cloud or browser services.

## 4. Recommended technology
- Frontend: **React + TypeScript + Tailwind CSS**.
- Backend API: **Python + FastAPI**.
- HTTP audit engine: **HTTPX + BeautifulSoup**.
- Browser checks later: **Playwright for Python**.
- Tests: **pytest**.
- Initial persistence: **SQLite and/or organized local files**.
- Execution: a local background worker or simple background task with job status.

Keep it straightforward. PostgreSQL, Redis, Celery, distributed workers, and complex job infrastructure are not required at the start. Introduce them only when real needs justify them. Use reusable validation functions/data-driven checks; do not force BDD/Cucumber into the engine merely because the product owner has prior Selenium/Cucumber experience.

## 5. Initial SEO checks
Start with objectively verifiable technical checks:
- HTTP status code and request failures.
- Redirect behavior and final URL.
- Missing/empty page title.
- Missing/empty meta description.
- Canonical link presence/value.
- Robots directives, including detectable `noindex`.
- Sitemap accessibility and URL extraction.
- Duplicate titles/metadata once enough pages have been collected.
- Response timing as a diagnostic metric, not an automatic ranking verdict.

Browser-based checks can follow for JavaScript-rendered content and console errors.

For every check, record whether it was actually performed. Do not label untested conditions PASS. Use WARNING for advisory findings/human judgment and ERROR for execution/tool failures. Passing checks does **not** guarantee search ranking improvement.

## 6. AI-ready export — important product differentiator
Reports should be understandable by AI coding assistants, not merely lists of errors.

### Early formats
1. JSON for structured data and automation.
2. Markdown for ChatGPT and developers.
3. CSV for spreadsheets.

### Suggested finding fields
- `issue_id`
- `category`
- `severity`
- `status`
- `url`
- `check_name`
- `expected`
- `actual`
- `evidence`
- `recommendation`
- `timestamp`
- Tool version and audit/run ID where appropriate.

The audit summary should include website/origin, run ID, start/end/duration, tool version, discovered/attempted/completed/skipped/remaining URLs, PASS/FAIL/WARNING/ERROR counts, checks executed/skipped, and coverage limitations.

Group repeated issue descriptions by issue type when helpful, retaining affected URLs and counts. Keep exports manageable for large sites and support filtered/summary exports when needed.

### Generated AI handoff prompt
Ask the AI assistant to:
1. Analyze the report and identify likely root causes.
2. Inspect actual project source code before proposing changes.
3. Separate confirmed findings from hypotheses.
4. Prioritize fixes by impact and effort.
5. Propose minimal, safe changes.
6. Preserve existing functionality and avoid unrelated refactoring.
7. Run relevant tests/build checks after changes.
8. Report changes and which findings were re-tested.

The report alone cannot prove the root cause in source code. The AI assistant should inspect the project code. Do not claim a code change fixed an issue until the relevant audit is rerun and passes.

### Export safety
Never export passwords, tokens, cookies, environment variables, API secrets, or unnecessary personal/sensitive page content. Tell users to review reports before external sharing. Do not bundle source code by default.

## 7. Local-first security
- Keep the first version local-only; bind the backend to loopback/localhost and do not expose it publicly.
- A login screen is not a substitute for secure authentication. Use an appropriate password hash and safe session/token handling; do not hardcode credentials or store plaintext passwords.
- Before accepting public/untrusted users, harden against SSRF: block localhost/private/link-local/cloud metadata destinations, validate DNS/connections, and revalidate redirects. Limit schemes to HTTP/HTTPS.
- Use request timeouts, concurrency caps, URL/page limits, response-size limits, and robust error handling.
- Do not expose secrets in frontend bundles or logs.
- Do not deploy publicly or add public registration before authentication, authorization, SSRF protection, resource limits, and tenant isolation are reviewed.
- Respect website robots/access policies and use conservative request rates. Automated visits do not improve search rankings or Search Console impressions.

## 8. Performance and hardware
The user has a Windows laptop with 16 GB RAM and no dedicated graphics card. Keep the tool practical on this machine. Use HTTP checks for most URLs and browser automation only where it adds value. Do not open thousands of browser tabs. Concurrency/timeouts should be configurable and measured on a representative batch before full-catalog runs.

Holy Space has roughly **3,773 song URLs**, so sitemap and large-batch handling matter. Do not assume every page needs a browser.

## 9. Suggested implementation milestones

### Milestone 0 — Inspect and confirm
- Check whether a dedicated folder/repository already exists.
- Inspect files and Git status; preserve existing work.
- Keep this independent from Holy Space.
- Summarize the structure and plan briefly.
- Do not run destructive cleanup.

### Milestone 1 — Foundation and UI
- Set up frontend/backend connection and local run instructions.
- Build login screen and dashboard shell.
- Implement a small real vertical slice, not just static mockups.
- Add configuration and basic tests.

### Milestone 2 — Working HTTP audit engine
- Accept URL and/or sitemap.
- Parse/validate URLs.
- Run initial SEO checks.
- Handle individual URL errors without aborting the whole batch.
- Store structured findings and audit status.

### Milestone 3 — Progress, results, history and exports
- Show progress/counts.
- Display/search/filter findings.
- Save audit history.
- Export JSON, Markdown, CSV.
- Generate AI-ready summary and handoff prompt.
- Test exports and their schemas.

### Milestone 4 — Browser checks
- Add Playwright checks for selected URLs.
- Add viewport/device simulation only; explain that emulation is not a physical-device test.
- Do not claim genuine iPhone Safari testing from Windows unless a supported real environment is configured.

### Milestone 5 — Hardening and usability
- Test failures, timeouts, cancellation if supported, large sitemap batches, reruns, and export edge cases.
- Review local authentication, SSRF protections, resource limits, and secret handling.
- Improve the interface and documentation.

Later: ZIP handoff bundle, before/after comparison, scheduled jobs, GSC integration, multi-user accounts and public hosting after security review.

## 10. Working rules for the next ChatGPT session / AI IDE
1. Work incrementally, one milestone at a time.
2. First inspect the current workspace/repository; do not assume it is empty.
3. Do not mix code into the Holy Space repository.
4. Do not overwrite/delete existing user work.
5. No commit, push, deployment, paid services, or cloud resource creation without explicit approval.
6. Do not claim a test passed unless actually executed; report command and real result.
7. Distinguish verified facts, assumptions, and proposed behavior.
8. Keep it simple but maintain clean module boundaries.
9. Prefer free/local tools initially.
10. Do not build every future feature before the core workflow works end-to-end.
11. Provide concise updates: files changed, behavior added, tests/results, next step.
12. If a choice can safely be deferred, choose a simple default and document it rather than blocking on many questions.

## 11. Immediate instruction
**Begin with Milestone 0.** Inspect the current workspace/repository and determine whether the SEO project folder already exists. If it exists, inspect and preserve it. If not, propose a clean standalone structure. Then begin the first small implementation milestone.

First demonstrable goal:

> A local app that opens in a browser, provides a login flow, accepts a website URL or sitemap, runs real basic SEO checks, displays live execution progress and findings, saves the run locally, and exports JSON/Markdown/CSV that the user can hand to ChatGPT or an AI IDE.

Do not deploy or build the full SaaS yet.
