# Changelog

All notable changes to this project will be documented in this file.
This project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
