## Tasks

- [ ] Add CLI command `ingest-all` (or equivalent) to run LinkedIn, Indeed, and Wellfound ingestion together.
- [ ] Run acquisition for the three sources concurrently (ThreadPoolExecutor).
- [ ] Serialize SQLite persistence through a single repository instance to avoid lock contention.
- [ ] Emit per-source acquisition diagnostics plus a consolidated persistence JSON summary.
- [ ] Add unit tests covering:
  - CLI dispatch for the new command
  - parallel acquisition wiring (mock adapters)
  - persistence behavior (upsert calls and inserted/updated accounting)
- [ ] Update `README.md` with the new command and common flags.
- [ ] Create/update delta spec: `job-source-ingestion`.
- [ ] Run `openspec validate v1-parallel-extractors`.
- [ ] Run `python3.11 -m unittest discover -s tests -v`.
