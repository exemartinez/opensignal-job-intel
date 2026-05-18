## Change Summary

Replace the thread-based acquisition executor in `ingest-all` with a process-based executor.

## Rationale

- Each source acquisition is dominated by a browser session and can be isolated safely.
- Using separate processes avoids sharing Python interpreter state and can improve stability under long runs.

## Design

- Use `concurrent.futures.ProcessPoolExecutor` with one job per source.
- The worker function is module-level (`_fetch_jobs_for_source`) to be picklable under macOS spawn.
- The parent process:
  - collects `JobRecord` batches
  - persists sequentially to SQLite
  - emits consolidated diagnostics/summaries

## Risks / Constraints

- Process startup overhead is higher than threads.
- Each worker process runs its own browser instance; memory usage increases.
