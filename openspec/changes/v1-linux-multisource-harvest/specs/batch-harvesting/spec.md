## MODIFIED Requirements

### Requirement: Runtime operational entrypoints
The system SHALL provide repo-owned Python operational entrypoints for unattended harvest installation, execution, and monitoring through the unified runtime surface.

#### Scenario: Runtime operational entrypoints support multi-source unattended harvest
- **WHEN** the user wants unattended harvesting beyond LinkedIn
- **THEN** the repository provides a runtime entrypoint that executes unattended harvesting for LinkedIn, Indeed, and Wellfound in one run
- **AND** existing source-specific operational entrypoints remain available for backward compatibility

### Requirement: Resume-aware harvest state
The system SHALL persist harvest state so unattended runs can continue from prior progress instead of restarting from the beginning each time.

#### Scenario: Multi-source unattended harvest resumes source-local progress
- **WHEN** a new unattended run starts after an earlier run stopped
- **THEN** the system resumes each enabled source from its own persisted progress/state where supported
- **AND** one source state failure does not block loading state for other enabled sources

## ADDED Requirements

### Requirement: Linux runtime preflight for unattended harvest
Before unattended harvesting starts, the system SHALL validate Linux runtime prerequisites and report actionable diagnostics.

#### Scenario: Missing Linux dependency is reported before source execution
- **WHEN** the unattended harvest command runs on Linux and a required runtime dependency is missing (for example `selenium`, browser runtime, or required config file)
- **THEN** the system reports a structured preflight failure with source scope and remediation guidance
- **AND** it does not start that failing source

#### Scenario: Global preflight failures stop the unattended run
- **WHEN** a global prerequisite fails (for example database path unavailable)
- **THEN** the unattended run stops before source acquisition begins
- **AND** the failure is reported as actionable runtime output

### Requirement: Source-isolated failure handling in unattended multi-source harvest
The unattended multi-source harvest flow SHALL isolate source failures so healthy sources can continue.

#### Scenario: One source fails while others continue
- **WHEN** one enabled source fails during preflight or acquisition
- **THEN** the system records that source as failed or skipped with structured error details
- **AND** acquisition continues for remaining enabled sources
- **AND** final summary output includes per-source status and counters

