## Why

The current LinkedIn surface has accumulated too many responsibilities inside a small number of large modules. Acquisition, extraction, filtering, harvest orchestration, runtime operations, and thin script entrypoints are coupled in ways that make the code difficult to reason about and expensive to evolve safely.

The archived test-coverage foundation now gives this repository enough regression protection to perform a structural refactor without changing externally visible behavior. This is the right moment to separate concerns, remove duplicated logic, and make the intended architecture explicit before more functionality gets built on top of the current layout.

## What Changes

- Refactor the current LinkedIn surface into a single `src/` package root, replacing the current `opensignal_job_intel/` layout.
- Consolidate the refactor target into a small set of top-level Python modules under `src/`, organized around these responsibility boundaries:
  - `LinkedIn Acquisition`
  - `Runtime Entrypoints`
  - `Harvest Orchestration`
  - `Core Domain Inputs`
  - `LinkedIn Extraction + Filtering`
  - `Persistence + Runtime Ops`
- Move the system behavior into classes within those modules so the design is explicitly object-oriented and responsibility-driven.
- Refactor the current `opensignal_job_intel/sources/` surface into cleaner collaborator boundaries for:
  - LinkedIn acquisition and transport
  - deterministic extraction and fallback extraction
  - query planning and filter evaluation
  - harvest orchestration and runtime state transitions
  - operational runtime support for cron/status/log helpers
- Reduce duplicated logic across acquisition and harvest flows, especially around query derivation, URL construction, filtering decisions, diagnostics, export/fixture serialization, and runtime helper concerns.
- Keep externally visible CLI behavior, ingestion behavior, harvest behavior, persistence behavior, and script entrypoint behavior stable while internal modules, classes, and package structure are reorganized.
- Clarify ingestion persistence reporting so command output distinguishes newly inserted jobs from updates to existing deduplicated rows.
- Keep runtime entrypoints thin. When executable entrypoints are still required, they should delegate immediately into class-owned behavior rather than accumulating operational logic in free functions or script bodies.
- Add or maintain module-level Python docstrings at the beginning of each refactored module describing its responsibility and author attribution (`Ezequiel H. Martinez`).
- Use `docs/linkedin_core_focused_class_diagram.puml` as the guiding structural reference for the intended organization during the refactor.
- Add and maintain curated plain-text UML artifacts that make the current structure and runtime flow reviewable during the refactor.

## Capabilities

### New Capabilities
- `linkedin-core-architecture`: Defines the intended architectural boundaries, collaborator responsibilities, package direction, and script/runtime separation for the LinkedIn core surface.

### Modified Capabilities
- `job-source-ingestion`: Internal LinkedIn ingestion responsibilities will be reorganized behind cleaner collaborators while preserving the ingestion contract.
- `batch-harvesting`: Harvest orchestration will be decomposed into clearer runtime and domain collaborators while preserving the existing harvest contract.
- `repo-docs`: Repository documentation will include architecture-facing guidance and curated UML artifacts that explain both the structural hotspot and the ingest/harvest runtime flow.

## Impact

- Affected code:
  - current `opensignal_job_intel/` package will be reorganized into `src/`
  - current `opensignal_job_intel/sources/` surface will be redistributed into the new top-level core modules
  - `cli.py`, `services.py`, `repositories/sqlite_jobs.py`, and shared models/evaluation boundaries will be absorbed or reorganized according to the new module boundaries
- Affected package layout:
  - imports, module boundaries, and runtime entrypoints will change substantially
  - externally visible behavior must remain stable during that transition
- Affected docs:
  - `ARCHITECTURE.md`
  - curated UML artifacts under `docs/`
  - any supporting README guidance needed to explain the new `src/` structure and runtime-entrypoint boundaries
- Affected workflow:
  - implementation must preserve behavior first, then improve structure in small validated steps
  - any behavior change discovered during refactor must be captured through OpenSpec instead of being folded into "cleanup"
