## ADDED Requirements

### Requirement: Live Wellfound acquisition adapter
The system SHALL support live acquisition of Wellfound job postings via a Wellfound-specific source adapter that returns canonical `JobRecord` entries.

#### Scenario: Live Wellfound acquisition returns canonical jobs
- **WHEN** the user runs the Wellfound ingestion command without a source fixture file
- **THEN** the system uses the Wellfound live adapter to fetch job postings
- **AND** it normalizes each posting into a canonical `JobRecord` with source, company, title, description, link, and collected timestamp

### Requirement: Fixture-backed Wellfound ingestion
The system SHALL support a local fixture-backed Wellfound adapter so ingestion behavior can be validated without live scraping.

#### Scenario: Local Wellfound fixture is ingested
- **WHEN** the user runs the Wellfound ingestion command with a local source fixture file
- **THEN** the system loads the fixture, normalizes items into canonical `JobRecord` rows, and passes them to persistence and evaluation

### Requirement: Wellfound diagnostics and capture support
The Wellfound live adapter SHALL emit structured diagnostics for acquisition and MAY persist raw capture artifacts for debugging.

#### Scenario: Live acquisition reports drops and request counts
- **WHEN** the Wellfound live adapter performs acquisition
- **THEN** it reports request counts and any dropped-record reasons
- **AND** failures include enough context to reproduce the failing request

### Requirement: Wellfound post datetime is not fabricated
The system SHALL NOT fabricate `post_datetime` for Wellfound postings when Wellfound does not provide a trustworthy posting timestamp.

#### Scenario: Missing Wellfound posting datetime remains unset
- **WHEN** a Wellfound posting does not include a reliable posting datetime signal
- **THEN** the canonical record stores `post_datetime` as null
- **AND** the system does not substitute `collected_at` as a posting time

