## ADDED Requirements

### Requirement: Multi-source ingestion can run acquisition in parallel
The system SHALL provide a CLI mode that ingests from multiple configured job sources in a single run while overlapping source acquisition work.

#### Scenario: Acquisition is parallelized but SQLite writes remain safe
- **WHEN** the user runs the multi-source ingestion command
- **THEN** the application runs source acquisition concurrently across LinkedIn, Indeed, and Wellfound
- **AND** the application persists canonical job records through the existing SQLite repository without concurrent writers (to avoid lock contention)
- **AND** the command reports per-source fetched/stored/inserted/updated counts

#### Scenario: One source failing does not block others
- **WHEN** one source acquisition fails during a multi-source ingestion run
- **THEN** the command reports the failure for that source
- **AND** continues ingesting any successfully acquired jobs from other sources
