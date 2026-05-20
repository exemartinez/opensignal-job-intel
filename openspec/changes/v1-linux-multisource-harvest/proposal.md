## Why

On this machine (pop!_OS/Linux), the unattended harvest workflow is not meeting expectations:

- The runtime harvest command is LinkedIn-only (`harvest-linkedin`), but the user expects unattended extraction to include Indeed and Wellfound as well.
- Linux-specific runtime assumptions are not explicit or validated in the operational flow, causing fragile execution and difficult troubleshooting.

We need a Linux-first, source-inclusive harvest path that is explicit about what runs unattended, what dependencies are required, and how failures are reported.

## What Changes

- Extend unattended harvesting from LinkedIn-only to a multi-source runtime flow that can include LinkedIn, Indeed, and Wellfound.
- Introduce a Linux compatibility layer for unattended runs:
  - preflight checks for required runtime dependencies
  - clear startup errors with actionable remediation
  - source-level failure isolation so one failing source does not abort all harvesting
- Add explicit source selection controls for unattended execution (enable/disable per source).
- Keep existing single-source commands available for backward compatibility.
- Update docs and runtime guidance for Linux (pop!_OS) operations.

## Capabilities

### New Capabilities

- Multi-source unattended harvest orchestration with per-source execution and reporting.
- Linux preflight diagnostics for unattended harvest runtime dependencies.

### Modified Capabilities

- Batch harvesting behavior: from LinkedIn-only unattended scheduling to configurable multi-source unattended scheduling.
- Runtime operational status/log outputs to include per-source health and counters.

## Impact

- Code:
  - `src/runtime_entrypoints.py`
  - `src/harvest_orchestration.py`
  - `src/indeed_acquisition.py`
  - `src/wellfound_acquisition.py`
  - `src/persistence_runtime_ops.py`
- Specs:
  - `openspec/specs/batch-harvesting/spec.md` (expand from LinkedIn-only to multi-source harvesting semantics)
- Tests:
  - add/adjust unit tests for multi-source unattended orchestration, Linux preflight behavior, and source-isolated failure handling
- Docs:
  - `README.md`
  - `AGENTS.md`
  - `CHANGELOG.md`
