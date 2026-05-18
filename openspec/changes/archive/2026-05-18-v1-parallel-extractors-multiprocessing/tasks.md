## Tasks

- [x] Replace `ThreadPoolExecutor` with `ProcessPoolExecutor` in `ingest-all`.
- [x] Ensure the acquisition worker function is picklable (module-level).
- [x] Keep SQLite persistence serialized (single writer).
- [x] Update unit tests for `ingest-all` to avoid spawning processes.
- [x] Update `README.md` and `CHANGELOG.md` to describe multiprocessing behavior accurately.
- [x] Run `openspec validate v1-parallel-extractors-multiprocessing`.
- [x] Run `python3.11 -m unittest discover -s tests -v`.
