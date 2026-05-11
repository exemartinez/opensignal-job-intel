## ADDED Requirements

### Requirement: Curated architecture diagrams are maintained
The repository SHALL maintain curated plain-text UML artifacts that explain the
LinkedIn core structure and the ingest/harvest runtime flow during the refactor.

#### Scenario: Contributor can inspect focused structure and flow
- **WHEN** a contributor needs to understand the LinkedIn refactor target
- **THEN** the repository provides a focused class diagram and an ingest/harvest
  flow diagram under `docs/`
- **AND** those diagrams remain aligned with the intended architectural
  boundaries of the refactor

### Requirement: Architecture docs explain the refactor boundary rules
The repository SHALL maintain architecture-facing documentation that explains
the responsibility boundaries, runtime-entrypoint rules, OO expectations, and
behavior-preserving refactor constraints for the LinkedIn core surface.

#### Scenario: Refactor guidance is discoverable
- **WHEN** a contributor reads the repository architecture guidance
- **THEN** they can identify the intended responsibility boundaries, the role of
  runtime entrypoints, and the requirement to preserve current behavior while
  refactoring
