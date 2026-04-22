## ADDED Requirements

### Requirement: README reflects current repo behavior
The repository SHALL maintain a README that describes the current supported CLI workflows and configuration inputs.

#### Scenario: README documents LinkedIn ingestion modes
- **WHEN** a user reads the README
- **THEN** it describes how to run LinkedIn ingestion in fixture mode and in live acquisition mode
- **AND** it describes the required inputs (professional compass JSON, and extraction spec default/override)

#### Scenario: README documents local-only sensitive configuration
- **WHEN** the README references optional authenticated scraping or local LLM usage
- **THEN** it documents the configuration mechanism (env vars / gitignored local files)
- **AND** it does not require committing secrets to the repository

### Requirement: Changelog exists and follows a stable format
The repository SHALL include a `CHANGELOG.md` that documents notable changes using an Unreleased section and dated release entries.

#### Scenario: Changelog has Unreleased and dated entries
- **WHEN** a user opens `CHANGELOG.md`
- **THEN** it contains a `## [Unreleased]` section
- **AND** it contains dated release entries with `### Added`, `### Changed`, `### Fixed`, and `### Removed` subsections when applicable
