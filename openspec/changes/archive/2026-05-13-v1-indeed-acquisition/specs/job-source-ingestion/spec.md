## MODIFIED Requirements

### Requirement: Source-specific ingestion boundary
The system SHALL isolate source acquisition behind a source adapter contract so
that LinkedIn, Indeed, and future sources can be implemented without coupling
the application to a specific acquisition mechanism or an official platform API.

#### Scenario: Indeed ingestion uses the adapter contract
- **WHEN** the application ingests jobs from Indeed
- **THEN** it invokes an Indeed-specific adapter through the source adapter
  boundary rather than calling Indeed acquisition logic directly from the CLI or
  repository layers

#### Scenario: Additional sources reuse the canonical ingestion flow
- **WHEN** a new source is introduced after LinkedIn and Indeed
- **THEN** the application can add a new source adapter that produces canonical
  job records without requiring a source-specific storage schema or evaluation
  flow
