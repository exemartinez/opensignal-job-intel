## Why

The README no longer reflects the repository's current capabilities after implementing live LinkedIn acquisition, compass-driven filters, and additional stored fields. A structured changelog is also needed so GitHub visitors can quickly understand what changed and when.

## What Changes

- Update `README.md` to accurately describe current CLI modes (fixture vs live), configuration inputs (professional compass + extraction spec), acquisition diagnostics, and optional local-only auth/LLM configuration.
- Add `CHANGELOG.md` following a SemVer-oriented format (Unreleased + dated release entries) that documents the notable changes introduced by `v1-linkedin-acquisition`.

## Capabilities

### New Capabilities

- `repo-docs`: Repository documentation and release notes expectations (README currency + changelog format and update rules).

### Modified Capabilities

- None.

## Impact

- Affected files: `README.md`, new `CHANGELOG.md`, and a new baseline spec under `openspec/specs/repo-docs/` (via delta spec in this change).
- No runtime behavior changes.
