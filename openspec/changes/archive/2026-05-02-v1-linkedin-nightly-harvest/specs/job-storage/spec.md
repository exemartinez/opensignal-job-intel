## ADDED Requirements

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
