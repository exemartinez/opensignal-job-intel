## ADDED Requirements

### Requirement: Nightly harvest schedule configuration
The system SHALL support a long-running harvest mode configured by a local schedule file so the user can run ingestion unattended (e.g., nightly via cron).

#### Scenario: Harvest schedule file is loaded
- **WHEN** the user runs the harvest mode
- **THEN** the system loads harvest configuration from `config/extraction_schedule.yaml`
- **AND** it fails with an actionable error if the configuration is missing or invalid

### Requirement: Pacing and randomized backoff
The system SHALL pace acquisition requests and apply randomized backoff under throttling to reduce the likelihood of being blocked.

#### Scenario: Harvest uses jittered pacing
- **WHEN** harvest mode is running
- **THEN** the system introduces jittered delays between network requests based on the schedule configuration

#### Scenario: Harvest backs off under throttling
- **WHEN** LinkedIn responds with throttling or access-denied signals (e.g., HTTP 429/403)
- **THEN** the system applies randomized backoff delays up to a configured ceiling
- **AND** the ceiling MUST allow values up to 4 hours

### Requirement: Low-noise progress reporting
The system SHALL provide stdout-friendly progress output suitable for overnight batch runs.

#### Scenario: Harvest prints periodic progress
- **WHEN** harvest mode is running
- **THEN** the system emits low-noise progress indicators (e.g., dots) for ongoing work
- **AND** it periodically prints summary lines with counts for requests, new jobs discovered, jobs stored, and jobs dropped/filtered
