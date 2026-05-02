# job-storage Specification

## Purpose
TBD - created by archiving change v1-linkedin-ingestion-storage. Update Purpose after archive.
## Requirements
### Requirement: SQLite job persistence
The system SHALL persist canonical job records in a local SQLite database as the default storage mechanism for v1.

#### Scenario: Canonical job is stored
- **WHEN** the application receives a canonical job record for storage
- **THEN** the record is written to SQLite with source metadata, job content fields, salary text when available, workflow status markers, and storage timestamps

#### Scenario: LinkedIn acquisition metadata is stored when available
- **WHEN** a LinkedIn job is stored
- **THEN** the database stores any available job location text and workplace mode (remote/hybrid/onsite)
- **AND** the database stores any available posting age signals (raw age text and/or a normalized numeric age)

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

#### Scenario: Existing database is missing newly introduced acquisition filter columns
- **WHEN** the repository initializes against an existing local SQLite database that lacks newly introduced columns for location/workplace mode/posting age
- **THEN** the repository adds the missing columns without requiring manual database recreation

### Requirement: Efficient existence checks for harvesting
The system SHALL support efficient existence checks for LinkedIn job identifiers so harvest mode can avoid redundant detail fetches.

#### Scenario: Repository can check presence of a LinkedIn job identifier
- **WHEN** harvest mode has a LinkedIn `external_job_id` candidate
- **THEN** the repository can determine whether that identifier is already stored without scanning all jobs

### Requirement: Harvest run state is persisted
The system SHALL persist harvest run state needed to resume a nightly run where it previously stopped.

#### Scenario: Harvest state is stored between runs
- **WHEN** a harvest run advances through queries or experiences throttling
- **THEN** the system stores enough state to resume later, including last query positions, recent throttling events, last successful run timestamps, and per-query yield stats

### Requirement: Inferred posting datetime is persisted
The system SHALL persist an inferred `post_datetime` when the source posting timestamp is missing.

#### Scenario: Inferred post_datetime is stored
- **WHEN** the ingestion flow infers `post_datetime` from `collected_at - post_age_days`
- **THEN** the inferred value is stored in SQLite as the posting datetime
- **AND** schema initialization remains additive for existing databases
