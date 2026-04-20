## ADDED Requirements

### Requirement: Canonical job normalization
The system SHALL normalize collected job postings into a canonical job record before passing them to persistence or downstream workflows.

#### Scenario: Source job is normalized before storage
- **WHEN** a source adapter returns a collected job posting
- **THEN** the system produces a canonical record containing source, company, title, description, source link, collected timestamp, and any available source identifier, post datetime, or salary text before storage is attempted

### Requirement: Source-specific ingestion boundary
The system SHALL isolate source acquisition behind a source adapter contract so that LinkedIn ingestion can be implemented without coupling the application to a specific acquisition mechanism or an official LinkedIn API.

#### Scenario: LinkedIn ingestion uses the adapter contract
- **WHEN** the application ingests jobs from LinkedIn
- **THEN** the application invokes a LinkedIn-specific adapter through the source adapter boundary rather than calling a LinkedIn API or browser automation flow directly from the CLI or repository layers

#### Scenario: Additional sources can be added without changing the canonical ingestion flow
- **WHEN** a new job source is introduced after LinkedIn
- **THEN** the application can add a new source adapter that produces canonical job records without requiring a source-specific storage schema

### Requirement: Fixture-backed LinkedIn stub ingestion
The system SHALL support a local fixture-backed LinkedIn adapter for v1 so the ingestion boundary can be exercised without claiming real LinkedIn acquisition.

#### Scenario: Local LinkedIn fixture is ingested
- **WHEN** the user runs the LinkedIn ingestion command with a local source fixture file
- **THEN** the LinkedIn adapter reads the fixture, normalizes the postings into canonical job records, and passes them to the persistence and evaluation flow
