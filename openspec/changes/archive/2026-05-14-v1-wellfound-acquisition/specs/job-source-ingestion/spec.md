## ADDED Requirements

### Requirement: Wellfound ingestion uses the adapter contract
The system SHALL ingest jobs from Wellfound through the existing source-adapter boundary.

#### Scenario: Wellfound ingestion is wired through the adapter boundary
- **WHEN** the user runs the Wellfound ingestion command
- **THEN** the application invokes a Wellfound-specific adapter through the `JobSourceAdapter` boundary
- **AND** it persists canonical job records through the same persistence and evaluation flow used for other sources

### Requirement: Wellfound source is deduplicated using the canonical policy
The system SHALL deduplicate Wellfound postings using the canonical `dedupe_key` policy.

#### Scenario: Wellfound records update rather than duplicate
- **WHEN** ingestion persists a Wellfound job whose dedupe key already exists in SQLite
- **THEN** the record is updated in place rather than inserted as a duplicate

