## MODIFIED Requirements

### Requirement: Six-module core architecture target
The refactor SHALL keep a direct `src/` package root organized around a small
set of shared runtime/domain modules plus source-local acquisition modules when
additional platforms require their own adapters.

#### Scenario: New source module fits the shared runtime architecture
- **WHEN** a contributor adds another acquisition source such as Indeed
- **THEN** the source can introduce a source-local acquisition module under
  `src/`
- **AND** shared runtime behavior, persistence, and evaluation remain owned by
  the existing shared runtime/domain modules
