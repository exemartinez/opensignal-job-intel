# batch-harvesting Specification

## Purpose
Define unattended harvest execution behavior for long-running LinkedIn collection workflows.

## Requirements
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

### Requirement: Runtime operational entrypoints
The system SHALL provide repo-owned Python operational entrypoints for LinkedIn harvest installation and monitoring through the unified runtime surface.

#### Scenario: Cron install helper remains external to core harvest loop
- **WHEN** the user wants to schedule recurring LinkedIn harvest runs
- **THEN** the repository provides a Python entrypoint through `src/runtime_entrypoints.py` that installs the cron command
- **AND** the scheduling mechanism remains external to the `harvest-linkedin` application command itself
- **AND** the installed cron command uses an absolute Python interpreter path from the install environment

#### Scenario: Runtime monitoring helpers are available through the runtime surface
- **WHEN** the user wants to inspect the current harvest process, recent stored jobs, or harvest logs
- **THEN** the repository provides Python entrypoints through `src/runtime_entrypoints.py` for those operations

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

### Requirement: Harvest orchestration is decomposed behind stable runtime behavior
The LinkedIn harvest implementation SHALL reorganize query planning, filter
evaluation, pacing/backoff, runtime state access, and result persistence behind
clear collaborators while preserving current harvest behavior.

#### Scenario: Harvest flow remains behaviorally stable
- **WHEN** the harvest internals are reorganized
- **THEN** the existing harvest command still honors schedule gating, resume
  state, filtering rules, and logging behavior
- **AND** those behaviors are implemented through explicit collaborators rather
  than one large mixed-responsibility module

### Requirement: Harvest operational helpers remain thin and external
The harvest operational helper modules SHALL remain external runtime entrypoints
that delegate into runtime-support collaborators rather than embedding harvest
domain logic directly.

#### Scenario: Operational helper behavior is preserved
- **WHEN** the refactor reorganizes cron installation, status, log tailing, or
  recent-job support
- **THEN** the operational helper entrypoints continue to expose the same
  runtime functions
- **AND** the helper modules remain thin wrappers over runtime-support classes
