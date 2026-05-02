## Context

The current CLI supports LinkedIn ingestion in fixture mode and live acquisition mode. It can store canonical jobs in SQLite and apply best-effort filters driven by the professional compass. The next step is to operate the system as a nightly “job farmer” that can run for hours, accumulate a large local corpus over months, and minimize the risk of throttling by reducing unnecessary requests and backing off under HTTP 403.

Key constraints:
- Local-first: SQLite remains the primary store.
- Human-in-the-loop: the system collects and scores; no auto-apply.
- LinkedIn acquisition is scraping-based and drift-prone; runs must be debuggable.
- Harvest runs must be incremental/idempotent: do not refetch details for jobs already stored.

## Goals / Non-Goals

**Goals:**
- Add a dedicated harvest orchestrator intended for unattended nightly runs.
- Read harvest runtime controls from a schedule config file (`config/extraction_schedule.yaml`).
- Reuse professional-compass roles as the query source for harvesting.
- Keep repo-owned operational entrypoints for installing/removing cron, running a guarded harvest, and inspecting logs/status alongside the LinkedIn source implementation in Python.
- Enforce compass-driven constraints for harvesting while stopping early once the result stream is clearly older than the recency window.
- Support Canada alongside the existing US, LATAM, EMEA, and AR regional query/filter labels, using `CANADA` as a valid compass region value.
- Reduce redundant network calls by checking SQLite for known LinkedIn job IDs before fetching details.
- Infer `post_datetime` when missing using `collected_at - post_age_days`.
- Persist run state so a harvest can resume where it left off on the next invocation.
- Provide verbose timestamped logging suitable for cron plus periodic summaries.

**Non-Goals:**
- No background service framework (Airflow) or daemonization; scheduling remains external (cron/systemd/launchd).
- No multi-source harvesting in this change.
- No LLM-based “self-modifying scraper” that mutates rules without explicit user control.

## Decisions

### Add a harvest orchestrator

Decision: add a dedicated harvest orchestrator and expose it with a dedicated entrypoint such as `harvest-linkedin`, rather than folding batch behavior into `ingest-linkedin` flags.

Rationale:
- Harvest mode has different concerns than interactive ingestion: resume state, runtime windows, backoff behavior, and verbose logging.
- Keeps the existing `ingest-linkedin` UX intact for ad-hoc runs.

### Keep operational helpers source-local and Python-based

Decision: implement repo-owned cron/status/log helper entrypoints as Python files under `opensignal_job_intel/sources/` rather than generic top-level shell scripts.

Rationale:
- The helpers are specific to LinkedIn harvest operations, not generic repository utilities.
- Keeping them in the source package makes ownership clearer and removes duplicated shell logic.
- Python entrypoints can share one implementation module while still leaving external scheduling in cron rather than inside the core application loop.
- Cron install helpers should emit absolute interpreter paths so scheduled runs do not depend on the reduced `PATH` available inside cron.

### Schedule configuration format and location

Decision: store a repo-owned schedule template at `config/extraction_schedule.template.yaml` and allow a gitignored local schedule instance at `config/extraction_schedule.yaml`.

Rationale:
- Keeps the committed template and the editable local instance together in one place instead of splitting them across `config/` and `profiles/`.

Implementation note:
- Python stdlib does not parse YAML; prefer a small dependency (`PyYAML`) rather than inventing a partial YAML parser.

### Incrementality via DB existence checks before detail fetch

Decision: treat LinkedIn job ID (`external_job_id`) as the primary identity for “already stored” checks. Harvest mode performs:
1) collect job IDs from search pages
2) check which IDs already exist in SQLite
3) fetch details only for unknown IDs

Rationale:
- The detail fetch is the most expensive and most throttle-prone step.
- This is the main lever to support harvesting thousands of postings safely.

### Query source comes from the professional compass

Decision: harvest queries reuse the role targets already present in the professional compass, instead of introducing a separate harvest query list in this change.

Rationale:
- Keeps the first implementation aligned with current repo behavior.
- Avoids introducing a second query-definition surface before the orchestrator is proven in practice.

### Age cutoff and search exhaustion stop rules

Decision: harvest mode stops pursuing a search stream when both of these are true:
1) the run encounters a posting older than the configured recency window (initially two weeks via `search.max_post_age_days`)
2) the run also sees N consecutive search pages with no new LinkedIn job IDs

Rationale:
- LinkedIn search results are expected to trend newest-to-oldest, so once the stream is stale there is little value in pushing deeper into the tail.
- This gives the harvester a simple, measurable way to stop when nightly yield has dried up.

Bug-fix clarification:
- Narrow searches can also exhaust without exposing clearly stale age signals in the returned HTML.
- Therefore, the harvester should stop after 5 consecutive search pages with no new LinkedIn job IDs even when `stale_results` remains false.

### Filter as much as possible before detail fetch, but keep v1 simple

Decision: the first harvest implementation should use the current extractor behavior plus aggressive known-ID skipping before detail fetch. Richer pre-detail filtering from search metadata can be added later if needed.

Rationale:
- Request minimization is more important than speculative pre-optimization.
- The existing extractor already gives enough surface area to validate the orchestrator before making search-page parsing more complex.

### Exponential backoff under HTTP 403 with sticky caution

Decision: implement exponential backoff triggered by HTTP 403 only. After a 403, the harvester becomes more conservative for the remainder of the run rather than immediately returning to its original pace after a single success.

Rationale:
- The user is most concerned about IP/account throttling rather than generic request failures.
- Sticky caution is the safer first behavior for unattended overnight runs.
- Non-403 errors should still be logged, but do not need to drive the same throttling policy in this change.

### Verbose timestamped logging

Decision: harvest mode logs every request and important event with a local timestamp (`YYYY-MM-DD HH:mm:ss`) and also emits periodic summary lines.

Rationale:
- Cronified overnight runs need enough detail to understand where the harvester was in the result stream when throttling or drift occurred.
- Summary lines make long logs easier to scan without sacrificing forensic detail.

### Resume where the last run stopped

Decision: the harvest orchestrator persists run memory beyond stored jobs, including last query positions, recent throttling events, last successful run timestamps, and per-query yield stats.

Rationale:
- This lets each nightly run continue from prior progress rather than rediscovering the same low-yield territory.
- Operational state is a core part of request minimization.

### Posting datetime inference

Decision: when `post_datetime` is missing and `post_age_days` is present, infer `post_datetime = collected_at - post_age_days` (date-level precision). Store the inferred value.

Rationale:
- Enables time-based queries and downstream workflows without re-scraping.

## Risks / Trade-offs

- [YAML dependency increases setup friction] -> Mitigation: keep dependency list minimal and document `pip install -r requirements.txt`.
- [LinkedIn blocks/changes pages] -> Mitigation: raw capture + diagnostics remain available; harvest should back off under 403, preserve state, and continue only while the nightly window remains open.
- [Large SQLite DB growth] -> Mitigation: rely on indices for ID existence checks; keep schema additive.
- [Verbose request logging creates large logs] -> Mitigation: keep line-oriented logs simple and pair them with periodic summaries.

## Migration Plan

- Add schedule template under `config/` and ignore the local override path.
- Add harvest orchestrator entrypoint.
- Add source-local Python operational entrypoints for install/remove/run/status/log inspection.
- Add repository helper(s) for efficient ID existence checks.
- Add persistent harvest run state.
- Backfill `post_datetime` inference for newly collected jobs (and optionally for existing rows if explicitly requested).

## Open Questions

- Should verbose request logs go only to a file, or to both stdout and a file during cron runs?
- Should persisted run state live in SQLite, a sidecar file, or both?
