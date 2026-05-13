## Context

The current implementation has one real source path: LinkedIn. That path already follows a useful boundary:

- source-specific acquisition and extraction produce canonical `JobRecord` instances
- persistence stays in the shared SQLite repository
- evaluation stays in the shared compass evaluator
- CLI dispatch stays in `src/runtime_entrypoints.py`

Indeed should land through the same model. The key architectural question is not whether the system can ingest another source; it can. The question is whether the second source arrives through the existing source-adapter seam cleanly enough that future sources do not force repeated rewrites of the CLI, persistence, or evaluation layers.

## Goals / Non-Goals

**Goals**

- Add an Indeed acquisition path that produces canonical `JobRecord` values.
- Preserve the current shared persistence, evaluation, and reporting flow.
- Reuse the existing source-adapter pattern explicitly rather than adding an Indeed-only custom flow.
- Support both offline fixture-backed ingestion and live acquisition for Indeed.
- Support live Indeed acquisition through Selenium-backed browser automation.
- Keep source-specific diagnostics source-local while preserving canonical reporting at the runtime-entrypoint level.

**Non-Goals**

- Replacing the LinkedIn implementation.
- Redesigning the SQLite schema for Indeed-specific fields.
- Replacing shared persistence or evaluation behavior with browser-specific state.
- Generalizing every LinkedIn helper immediately if the abstraction is not yet clear.

## Decisions

### Decision: Indeed follows the existing source-adapter strategy seam

Indeed will be implemented as another `JobSourceAdapter` participant that returns canonical `JobRecord` values to the shared ingestion service.

Rationale:

- The adapter seam already exists and has test coverage.
- A second source is the right time to prove the seam instead of bypassing it.
- This keeps persistence and evaluation source-agnostic.

### Decision: Indeed starts without a dedicated extraction-spec file

The first Indeed implementation will use source-local deterministic parsing in
`src/indeed_acquisition.py` rather than introducing a separate extraction-spec
file on day one.

Rationale:

- The current scope is one additional source, not a generic extraction-spec
  framework for all platforms.
- A source-local parser is enough to establish the adapter boundary.
- If Indeed HTML drift later justifies a dedicated spec, that can be added in a
  follow-up change.

### Decision: Keep source-local acquisition and extraction code separated from shared ingestion flow

Indeed-specific network acquisition, extraction rules, and diagnostics should live in an Indeed-focused source module rather than being mixed into the LinkedIn implementation.

Rationale:

- LinkedIn and Indeed will differ in HTML structure, URL patterns, and filter opportunities.
- Mixing them would create the wrong abstraction.
- The shared contract is the canonical job record, not a shared HTML parser.

### Decision: Share only the source-agnostic pieces

Shared behavior should be reused only where the concept is genuinely common:

- canonical persistence
- evaluation
- ingestion-result reporting
- adapter contract
- common fixture/export shape when appropriate

Rationale:

- The right abstraction boundary is the canonical domain model, not a forced common scraper.
- Shared helpers should emerge from real overlap, not assumption.

### Decision: Add an Indeed command surface through the existing runtime entrypoint

The runtime should gain an Indeed ingestion command through `src/runtime_entrypoints.py` rather than introducing a second top-level launcher.

Rationale:

- The repository already has one approved CLI surface.
- Keeping all source ingestion commands under the same entrypoint preserves discoverability and testing patterns.

### Decision: Indeed live acquisition uses Selenium-backed browser automation

The live Indeed path will use Selenium with a local browser session instead of
raw `urllib` requests.

Rationale:

- Indeed is challenge-protected behind Cloudflare, and direct HTTP requests are
  returning 403 challenge pages rather than parsable search HTML.
- Browser-backed navigation preserves the existing canonical adapter contract
  while making the live path viable on a developer machine.
- The deterministic extraction layer can stay source-local and unchanged even
  when transport moves from raw HTTP to a browser session.
- Live search-card extraction must validate the href-derived `jk` and persist
  only canonical `https://www.indeed.com/viewjob?jk=...` links so placeholder
  ids or mismatched card metadata do not enter the database.

## Proposed Structure

The minimal target for this change is:

- keep `src/core_domain_inputs.py` as the canonical ingestion boundary
- keep `src/runtime_entrypoints.py` as the CLI/runtime dispatcher
- add a dedicated Indeed source module under `src/`
- factor shared acquisition/extraction helpers only if the abstraction is already clear from both sources

Expected shape:

- `src/indeed_acquisition.py`
  - fixture-backed Indeed adapter
  - live Indeed Selenium adapter
  - Indeed diagnostics
  - Indeed fixture/export normalization
  - Indeed query/filter helpers where needed
  - deterministic Indeed search/detail parsing
  - reusable browser session management for Indeed live scraping

If the implementation reveals a clear cross-source helper seam, a small shared collaborator can be introduced later in this change. That should be done only when both sources genuinely use the same behavior.

## Risks / Trade-offs

- **Risk: accidental duplication of the LinkedIn adapter**
  - Mitigation: preserve the adapter contract, but only reuse source-agnostic behavior.

- **Risk: premature multi-source abstraction**
  - Mitigation: do not create a generic scraper framework unless Indeed and LinkedIn demonstrably need the same collaborator.

- **Risk: CLI sprawl**
  - Mitigation: keep Indeed under the same runtime entrypoint style and argument conventions as LinkedIn.

- **Risk: source-specific parser fragility**
  - Mitigation: add deterministic fixture/extraction tests for Indeed before relying on live acquisition behavior.

- **Risk: local browser prerequisites**
  - Mitigation: document the Selenium dependency, supported browser path, and Safari remote automation requirement for macOS.

## Migration Plan

1. Add OpenSpec requirements for Indeed acquisition and the shared ingestion surface.
2. Introduce the Indeed source module and fixture-backed adapter first.
3. Add live Indeed browser-backed acquisition and deterministic extraction.
4. Wire the new command through `src/runtime_entrypoints.py`.
5. Add source-specific tests plus shared CLI/persistence coverage.
6. Update README and changelog.

## Open Questions

- Should the command be `ingest-indeed`, or should the CLI move toward a source-parameterized `ingest` command in a later change?
- Which local browser should be the default transport for developers on this machine, and what fallback should be documented when Safari remote automation is disabled?
