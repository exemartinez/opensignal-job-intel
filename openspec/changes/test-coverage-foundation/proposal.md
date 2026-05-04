## Why

The repository has enough behavior to justify a broad architectural refactor, but the current test suite is concentrated in one file and does not protect the full codebase evenly. A refactor aimed at stronger object boundaries and removing duplicated logic needs a wider regression net first so structural changes can be made without silently changing CLI, harvesting, storage, or operational behavior.

## What Changes

- Add a refactor-safety testing foundation for the codebase, prioritizing high-risk orchestration and persistence modules before architecture changes begin.
- Define which subsystems require strong regression coverage versus lighter smoke coverage so the test effort stays aligned with refactor risk instead of chasing meaningless 100% line coverage on thin wrappers.
- Expand automated tests around CLI wiring, LinkedIn acquisition/harvest orchestration, repository state transitions, and operational helper behavior.
- Reorganize the test suite by subsystem so future refactor work can evolve modules without keeping all regression coverage in a single monolithic test file.
- Update repository documentation to reflect the supported environment bootstrap and test execution workflow needed to maintain the new coverage baseline.

## Capabilities

### New Capabilities
- `engineering-test-foundation`: Defines the regression protection, coverage tiers, and validation expectations required before broad architectural refactoring.

### Modified Capabilities
- `repo-docs`: README and repository guidance must document environment setup and the canonical test workflow that supports the refactor-safety coverage baseline.

## Impact

- Affected code: `tests/`, CLI wiring, LinkedIn acquisition/harvest modules, SQLite repository behavior, and operational helper surfaces that need regression coverage.
- Affected documentation: `README.md` and any repo-level testing guidance.
- Affected workflow: future refactor changes will depend on this change to establish a trusted automated safety net before major OO restructuring and deduplication work begins.
