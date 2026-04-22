## Context

The current implementation exercises the ingestion boundary using `LinkedInJsonFileAdapter`, which reads a local JSON fixture and returns canonical `JobRecord` instances. The goal of this change is to keep that same boundary and downstream flow (SQLite persistence + compass evaluation), while adding real LinkedIn acquisition.

Constraints and expectations for v1 acquisition:
- Human-in-the-loop job discovery only. No auto-apply and no outreach.
- Do not assume official LinkedIn API access.
- Scraping is acceptable; resilience to LinkedIn drift matters.
- Full job description text and the job link must be stored in SQLite.
- The professional compass is the only user-facing input; the system derives what to search for from the compass.

## Goals / Non-Goals

**Goals:**
- Implement a real LinkedIn acquisition mode behind the existing `JobSourceAdapter` boundary.
- Collect stable identifiers when available and always collect the canonical link and full description.
- Keep acquisition debuggable via structured diagnostics and optional raw capture storage under `data/` (gitignored).
- Support a configurable parsing/extraction model (JSON) so deterministic extraction logic can be changed without code edits.
- Provide an LLM-assisted fallback extraction path (local endpoint) when deterministic extraction cannot satisfy required canonical fields.
- Preserve fixture ingestion for offline debugging and tests.

**Non-Goals:**
- Browser automation (Playwright/Selenium) in this change.
- Multi-source ingestion beyond LinkedIn.
- Replacing the existing rule-based evaluator with LLM evaluation.
- Autonomous search expansion or background scheduling beyond a single CLI run.

## Decisions

### Keep adapter boundary; add a LinkedIn acquisition adapter

Decision: keep `JobSourceAdapter.fetch_jobs() -> list[JobRecord]` as the seam. Implement a new LinkedIn adapter that performs acquisition (HTTP + parsing) and returns canonical jobs, while retaining the existing JSON fixture adapter for tests.

Rationale:
- Minimizes impact on persistence and evaluation.
- Keeps a clean separation between acquisition mechanics and the ingestion pipeline.

Alternatives considered:
- Embed scraping in CLI directly. Rejected (breaks boundary).

### Two-stage acquisition: search results -> job details

Decision: acquisition is modeled as:
1. derive a small set of search queries from `ProfessionalCompass` (e.g., `target_roles` + remote preference)
2. fetch search results pages to collect job IDs/links
3. fetch job detail pages/endpoints to extract full descriptions

Rationale:
- Job detail pages are the stable place to get full descriptions.
- Allows incremental diagnostics and partial progress.

Alternatives considered:
- Only ingest search result cards (often incomplete). Rejected (must store full description).

### Compass-driven scope: time, workplace mode, region

Decision: extend the compass schema with a `search` section that controls acquisition scoping:
- `search.max_post_age_days`
- `search.workplace_types` (remote/hybrid/onsite)
- `search.regions` (US/LATAM/EMEA/AR)

Rationale:
- Keeps CLI simple and keeps user intent centralized in one local file.
- Makes acquisition runs repeatable without retyping flags.

Alternatives considered:
- Add CLI flags for each filter. Rejected (compass-only input is a project constraint).

### Store filter-relevant metadata in SQLite

Decision: extend storage to persist extracted `location_text`, `workplace_type`, and posting age signals (`post_age_text` and a normalized numeric age when possible).

Rationale:
- Allows downstream review and filtering without re-scraping.
- Supports later improvements to filtering without losing previously collected jobs.

### Extraction spec placement and overrides

Decision: keep a repo-owned default extraction template under `config/` and allow a user override under `profiles/` (gitignored).

Rationale:
- Defaults are discoverable and versioned with the repo.
- Overrides avoid committing site-specific tweaks.

### Parsing is driven by an explicit JSON extraction spec

Decision: introduce a JSON “extraction model” that describes how to extract required fields (id, company, title, description, link, posted time when available, salary text when available) from the acquired payload (HTML or JSON).

Rationale:
- LinkedIn markup/endpoints drift. Keeping extraction rules in data makes iteration faster.
- Enables future runtime edits by an LLM or human without code changes.

Alternatives considered:
- Hardcode CSS selectors/regex in code only. Rejected (slow iteration when LinkedIn changes).

### LLM-assisted fallback is a last resort, not the primary parser

Decision: deterministic extraction runs first; if required canonical fields cannot be produced, the adapter may invoke a locally configured LLM endpoint to attempt extraction from the raw payload.

Rationale:
- Keeps the happy path fast and predictable.
- Limits LLM usage to drift recovery, aligned with the spec.

Alternatives considered:
- LLM-first extraction always. Rejected (cost/latency and harder to debug).

### Secrets handling: local-only and gitignored

Decision: authenticated scraping (cookies/CSRF) is supported via local-only configuration (env vars or a gitignored file). Raw captures go under `data/` (gitignored).

Rationale:
- Avoids committing credentials.
- Keeps reproduction possible without leaking tokens.

## Risks / Trade-offs

- [LinkedIn blocks unauthenticated scraping or rate limits aggressively] -> Mitigation: optional authenticated mode and conservative request pacing; keep fixture ingestion for offline workflows.
- [Payload drift breaks deterministic extraction] -> Mitigation: configurable extraction spec + raw capture persistence + LLM fallback extraction.
- [LLM fallback introduces nondeterminism] -> Mitigation: only use when required fields are missing; record extraction mode and keep raw payload for review.
- [“Compass-only input” produces noisy searches] -> Mitigation: cap queries/pages per run, emit diagnostics for tuning, and make query derivation explicit.

## Migration Plan

- Add new acquisition mode while retaining fixture ingestion for tests.
- Evolve SQLite schema additively to store location/workplace mode/post age signals without requiring DB recreation.
- If rolling back, disable/remove acquisition mode; existing SQLite DB remains valid.

## Open Questions

- What is the initial supported acquisition substrate: HTML pages only, or a specific internal JSON endpoint when available?
- What should the extraction spec look like (regex-first vs selector-first vs both), and where should it live (e.g., `profiles/linkedin_extraction.json` vs `opensignal_job_intel/resources/`)?
- What is the expected local LLM API contract for `llama-server` (OpenAI-compatible `/v1/chat/completions` vs llama.cpp `/completion`), and do we need streaming?
