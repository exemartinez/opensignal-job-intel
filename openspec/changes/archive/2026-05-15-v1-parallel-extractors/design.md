## Overview

Introduce a single CLI entrypoint that runs LinkedIn, Indeed, and Wellfound ingestion together while overlapping their acquisition work.

## Concurrency Model

### What runs in parallel

- Source acquisition (`JobSourceAdapter.fetch_jobs()`), one task per source.
- Use `concurrent.futures.ThreadPoolExecutor` since acquisition is I/O-bound (network + Selenium).

### What remains serialized

- SQLite persistence (`SQLiteJobRepository.upsert_job()`), to avoid multiple concurrent writers and DB lock contention.
- Evaluation is performed in the same loop as persistence for each canonical job record so the run remains easy to reason about and test.

## Error Handling

- If a source acquisition fails, the command reports that failure and continues with other sources.
- The command returns a non-zero exit code only when all sources fail or when persistence initialization fails.

## Output / Observability

- Per-source acquisition diagnostics (if adapter exposes `.diagnostics.as_dict()`).
- A final JSON summary containing:
  - per-source fetched/persisted counts
  - total inserted/updated counts
  - final stored record count

## Configuration

- Reuse existing per-source adapter configuration and defaults.
- Wellfound configuration continues to come from the schedule YAML (for headless/headful, profile dir, pacing knobs). No environment variables are required.
