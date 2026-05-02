# job-source-ingestion Specification

## Purpose
TBD - created by archiving change v1-linkedin-ingestion-storage. Update Purpose after archive.
## Requirements
### Requirement: Canonical job normalization
The system SHALL normalize collected job postings into a canonical job record before passing them to persistence or downstream workflows.

#### Scenario: Source job is normalized before storage
- **WHEN** a source adapter returns a collected job posting
- **THEN** the system produces a canonical record containing source, company, title, description, source link, collected timestamp, and any available source identifier, post datetime, or salary text before storage is attempted

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

#### Scenario: Additional sources can be added without changing the canonical ingestion flow
- **WHEN** a new job source is introduced after LinkedIn
- **THEN** the application can add a new source adapter that produces canonical job records without requiring a source-specific storage schema

### Requirement: Fixture-backed LinkedIn stub ingestion
The system SHALL support a local fixture-backed LinkedIn adapter for v1 so the ingestion boundary can be exercised without claiming real LinkedIn acquisition.

#### Scenario: Local LinkedIn fixture is ingested
- **WHEN** the user runs the LinkedIn ingestion command with a local source fixture file
- **THEN** the LinkedIn adapter reads the fixture, normalizes the postings into canonical job records, and passes them to the persistence and evaluation flow

#### Scenario: Live acquisition coexists with fixture ingestion
- **WHEN** the user runs the LinkedIn ingestion command in live acquisition mode
- **THEN** the adapter performs live acquisition and produces canonical job records with full job descriptions and stable identifiers when available
- **AND** fixture ingestion remains available for tests and offline debugging

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

### Requirement: Compass-driven acquisition filters
The system SHALL derive acquisition filtering behavior from the professional compass JSON so the user can scope collection by time, workplace mode, and geography without adding CLI flags.

#### Scenario: User configures a maximum post age
- **WHEN** the compass defines `search.max_post_age_days`
- **THEN** the LinkedIn adapter excludes jobs older than that age when a posting age signal can be extracted

#### Scenario: User configures workplace modes
- **WHEN** the compass defines `search.workplace_types`
- **THEN** the LinkedIn adapter scopes acquisition to those workplace modes (remote/hybrid/onsite) when the source can be constrained or extracted reliably

#### Scenario: User configures regions
- **WHEN** the compass defines `search.regions`
- **THEN** the LinkedIn adapter scopes acquisition to those regions (e.g., US, LATAM, EMEA, AR) when the source can be constrained or extracted reliably

### Requirement: Posting age extraction
The system SHALL attempt to extract posting age signals from LinkedIn pages when available.

#### Scenario: Posting age text is present
- **WHEN** a LinkedIn job detail page contains a relative posting age (e.g., "2 months ago")
- **THEN** the adapter captures the raw posting age text
- **AND** the adapter computes a best-effort normalized age value for filtering

### Requirement: Harvest mode is incremental and idempotent
The system SHALL support a harvest mode that incrementally discovers recent LinkedIn job postings and avoids refetching details for jobs already stored.

#### Scenario: Harvest skips already-stored job details
- **WHEN** harvest mode discovers a LinkedIn job identifier from search results
- **AND** the job identifier already exists in the local SQLite database
- **THEN** the system does not fetch the job detail page again
- **AND** it proceeds to the next candidate posting

### Requirement: Harvest queries come from the professional compass
The system SHALL derive harvest queries from the professional compass roles already used by the current live acquisition flow.

#### Scenario: Harvest reuses compass role queries
- **WHEN** the nightly harvester builds LinkedIn search queries
- **THEN** it uses the target role signals from the professional compass
- **AND** it does not require a separate harvest-specific query list in this change

### Requirement: Strict filtering policy for harvesting
The system SHALL support a strict filtering policy for harvest mode so that the database is populated with postings that match the compass constraints.

#### Scenario: Harvest applies remote-only and region filters
- **WHEN** the professional compass indicates remote-only and a region scope (e.g., US)
- **THEN** harvest mode stores only postings that match those constraints
- **AND** a posting that clearly indicates "United States" and "Remote" is considered a match even if city/state is absent

#### Scenario: Harvest supports Canada as a named region
- **WHEN** the professional compass includes `CANADA` in `search.regions`
- **THEN** the harvester builds LinkedIn search requests using a Canada location label
- **AND** postings whose extracted location clearly indicates Canada are treated as a regional match

#### Scenario: Harvest applies a parametric recency window
- **WHEN** the professional compass defines `search.max_post_age_days`
- **THEN** harvest mode drops postings with extracted `post_age_days` greater than that value

#### Scenario: Harvest stops scanning a stale result stream
- **WHEN** search results have reached postings older than the configured recency window
- **AND** N consecutive search pages yield no new LinkedIn job IDs
- **THEN** the harvester stops scanning deeper into that search stream for the current run

#### Scenario: Harvest stops scanning an exhausted narrow search
- **WHEN** a narrow search keeps yielding pages whose LinkedIn job IDs are all already known
- **AND** 5 consecutive search pages yield no new LinkedIn job IDs
- **THEN** the harvester stops scanning deeper into that search stream for the current run even if no stale age signal was extracted from those pages

#### Scenario: Missing filter fields are handled explicitly
- **WHEN** harvest mode cannot extract required filter signals (posting age, location/region, or workplace type)
- **THEN** the system applies an explicit policy (configured for harvest mode) to either drop the posting or keep it
- **AND** the decision and reason are reflected in diagnostics

### Requirement: Inferred posting datetime
The system SHALL infer a posting datetime when the source does not provide `post_datetime` but the adapter can extract a posting age.

#### Scenario: post_datetime is inferred from post age
- **WHEN** a posting has `post_datetime` missing
- **AND** the adapter extracted `post_age_days`
- **THEN** the system infers an expected `post_datetime` as `collected_at - post_age_days` (date-level precision)
