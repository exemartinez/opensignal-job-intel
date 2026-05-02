## Why

Live LinkedIn acquisition works, but it is currently optimized for interactive runs rather than building a large, reliable local corpus. This change introduces a nightly, long-running harvest mode that incrementally collects recent US-remote, LATAM and AR job postings without repeatedly fetching the same jobs, while producing low-noise progress output suitable for cron.

## What Changes

- Add a “nightly harvest” execution path that can run for hours, pacing requests to resemble a human browsing pattern (jittered delays) and applying strict recency + geography + workplace constraints.
- Make harvesting incremental and idempotent at scale: avoid fetching job detail pages for jobs already present in SQLite, and rely on stable LinkedIn job IDs / canonical links for dedupe.
- Add schedule/run controls via a configuration file (e.g., runtime window, pacing, randomized backoff on 429/403 up to a 4-hour ceiling).
- Improve posting timestamps: when `post_datetime` is missing but `post_age_days` is available, infer an expected `post_datetime` from `collected_at - post_age_days`.
- Add lightweight progress reporting for long runs (stdout-friendly, periodic summaries).

## Capabilities

### New Capabilities

- `batch-harvesting`: Batch execution controls for long-running ingestion (schedule config, pacing/jitter, backoff/stop rules, and progress reporting).

### Modified Capabilities

- `job-source-ingestion`: Add harvest-mode behavior (strict filter policy, idempotent detail fetching based on DB existence, randomized backoff handling, and low-noise progress output).
- `job-storage`: Persist inferred `post_datetime` when the source-provided timestamp is missing, and support efficient “already have this job ID” checks to prevent refetching.

## Impact

- Affected code: LinkedIn acquisition adapter, CLI entrypoints, and SQLite repository query patterns (plus any new batch config loading).
- Data: SQLite continues to be the primary store; harvest mode increases volume (thousands of jobs) and should minimize duplicate network fetches.
- Operations: Intended to be run unattended (cron/server). Runs must degrade safely under throttling (randomized backoff) and exit cleanly.
