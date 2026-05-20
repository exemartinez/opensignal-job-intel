# Changelog

All notable changes to this project will be documented in this file.
This project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Indeed ingestion support through the shared `JobSourceAdapter` flow, including fixture-backed and live acquisition modes, deterministic extraction, source-local diagnostics, and canonical SQLite persistence/reporting.
- Wellfound ingestion support through the shared `JobSourceAdapter` flow (fixture-backed and live scraping), including canonical normalization and CLI wiring via `ingest-wellfound`.
- `ingest-all` CLI command to run LinkedIn, Indeed, and Wellfound acquisition in parallel (multiprocessing) while serializing SQLite writes for lock-safe persistence.

### Changed
- Live Indeed acquisition now uses Selenium-backed browser automation rather than raw HTTP requests because Indeed search pages are challenge-protected, with Chrome as the default live browser path on this machine.
- Live Indeed search-card persistence now rejects placeholder or mismatched card ids and stores only canonical href-backed `viewjob` URLs derived from verified `jk` values.
- Live Wellfound acquisition now uses Selenium-backed browser automation so job detail pages can be fetched reliably without guest-mode 403 blocks.
- Added `harvest-all` runtime command for unattended multi-source harvesting (LinkedIn + Indeed + Wellfound) with per-source status output and failure isolation.
- Added Linux preflight diagnostics for unattended harvest runs so missing source dependencies and unsupported browser/runtime settings are reported before acquisition starts.
- Runtime cron wrapper (`run-harvest-cron`) now executes `main.py harvest-all` instead of a LinkedIn-only run.
- Runtime source imports are now resilient to optional dependency gaps so non-source commands can still run and preflight can report actionable errors.

## - 2026-05-18

### Changed
- Updated `AGENTS.md` runtime boundaries to reflect the current `src/` architecture, including the shared `JobSourceAdapter` contract and canonical `JobRecord` flow through ingestion.
- Documented the active source surface in `AGENTS.md` as LinkedIn, Indeed, and Wellfound acquisition modules, plus shared extraction/filter helpers in `src/linkedin_extraction_filtering.py`.
- Clarified operational flow in `AGENTS.md` for `ingest-all` (parallel acquisition with serialized SQLite persistence) and for nightly LinkedIn harvest orchestration in `src/harvest_orchestration.py`.

## - 2026-05-09

### Changed
- The refactored `src/` runtime surface now documents the purpose of each module and the goal of each class, method, and helper with concise Python docstrings.
- LinkedIn ingestion now reports persistence results as `persisted`, `new`, and `updated` counts, and emits a machine-readable `persistence_summary` block so duplicate-safe upserts are distinguishable from new inserts.
- Runtime and usage documentation in `README.md` now reflects the current `src/` command surface, end-to-end ingest commands, runtime helper commands, and OpenSpec validation commands.

## - 2026-05-07

### Changed
- Live LinkedIn fixture export now uses the canonical SQLite/job-record row shape instead of the older ad hoc extractor JSON shape, including `id`, `dedupe_key`, `source`, `external_job_id`, `company`, `title`, `description`, `post_datetime`, `link`, `salary_text`, `location_text`, `workplace_type`, `post_age_text`, `post_age_days`, `collected_at`, `stored_at`, `seen`, and `applied`, making the output safer for later data migration work.
- Live LinkedIn acquisition diagnostics now include richer URL/error details for transport failures.

## - 2026-04-22

### Added
- Live LinkedIn acquisition (scraping) mode for `ingest-linkedin` in addition to fixture mode.
- Compass-driven acquisition filters (best-effort): max post age, workplace type, and region.
- Configurable extraction spec template under `config/` with a local override path under `profiles/`.
- Optional local-only configuration for authenticated scraping and local LLM fallback extraction.
- Additional SQLite fields for filtering/review: `location_text`, `workplace_type`, `post_age_text`, `post_age_days`.

### Changed
- LinkedIn job detail extraction now supports guest-page HTML variants (not only JSON-LD).
- SQLite schema evolves additively to avoid requiring DB recreation.
