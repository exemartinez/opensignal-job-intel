# indeed-acquisition Specification

## ADDED Requirements

### Requirement: Indeed fixture-backed ingestion
The system SHALL support fixture-backed Indeed ingestion through the same
canonical source-adapter boundary used by other sources.

#### Scenario: Local Indeed fixture is ingested
- **WHEN** the user runs the Indeed ingestion command with a local source fixture
- **THEN** the Indeed adapter reads the fixture, normalizes the postings into
  canonical job records, and passes them to the shared persistence and
  evaluation flow

### Requirement: Indeed live acquisition
The system SHALL support live Indeed acquisition that produces canonical job
records suitable for the shared ingestion workflow.

#### Scenario: Live Indeed acquisition succeeds
- **WHEN** the user runs the Indeed ingestion command in live mode
- **THEN** the adapter performs browser-backed Indeed acquisition and returns
  canonical job records with full descriptions and stable identifiers when
  available
- **AND** search-card records are persisted only when the adapter can derive a
  real href-backed `jk` identifier and canonical Indeed job URL

### Requirement: Indeed acquisition diagnostics
The Indeed adapter SHALL emit structured diagnostics for acquisition,
extraction, and drop behavior.

#### Scenario: Indeed acquisition is debuggable
- **WHEN** the Indeed adapter performs live acquisition
- **THEN** it reports request counts, parse failures, and dropped-record reasons
- **AND** it MAY persist local capture artifacts for debugging

### Requirement: Indeed live acquisition declares browser prerequisites
The system SHALL document the Selenium and browser prerequisites required for
live Indeed scraping.

#### Scenario: Developer prepares the live Indeed runtime
- **WHEN** a developer follows the repository setup instructions for live Indeed scraping
- **THEN** the docs explain that Selenium is required
- **AND** the docs explain the local browser prerequisite for the supported automation path

### Requirement: Indeed extraction normalizes into the canonical job shape
The Indeed adapter SHALL map Indeed source content into the canonical shared
job-record structure rather than introducing an Indeed-specific persisted row
shape.

#### Scenario: Indeed job is normalized before storage
- **WHEN** an Indeed posting is acquired from fixture or live mode
- **THEN** the adapter produces a canonical record containing source, company,
  title, description, link, collected timestamp, and any available source
  identifier, posting datetime, or salary text before storage is attempted
