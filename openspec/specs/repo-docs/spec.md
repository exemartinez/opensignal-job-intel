# repo-docs Specification

## Purpose
TBD - created by archiving change v1-docs-release-notes. Update Purpose after archive.
## Requirements
### Requirement: README reflects current repo behavior
The repository SHALL maintain a README that describes the current supported CLI workflows, configuration inputs, environment setup, and canonical test execution workflow.

#### Scenario: README documents LinkedIn ingestion modes
- **WHEN** a user reads the README
- **THEN** it describes how to run LinkedIn ingestion in fixture mode and in live acquisition mode
- **AND** it describes the required inputs (professional compass JSON, and extraction spec default/override)

#### Scenario: README documents local-only sensitive configuration
- **WHEN** the README references optional authenticated scraping or local LLM usage
- **THEN** it documents the configuration mechanism (env vars / gitignored local files)
- **AND** it does not require committing secrets to the repository

#### Scenario: README documents engineering bootstrap and test workflow
- **WHEN** a contributor prepares to run or extend the automated suite
- **THEN** the README documents the supported Python environment bootstrap steps
- **AND** it documents the canonical dependency installation command
- **AND** it documents the canonical automated test command used for repository validation

### Requirement: Changelog exists and follows a stable format
The repository SHALL include a `CHANGELOG.md` that documents notable changes using an Unreleased section and dated release entries.

#### Scenario: Changelog has Unreleased and dated entries
- **WHEN** a user opens `CHANGELOG.md`
- **THEN** it contains a `## [Unreleased]` section
- **AND** it contains dated release entries with `### Added`, `### Changed`, `### Fixed`, and `### Removed` subsections when applicable

### Requirement: Curated architecture diagrams are maintained
The repository SHALL maintain curated plain-text UML artifacts that explain the
LinkedIn core structure and the ingest/harvest runtime flow during the refactor.

#### Scenario: Contributor can inspect focused structure and flow
- **WHEN** a contributor needs to understand the LinkedIn refactor target
- **THEN** the repository provides a focused class diagram and an ingest/harvest
  flow diagram under `docs/`
- **AND** those diagrams remain aligned with the intended architectural
  boundaries of the refactor

### Requirement: Architecture docs explain the refactor boundary rules
The repository SHALL maintain architecture-facing documentation that explains
the responsibility boundaries, runtime-entrypoint rules, OO expectations, and
behavior-preserving refactor constraints for the LinkedIn core surface.

#### Scenario: Refactor guidance is discoverable
- **WHEN** a contributor reads the repository architecture guidance
- **THEN** they can identify the intended responsibility boundaries, the role of
  runtime entrypoints, and the requirement to preserve current behavior while
  refactoring
