## ADDED Requirements

### Requirement: Harvest orchestration is decomposed behind stable runtime behavior
The LinkedIn harvest implementation SHALL reorganize query planning, filter
evaluation, pacing/backoff, runtime state access, and result persistence behind
clear collaborators while preserving current harvest behavior.

#### Scenario: Harvest flow remains behaviorally stable
- **WHEN** the harvest internals are reorganized
- **THEN** the existing harvest command still honors schedule gating, resume
  state, filtering rules, and logging behavior
- **AND** those behaviors are implemented through explicit collaborators rather
  than one large mixed-responsibility module

### Requirement: Harvest operational helpers remain thin and external
The harvest operational helper modules SHALL remain external runtime entrypoints
that delegate into runtime-support collaborators rather than embedding harvest
domain logic directly.

#### Scenario: Operational helper behavior is preserved
- **WHEN** the refactor reorganizes cron installation, status, log tailing, or
  recent-job support
- **THEN** the operational helper entrypoints continue to expose the same
  runtime functions
- **AND** the helper modules remain thin wrappers over runtime-support classes
