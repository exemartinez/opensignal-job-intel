## Context

The current CLI supports LinkedIn ingestion in fixture mode and live acquisition mode. It can store canonical jobs in SQLite and apply best-effort filters driven by the professional compass. The next step is to operate the system as a nightly “job farmer” that can run for hours, accumulate a large local corpus, and minimize the risk of throttling by pacing requests and backing off under 429/403.

Key constraints:
- Local-first: SQLite remains the primary store.
- Human-in-the-loop: the system collects and scores; no auto-apply.
- LinkedIn acquisition is scraping-based and drift-prone; runs must be debuggable.
- Harvest runs must be incremental/idempotent: do not refetch details for jobs already stored.

## Goals / Non-Goals

**Goals:**
- Add a dedicated harvest execution path intended for unattended nightly runs.
- Read harvest runtime controls from a schedule config file (`config/extraction_schedule.yaml`).
- Enforce strict, compass-driven constraints for harvesting (remote-only + region + parametric recency).
- Reduce redundant network calls by checking SQLite for known LinkedIn job IDs before fetching details.
- Infer `post_datetime` when missing using `collected_at - post_age_days`.
- Provide low-noise stdout progress suitable for cron logs.

**Non-Goals:**
- No background service framework (Airflow) or daemonization; scheduling remains external (cron/systemd/launchd).
- No multi-source harvesting in this change.
- No LLM-based “self-modifying scraper” that mutates rules without explicit user control.

## Decisions

### Add a harvest entrypoint

Decision: add a dedicated harvest entrypoint (either a new subcommand like `harvest-linkedin` or an explicit `--harvest` mode) to separate interactive runs from long-running batch behavior.

Rationale:
- Harvest mode has different defaults (strict filtering, pacing/backoff, progress cadence).
- Keeps the existing `ingest-linkedin` UX intact for ad-hoc runs.

### Schedule configuration format and location

Decision: store a repo-owned schedule template at `config/extraction_schedule.yaml` and allow a user override under a gitignored local file (e.g., `profiles/extraction_schedule.yaml`).

Rationale:
- Mirrors the extraction-spec pattern: committed default + local override.

Implementation note:
- Python stdlib does not parse YAML; prefer a small dependency (`PyYAML`) rather than inventing a partial YAML parser.

### Idempotency via DB existence checks before detail fetch

Decision: treat LinkedIn job ID (`external_job_id`) as the primary identity for “already stored” checks. Harvest mode performs:
1) collect job IDs from search pages
2) check which IDs already exist in SQLite
3) fetch details only for unknown IDs

Rationale:
- The detail fetch is the most expensive and most throttle-prone step.
- This is the main lever to support harvesting thousands of postings safely.

### Strict filter policy for harvest mode

Decision: harvest mode uses a stricter policy than interactive ingestion:
- region: accept postings that clearly indicate "United States" and "Remote" even without city/state
- recency: use `search.max_post_age_days` (parametric)
- missing signals: apply an explicit policy (configured for harvest mode) to drop or keep when age/location/workplace cannot be extracted

Rationale:
- The goal is a high-signal database; permissive behavior will accumulate junk at scale.

### Randomized backoff under 429/403

Decision: implement randomized backoff with jitter, up to a configured ceiling (max 4 hours). Backoff state should be visible via diagnostics/progress.

Rationale:
- Randomized delay reduces synchronized retry patterns and is less bot-like than a deterministic exponential schedule.
- A ceiling prevents the process from stalling indefinitely.

### Posting datetime inference

Decision: when `post_datetime` is missing and `post_age_days` is present, infer `post_datetime = collected_at - post_age_days` (date-level precision). Store the inferred value.

Rationale:
- Enables time-based queries and downstream workflows without re-scraping.

## Risks / Trade-offs

- [YAML dependency increases setup friction] -> Mitigation: keep dependency list minimal and document `pip install -r requirements.txt`.
- [Strict filtering drops good jobs when signals are missing] -> Mitigation: make the missing-field policy configurable; emit counts and reasons.
- [LinkedIn blocks/changes pages] -> Mitigation: raw capture + diagnostics remain available; harvest should exit cleanly after configured stop conditions.
- [Large SQLite DB growth] -> Mitigation: rely on indices for ID existence checks; keep schema additive.

## Migration Plan

- Add schedule template under `config/` and ignore the local override path.
- Add harvest entrypoint.
- Add repository helper(s) for efficient ID existence checks.
- Backfill `post_datetime` inference for newly collected jobs (and optionally for existing rows if explicitly requested).

## Open Questions

- Do we want harvest mode to stop immediately on first 403, or only after N consecutive 403/429 responses?
- Should `post_datetime` inference be applied only at ingestion time, or also as a periodic backfill job for existing rows?
- What is the minimum progress cadence (dots per request vs per detail fetch; summary every N details)?
