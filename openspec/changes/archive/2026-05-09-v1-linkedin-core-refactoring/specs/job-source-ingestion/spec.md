## ADDED Requirements

### Requirement: Ingestion responsibilities are decomposed into explicit collaborators
The LinkedIn ingestion implementation SHALL decompose acquisition behavior into
explicit collaborators for transport, extraction, diagnostics, query derivation,
and fixture/export handling while preserving the existing ingestion contract.

#### Scenario: Ingestion boundary remains stable during refactor
- **WHEN** the LinkedIn ingestion internals are reorganized
- **THEN** the application still acquires jobs through a source adapter boundary
- **AND** canonical job records are still produced before persistence and
  evaluation

### Requirement: Live and fixture ingestion share stable canonical serialization
The LinkedIn ingestion implementation SHALL keep fixture-backed and live
acquisition flows aligned on the canonical job-record shape used by persistence.

#### Scenario: Live export and fixture ingestion use the same record contract
- **WHEN** the system writes or reads a LinkedIn fixture/export artifact during
  ingestion
- **THEN** the artifact follows the canonical job-record structure used by the
  persistence layer
- **AND** refactoring the ingestion internals does not introduce a second
  LinkedIn-specific row shape

### Requirement: Ingestion reporting distinguishes inserts from updates
The LinkedIn ingestion command SHALL report whether persisted jobs were newly
inserted or updated in place because of deduplication.

#### Scenario: Existing LinkedIn rows are refreshed by a live or fixture ingest
- **WHEN** ingestion persists jobs whose dedupe keys already exist in SQLite
- **THEN** the command output reports the total persisted jobs and how many were
  updates rather than new rows
- **AND** machine-readable diagnostics expose inserted and updated counts
