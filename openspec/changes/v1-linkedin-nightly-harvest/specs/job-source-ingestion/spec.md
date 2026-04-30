## ADDED Requirements

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
