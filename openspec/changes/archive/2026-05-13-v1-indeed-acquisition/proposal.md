## Why

The repository now has a working source-adapter pattern, but LinkedIn is still the only real acquisition path. Adding Indeed is the next useful test of whether the current ingestion architecture can support another source without breaking the canonical job flow or duplicating persistence and evaluation logic.

Indeed support should be added now while the `src/` boundaries are still fresh, so the second source lands through the intended strategy-style adapter seam instead of forcing another source-specific one-off path later.

## What Changes

- Add an Indeed acquisition path that follows the same canonical ingestion contract used by LinkedIn.
- Add an Indeed-specific source adapter with fixture-backed and live browser-backed acquisition modes, structured diagnostics, and canonical job normalization.
- Add Indeed extraction and filtering support for mapping Indeed search/detail pages into the shared `JobRecord` shape.
- Add CLI support for Indeed ingestion through the existing runtime-entrypoint surface.
- Keep persistence, evaluation, and reporting shared across sources rather than introducing an Indeed-specific storage schema.
- Document the Indeed runtime commands, Selenium/browser prerequisites, and any local-only environment variables required for live acquisition.

## Capabilities

### New Capabilities
- `indeed-acquisition`: Defines Indeed-specific acquisition, extraction, diagnostics, and canonical fixture/export behavior.

### Modified Capabilities
- `job-source-ingestion`: The shared ingestion contract will expand from a LinkedIn-only real source path to a multi-source ingestion surface that includes Indeed.
- `linkedin-core-architecture`: The current `src/` structure will be widened from a LinkedIn-only source layout to a multi-source adapter layout that still preserves shared runtime and persistence boundaries.
- `repo-docs`: The README and supporting docs will need to describe the Indeed commands, configuration paths, and local-only runtime options.

## Impact

- Affected code:
  - `src/runtime_entrypoints.py`
  - `src/core_domain_inputs.py`
  - new Indeed source module(s) under `src/`
  - Selenium-backed live acquisition collaborators for Indeed
- Affected CLI:
  - new Indeed ingestion command surface
  - possible shared argument cleanup where LinkedIn and Indeed can reuse the same runtime patterns
- Affected docs:
  - `README.md`
  - `CHANGELOG.md`
  - any architecture notes needed to explain how multiple source adapters fit the current design
- Affected dependencies:
  - `requirements.txt` gains Selenium for live Indeed browser automation
- Affected tests:
  - new Indeed adapter/extraction coverage
  - CLI coverage for the Indeed command path
  - preservation of canonical persistence and evaluation behavior across both sources
