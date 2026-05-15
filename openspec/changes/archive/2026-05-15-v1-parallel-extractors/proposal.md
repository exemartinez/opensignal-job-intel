## Why

Running LinkedIn, Indeed, and Wellfound ingestion sequentially makes a full run slower than it needs to be. Acquisition is largely I/O-bound (HTTP + Selenium) and can be overlapped safely, but persistence into SQLite must remain correct and predictable.

## What Changes

- Add a new CLI command to run LinkedIn, Indeed, and Wellfound ingestion in a single run with parallelized acquisition.
- Keep SQLite persistence deterministic and safe (avoid concurrent writers / lock contention).
- Emit per-source acquisition diagnostics plus a consolidated persistence summary.

## Capabilities

### New Capabilities
- (none)

### Modified Capabilities
- `job-source-ingestion`: add a multi-source parallel ingestion mode/command that runs source acquisition concurrently while preserving canonical persistence behavior.

## Impact

- Code:
  - `src/runtime_entrypoints.py` (new CLI command and wiring)
  - possibly small helper(s) in `src/core_domain_inputs.py` if needed for shared ingestion logic
- Tests:
  - new unit tests for CLI dispatch and persistence behavior under the parallel command
- Docs:
  - `README.md` to include the new command and expected outputs/knobs
