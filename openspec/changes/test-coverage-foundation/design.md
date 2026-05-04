## Context

The repository currently has a useful but uneven regression net: the existing test suite exercises core ingestion, extraction, harvest state, and SQLite behaviors, but most of that protection lives in a single `tests/test_ingestion.py` module. Large orchestration modules such as `cli.py`, `linkedin_acquire.py`, `linkedin_harvest.py`, `linkedin_harvest_ops.py`, and `repositories/sqlite_jobs.py` carry a disproportionate share of refactor risk, while thin operational entrypoints and some support modules have little or no direct coverage.

The next planned engineering step is a broad architectural refactor focused on stronger object-oriented boundaries and removal of duplicated logic. That kind of work is unsafe without a wider and more intentionally structured regression net. This change therefore establishes the test foundation first, without coupling it to the refactor implementation itself.

Constraints:
- Tests must remain deterministic and runnable offline.
- No real LinkedIn network calls, cron modifications, or external process side effects should be required for regression coverage.
- Coverage effort must prioritize behavior-rich modules rather than chasing line-count vanity on tiny wrappers.

## Goals / Non-Goals

**Goals:**
- Define a refactor-safety testing baseline for the codebase before broad architectural changes begin.
- Expand regression coverage around high-risk modules: CLI wiring, LinkedIn acquisition/harvest orchestration, repository state transitions, and operational helper behavior.
- Reorganize tests by subsystem so failures map more clearly to architecture boundaries.
- Document the canonical setup and test workflow needed to preserve the new coverage baseline.

**Non-Goals:**
- Performing the architecture refactor itself.
- Rewriting production modules solely to make them more elegant during this change.
- Requiring real network, real cron scheduling, or browser automation in the automated suite.
- Treating 100% line coverage on thin wrapper files as a primary objective.

## Decisions

### Use risk-tiered coverage rather than uniform line-coverage targets

Decision: classify modules into critical, moderate, and smoke-only coverage tiers.

Rationale:
- The refactor risk is concentrated in orchestration, persistence, and stateful flow modules.
- Thin entrypoints can often be protected by a small number of import/dispatch smoke tests.
- This keeps the work aligned with behavioral safety rather than vanity metrics.

Alternatives considered:
- Pursue uniform 100% line coverage across the repo. Rejected because it would spend effort on trivial wrappers while leaving less time for failure-path and state-transition coverage in the high-risk modules.

### Organize tests by subsystem instead of keeping a single monolithic test module

Decision: split the current suite into subsystem-oriented test files, such as CLI, repository, extraction, harvest orchestration, and operational helper tests.

Rationale:
- A broad refactor will be easier to validate when tests map to module boundaries.
- Failure localization is stronger when architecture seams have corresponding test files.

Alternatives considered:
- Keep all tests in `tests/test_ingestion.py`. Rejected because growth in that file would make targeted maintenance and refactor validation harder.

### Use fakes and temp-backed state for orchestration coverage

Decision: cover harvest/acquisition/ops behavior through fake fetchers, temporary SQLite files, stubbed subprocess/crontab interactions, and temp filesystem state.

Rationale:
- These modules are behavior-rich but also side-effect heavy.
- Controlled fakes give repeatable coverage without introducing network or machine-level dependencies.

Alternatives considered:
- End-to-end tests against live LinkedIn or the system crontab. Rejected because they are nondeterministic and unsuitable as a refactor safety net.

### Capture repository-level testing workflow in documentation

Decision: update repo documentation so environment bootstrap and the canonical test command are explicit parts of the supported engineering workflow.

Rationale:
- A stronger test foundation is only useful if contributors can reliably run it.
- The README is already the repo’s primary operational guide.

## Risks / Trade-offs

- [Coverage work becomes open-ended] → Mitigation: define coverage tiers and prioritize high-risk modules before adding lower-value cases.
- [Tests may expose design seams that are awkward to exercise] → Mitigation: prefer fakes and targeted seams, and defer production refactor work to the follow-on architecture change rather than mixing concerns here.
- [Broad orchestration tests become brittle] → Mitigation: assert stable externally visible behavior and persisted state transitions, not incidental implementation details.
- [Documentation drifts from the actual test workflow] → Mitigation: keep README setup/test commands aligned with the commands used in validation for this change.
