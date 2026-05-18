## Why

`ingest-all` overlaps acquisition across sources. For some runs, we want each source acquisition isolated in its own OS process to better utilize multicore hardware and to isolate browser crashes/leaks per source.

## What Changes

- Switch `ingest-all` acquisition fan-out from threads to multiprocessing (`ProcessPoolExecutor`).
- Keep SQLite persistence serialized in the parent process (single writer).
- Keep CLI surface stable.

## Capabilities

### New Capabilities
- (none)

### Modified Capabilities
- (none) Implementation detail only; externally visible behavior remains “parallel acquisition + canonical persistence”.

## Impact

- Code: `src/runtime_entrypoints.py`
- Tests: adjust `ingest-all` unit test to avoid spawning real processes
- Docs: update README/Changelog to reflect multiprocessing (not threads)
