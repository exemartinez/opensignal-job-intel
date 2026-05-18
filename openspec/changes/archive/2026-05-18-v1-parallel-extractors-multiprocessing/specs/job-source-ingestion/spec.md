## MODIFIED Requirements

### Requirement: Multi-source ingestion can run acquisition in parallel
The system SHALL provide a CLI mode that ingests from multiple configured job sources in a single run while overlapping source acquisition work.

#### Scenario: Each source acquisition runs in its own process
- **WHEN** the user runs the multi-source ingestion command
- **THEN** the application runs source acquisition concurrently across LinkedIn, Indeed, and Wellfound
- **AND** each source acquisition runs in a separate OS process
- **AND** the application persists canonical job records through a single SQLite writer in the parent process
