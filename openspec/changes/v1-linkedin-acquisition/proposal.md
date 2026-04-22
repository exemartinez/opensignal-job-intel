## Why

The current LinkedIn adapter is fixture-backed, which blocks the project from collecting fresh real-world job postings into the existing canonical ingestion, SQLite storage, and evaluation flow. This change implements pragmatic LinkedIn acquisition behind the existing adapter boundary so the system becomes usable for ongoing human-in-the-loop job discovery without assuming official API access.

## What Changes

- Replace the v1 fixture-only LinkedIn ingestion behavior with real acquisition that scrapes LinkedIn job search results and job detail pages to collect full job descriptions, links, and stable identifiers when available.
- Keep the existing canonical `JobRecord` model, SQLite repository, and rule-based compass evaluation flow intact.
- Make acquisition debuggable: emit structured diagnostics (request counts, parse failures, drop reasons) and optionally persist raw HTML/JSON captures locally under `data/` (gitignored) for reproduction.
- Support optional authenticated scraping via user-supplied session cookies/CSRF (local-only) when guest-mode access is insufficient.
- Introduce a configurable extraction/parsing model (JSON) for mapping LinkedIn responses/pages into canonical fields, with validation and an LLM-assisted fallback path when the deterministic parser fails due to LinkedIn changes.
- Use the professional compass as the only user-facing input; the system derives search queries/targets from the compass rather than requiring the user to paste a LinkedIn search URL.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `job-source-ingestion`: change LinkedIn ingestion from fixture-backed stub to real acquisition (scraping), add acquisition diagnostics, add configurable parsing/extraction spec + validation, and allow an LLM-assisted fallback when source payloads drift.

## Impact

- Affected code: `opensignal_job_intel/sources/linkedin.py` (acquisition + parsing), `opensignal_job_intel/cli.py` (ingestion command wiring and configuration), and possibly `opensignal_job_intel/services.py` (diagnostic reporting) while keeping repository/evaluator contracts stable.
- Data: more complete canonical records (full descriptions) stored in SQLite; optional raw capture files stored locally under `data/` (untracked).
- Security: authenticated scraping requires local-only handling of cookies/CSRF (via env vars or local config files that are gitignored).
- Dependencies: prefer Python standard library for HTTP where feasible; add third-party HTTP/HTML parsing only if necessary for reliability.
