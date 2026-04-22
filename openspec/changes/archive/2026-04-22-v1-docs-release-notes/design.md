## Context

The repo now supports live LinkedIn acquisition (scraping) in addition to fixture-backed ingestion, plus compass-driven acquisition filters and additional stored metadata in SQLite. The current `README.md` still describes only the original fixture-backed behavior and does not document the new configuration surface (compass `search` fields, extraction spec location, auth/LLM env vars). There is also no changelog, which reduces discoverability on GitHub.

## Goals / Non-Goals

**Goals:**
- Update `README.md` so a new GitHub visitor can run the project in fixture mode or live mode without reading code.
- Document the minimal, local-first configuration knobs that matter: compass `search` fields, extraction spec default + override, and optional env vars.
- Add `CHANGELOG.md` with a stable structure: `## [Unreleased]` plus dated release entries and `### Added/Changed/Fixed/Removed` subsections.

**Non-Goals:**
- No changes to runtime behavior, scraping mechanics, or evaluation logic.
- No automated release tooling.

## Decisions

### Changelog format

Decision: adopt a SemVer-oriented changelog header with `## [Unreleased]` and dated entries, using `### Added/Changed/Fixed/Removed` subsections when applicable.

Rationale:
- Familiar to GitHub readers.
- Works without any packaging/release automation.

Alternative considered:
- Git-only history / release notes in PRs. Rejected (harder for users to skim).

### README content structure

Decision: keep the README concise and operational:
- One quickstart for fixture mode
- One quickstart for live mode
- A short configuration section for:
  - `profiles/professional_compass.json` fields (including `search.*`)
  - extraction spec default (`config/...template.json`) and local override path
  - optional env vars (`LINKEDIN_COOKIES`, `LINKEDIN_CSRF`, `LOCAL_LLM_BASE_URL`)
- A brief “what gets stored” section summarizing the SQLite fields relevant to filtering and review

Rationale:
- Minimizes scrolling while still being sufficient to run.

## Risks / Trade-offs

- [README drifts from implementation] -> Mitigation: keep it command-driven and update as part of future change workflows.
- [Changelog becomes stale] -> Mitigation: treat it as required output in future feature changes.

## Migration Plan

- Add `CHANGELOG.md`.
- Update `README.md` to reflect current behavior.

## Open Questions

- Should the changelog use dated entries only, or also include version tags once packaging is introduced?
