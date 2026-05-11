# Changelog

All notable changes to this project will be documented in this file.
This project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
