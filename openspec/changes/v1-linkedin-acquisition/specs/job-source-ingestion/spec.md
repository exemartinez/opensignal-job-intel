## MODIFIED Requirements

### Requirement: Source-specific ingestion boundary
The system SHALL isolate source acquisition behind a source adapter contract so that LinkedIn ingestion can be implemented without coupling the application to a specific acquisition mechanism or an official LinkedIn API.

#### Scenario: LinkedIn ingestion uses the adapter contract
- **WHEN** the application ingests jobs from LinkedIn
- **THEN** the application invokes a LinkedIn-specific adapter through the source adapter boundary rather than calling LinkedIn acquisition logic directly from the CLI or repository layers

#### Scenario: LinkedIn acquisition is debuggable
- **WHEN** the LinkedIn adapter performs acquisition
- **THEN** it emits structured diagnostics that include request counts, parse failures, and dropped-record reasons
- **AND** it MAY persist raw capture artifacts locally under `data/` for reproduction without re-fetching

#### Scenario: Optional authenticated scraping is supported
- **WHEN** guest-mode acquisition is insufficient to retrieve job results or full job detail content
- **THEN** the LinkedIn adapter can be configured to attach locally supplied session cookies and/or CSRF tokens to acquisition requests
- **AND** the system does not require credentials to be committed to the repository

### Requirement: Fixture-backed LinkedIn stub ingestion
The system SHALL support a local fixture-backed LinkedIn adapter for v1 so the ingestion boundary can be exercised without claiming real LinkedIn acquisition.

#### Scenario: Local LinkedIn fixture is ingested
- **WHEN** the user runs the LinkedIn ingestion command with a local source fixture file
- **THEN** the LinkedIn adapter reads the fixture, normalizes the postings into canonical job records, and passes them to the persistence and evaluation flow

#### Scenario: Live acquisition coexists with fixture ingestion
- **WHEN** the user runs the LinkedIn ingestion command in live acquisition mode
- **THEN** the adapter performs live acquisition and produces canonical job records with full job descriptions and stable identifiers when available
- **AND** fixture ingestion remains available for tests and offline debugging

## ADDED Requirements

### Requirement: Configurable LinkedIn extraction model
The system SHALL support a configurable extraction model for mapping LinkedIn pages or responses into canonical job fields.

#### Scenario: Extraction model validates against required canonical fields
- **WHEN** the LinkedIn adapter loads an extraction model configuration
- **THEN** the configuration is validated before ingestion begins
- **AND** invalid configurations fail fast with an actionable error

### Requirement: LLM-assisted fallback extraction
The system SHALL support an LLM-assisted fallback path for extracting canonical job fields when deterministic parsing fails due to LinkedIn payload drift.

#### Scenario: Deterministic parsing fails
- **WHEN** the adapter cannot extract required canonical job fields (such as title, company, link, or description) for a collected posting
- **THEN** the adapter can invoke a locally configured LLM endpoint to attempt extraction
- **AND** the adapter records whether the job was extracted deterministically or via the fallback path
