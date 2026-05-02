## ADDED Requirements

### Requirement: Nightly harvest schedule configuration
The system SHALL support a long-running harvest mode configured by a local schedule file so the user can run ingestion unattended (e.g., nightly via cron).

#### Scenario: Harvest schedule file is loaded
- **WHEN** the user runs the harvest mode
- **THEN** the system loads harvest configuration from `config/extraction_schedule.yaml`
- **AND** it fails with an actionable error if the configuration is missing or invalid

#### Scenario: Harvest runs within a nightly window
- **WHEN** the harvest schedule defines a nightly runtime window
- **THEN** the system runs only while the current local time remains within that window
- **AND** it stops cleanly when the window ends

### Requirement: Pacing and randomized backoff
The system SHALL pace acquisition requests and apply randomized backoff under throttling to reduce the likelihood of being blocked.

#### Scenario: Harvest uses jittered pacing
- **WHEN** harvest mode is running
- **THEN** the system introduces jittered delays between network requests based on the schedule configuration

#### Scenario: Harvest backs off under throttling
- **WHEN** LinkedIn responds with HTTP 403 during harvest mode
- **THEN** the system applies exponential backoff delays up to a configured ceiling
- **AND** the ceiling MUST allow values up to 4 hours

#### Scenario: Harvest remains cautious after throttling
- **WHEN** harvest mode receives an HTTP 403 and later resumes making requests in the same run
- **THEN** the system continues at a more conservative pace for the remainder of that run

### Requirement: Resume-aware harvest state
The system SHALL persist harvest state so nightly runs can continue from prior progress instead of restarting from the beginning each time.

#### Scenario: Harvest resumes from prior state
- **WHEN** a new nightly harvest run starts after an earlier run stopped due to time window completion or throttling
- **THEN** the system loads prior harvest state including query position, throttling memory, last success timestamps, and per-query yield stats
- **AND** it resumes from that state when choosing the next work to perform

### Requirement: Verbose timestamped logging
The system SHALL provide verbose timestamped logging suitable for overnight batch runs.

#### Scenario: Harvest logs each request and important event
- **WHEN** harvest mode is running
- **THEN** the system emits request and event log lines with local timestamps
- **AND** it periodically prints summary lines with counts for requests, new jobs discovered, jobs stored, and jobs dropped/filtered
