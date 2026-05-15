## Tasks

- [x] Add CLI command `ingest-all` (or equivalent) to run LinkedIn, Indeed, and Wellfound ingestion together.
- [x] Run acquisition for the three sources concurrently (ThreadPoolExecutor).
- [x] Serialize SQLite persistence through a single repository instance to avoid lock contention.
- [x] Emit per-source acquisition diagnostics plus a consolidated persistence JSON summary.
- [x] Add unit tests covering:
  - CLI dispatch for the new command
  - parallel acquisition wiring (mock adapters)
  - persistence behavior (upsert calls and inserted/updated accounting)
- [x] Update `README.md` with the new command and common flags.
- [x] Create/update delta spec: `job-source-ingestion`.
- [x] Run `openspec validate v1-parallel-extractors`.
- [x] Run `python3.11 -m unittest discover -s tests -v`.
