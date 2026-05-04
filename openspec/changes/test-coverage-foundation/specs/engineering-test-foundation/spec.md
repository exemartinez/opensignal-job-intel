## ADDED Requirements

### Requirement: Refactor-safety regression baseline
The repository SHALL maintain automated regression coverage sufficient to protect broad architectural refactoring of behavior-rich modules.

#### Scenario: Critical modules receive direct regression coverage
- **WHEN** the repository prepares for a broad architectural refactor
- **THEN** behavior-rich modules such as CLI orchestration, LinkedIn acquisition/harvest flows, repository state management, and operational helper logic MUST have direct automated tests covering their supported behavior

### Requirement: Risk-tiered test coverage
The repository SHALL prioritize test depth according to module risk and side-effect complexity instead of applying a uniform coverage expectation to every file.

#### Scenario: Thin wrappers receive smoke coverage
- **WHEN** a module is primarily a thin entrypoint or dispatch wrapper
- **THEN** the automated suite MAY protect it with smoke coverage instead of exhaustive branch-by-branch tests

#### Scenario: Stateful orchestration receives behavior coverage
- **WHEN** a module coordinates filesystem state, subprocess calls, harvest loops, persistence, or request pacing
- **THEN** the automated suite MUST cover success paths, key failure paths, and state transitions relevant to supported behavior

### Requirement: Offline deterministic test execution
The repository SHALL keep the regression suite deterministic and runnable without external network or machine-level side effects.

#### Scenario: Side-effect-heavy modules use controlled test doubles
- **WHEN** tests exercise LinkedIn harvest orchestration, cron helper behavior, subprocess integration, or persistence flows
- **THEN** they use fakes, temporary files, or stubbed interactions instead of real LinkedIn network calls or real crontab modifications

### Requirement: Test suite organization follows subsystem boundaries
The repository SHALL organize regression tests so that major codebase subsystems can be validated independently during refactoring.

#### Scenario: Tests are grouped by architecture seam
- **WHEN** the regression suite grows beyond a single module
- **THEN** tests are organized by subsystem boundaries such as CLI, repository, extraction, acquisition, harvest orchestration, and operations helpers
