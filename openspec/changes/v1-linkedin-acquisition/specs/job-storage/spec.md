## MODIFIED Requirements

### Requirement: SQLite job persistence
The system SHALL persist canonical job records in a local SQLite database as the default storage mechanism for v1.

#### Scenario: Canonical job is stored
- **WHEN** the application receives a canonical job record for storage
- **THEN** the record is written to SQLite with source metadata, job content fields, salary text when available, workflow status markers, and storage timestamps

#### Scenario: LinkedIn acquisition metadata is stored when available
- **WHEN** a LinkedIn job is stored
- **THEN** the database stores any available job location text and workplace mode (remote/hybrid/onsite)
- **AND** the database stores any available posting age signals (raw age text and/or a normalized numeric age)

### Requirement: Additive schema initialization
The system SHALL initialize and evolve the local SQLite schema without requiring the user to delete an existing database for additive column changes in v1.

#### Scenario: Existing database is missing a newly introduced column
- **WHEN** the repository initializes against an existing local SQLite database that lacks an additive canonical field such as salary text
- **THEN** the repository updates the schema so the ingestion workflow can continue without manual database recreation

#### Scenario: Existing database is missing newly introduced acquisition filter columns
- **WHEN** the repository initializes against an existing local SQLite database that lacks newly introduced columns for location/workplace mode/posting age
- **THEN** the repository adds the missing columns without requiring manual database recreation
