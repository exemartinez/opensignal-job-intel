## Context

The repo currently supports acquisition + ingestion for LinkedIn and Indeed through a consistent surface:

- a `JobSourceAdapter` implementation per source (fixture + live)
- normalization into canonical `JobRecord`
- optional compass-based filters (age/workplace/region) applied without mutating fields that were not extracted
- persistence through `SQLiteJobRepository` keyed by `dedupe_key`
- CLI wiring in `main.py` and `src/runtime_entrypoints.py`

We are adding Wellfound as an additional source while keeping these boundaries intact and avoiding a one-off flow.

Constraints:
- Network/DNS can be unreliable in some environments; fixture mode must remain first-class for tests.
- We should prefer reusing the existing live-transport approach (Selenium) when needed (already used for Indeed), rather than introducing a second browser stack.

## Goals / Non-Goals

**Goals:**
- Add Wellfound acquisition with both live scraping and fixture ingestion.
- Normalize Wellfound postings into the existing canonical `JobRecord` and persist into the existing SQLite schema.
- Preserve current ingestion semantics for LinkedIn and Indeed.
- Add focused test coverage for Wellfound parsing/normalization, URL canonicalization, filtering, and CLI wiring.

**Non-Goals:**
- No schema changes to SQLite in this change.
- No refactor of existing LinkedIn/Indeed acquisition beyond the minimal shared helpers needed for Wellfound.
- No attempt to guarantee `post_datetime` for Wellfound when it cannot be reliably extracted; do not backfill with `collected_at`.

## Decisions

1. **Adapter structure mirrors existing sources**
   - Decision: Implement `WellfoundScrapeAdapter` (live) and `WellfoundJsonFileAdapter` (fixture) under `src/wellfound_acquisition.py`.
   - Rationale: Keeps the “strategy per source” pattern consistent and makes CLI wiring/tests straightforward.

2. **Transport: reuse Selenium when dynamic rendering is required**
   - Decision: Prefer Selenium for Wellfound live acquisition if HTML requires JS execution.
   - Rationale: Indeed already uses Selenium in this repo; reuse reduces operational complexity.

3. **Age filtering happens at acquisition/filter policy, not by mutating timestamps**
   - Decision: Apply tenure filtering via source-native search parameters when available; otherwise apply best-effort filter only when the source provides an explicit “age” signal.
   - Rationale: Avoid inventing timestamps and keep `post_datetime` semantics trustworthy.

4. **Dedup keys follow the existing policy**
   - Decision: Use `source + external_job_id` when Wellfound provides a stable id; otherwise use normalized link.
   - Rationale: Aligns with existing persistence behavior and prevents double inserts.

## Risks / Trade-offs

- **[Wellfound markup/JS changes]** → Mitigation: keep selectors isolated in the adapter and add fixture-based regression tests with captured HTML/JSON.
- **[Anti-bot / throttling / blocking]** → Mitigation: keep pacing controls, allow cookie injection via environment variables, and support fixture mode for development.
- **[Missing post date]** → Mitigation: keep `post_datetime=None` unless extracted; rely on search filters and/or `post_age_*` when present.
