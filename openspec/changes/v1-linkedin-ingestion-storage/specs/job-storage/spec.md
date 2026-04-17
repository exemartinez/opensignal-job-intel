## ADDED Requirements

### Requirement: SQLite job persistence
The system SHALL persist canonical job records in a local SQLite database as the default storage mechanism for v1.

#### Scenario: Canonical job is stored
- **WHEN** the application receives a canonical job record for storage
- **THEN** the record is written to SQLite with source metadata, job content fields, salary text when available, workflow status markers, and storage timestamps

### Requirement: Duplicate-safe source record storage
The system SHALL avoid creating duplicate stored jobs for the same source-origin posting when a stable identifier or canonical link is available.

#### Scenario: Duplicate source job is ingested again
- **WHEN** the application attempts to store a job that matches an existing source-origin record
- **THEN** the repository preserves a single stored job record and updates timestamps or other allowed mutable fields according to repository rules

### Requirement: Workflow status tracking
The system SHALL store human workflow status markers needed to exclude jobs that were already reviewed or applied to in future qualification flows.

#### Scenario: Stored job includes human workflow status
- **WHEN** a job record is stored in SQLite
- **THEN** the database schema includes fields that can represent whether the job has been seen or applied to

### Requirement: Additive schema initialization
The system SHALL initialize and evolve the local SQLite schema without requiring the user to delete an existing database for additive column changes in v1.

#### Scenario: Existing database is missing a newly introduced column
- **WHEN** the repository initializes against an existing local SQLite database that lacks an additive canonical field such as salary text
- **THEN** the repository updates the schema so the ingestion workflow can continue without manual database recreation
