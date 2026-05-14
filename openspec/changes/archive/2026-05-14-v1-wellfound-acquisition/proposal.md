## Why

We want to expand job sourcing beyond LinkedIn/Indeed by adding Wellfound as a first-class acquisition source, using the same ingestion + persistence pipeline so job data lands in SQLite with consistent normalization and filtering.

## What Changes

- Add a Wellfound acquisition adapter that supports:
  - live scraping (primary mode)
  - JSON fixture ingestion (offline/test mode)
- Add a new CLI command to ingest Wellfound jobs into the existing SQLite schema.
- Ensure normalization, deduplication, and compass filtering work the same way as other sources.
- Add tests covering parsing/normalization, URL canonicalization, filtering, and CLI wiring.
- Update repo docs (README/AGENTS/CHANGELOG as needed) with commands and operational notes.

## Capabilities

### New Capabilities

- `wellfound-acquisition`: Acquire Wellfound jobs (live scrape and fixture) and normalize them into canonical `JobRecord` rows suitable for evaluation + persistence.

### Modified Capabilities

- `job-source-ingestion`: Extend ingestion to support a new `JobSource` (Wellfound) while preserving existing ingestion behavior for LinkedIn and Indeed.

## Impact

- New/updated modules under `src/` for Wellfound acquisition (adapter, query/url builder, extraction/normalization).
- CLI surface in `main.py` / `src/runtime_entrypoints.py` gains an `ingest-wellfound` command.
- Potential dependency additions if Wellfound requires a different transport (ideally reuse existing Selenium setup used for Indeed).
- Tests expanded under `tests/` for Wellfound adapter behavior and CLI wiring.
