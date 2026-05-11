## Context

The current LinkedIn implementation now lives under `src/`, but the same
constraints remain: domain logic, transport, orchestration, parsing, state
persistence, cron/runtime helpers, and runtime dispatch must stay separated
enough that future changes do not collapse back into mixed-responsibility
modules.

The repository now has a regression foundation from the archived
`v1-test-coverage-foundation` change. That test coverage protects the current
CLI flows, harvest behaviors, runtime helper behaviors, repository semantics,
and key LinkedIn acquisition/extraction paths. This refactor is therefore a
structural change with a strong "preserve behavior first" constraint.

The target architectural direction is intentionally narrow:

- move the package root toward `src/`
- collapse the current multi-module LinkedIn surface into a small number of
  responsibility-driven modules
- make the main runtime behavior class-owned rather than distributed across
  free functions and mixed-responsibility modules
- keep runtime entrypoints thin

The curated diagrams under `docs/` are part of the design input:

- `docs/linkedin_core_focused_class_diagram.puml`
- `docs/ingest_and_harvest_flow_diagram.puml`

## Goals / Non-Goals

**Goals:**

- Preserve current ingestion, harvest, persistence, and runtime-entrypoint
  behavior while changing internal structure.
- Reorganize the implementation into a `src/` package root with a small set of
  top-level responsibility modules:
  - `core_domain_inputs`
  - `linkedin_acquisition`
  - `linkedin_extraction_filtering`
  - `harvest_orchestration`
  - `persistence_runtime_ops`
  - `runtime_entrypoints`
- Replace duplicated acquisition/harvest logic with explicit collaborators for
  query derivation, filtering, diagnostics, runtime path resolution, and cron
  entry construction.
- Make ingestion persistence reporting explicit enough to distinguish inserts
  from updates when deduplication causes an existing row to be refreshed.
- Keep module-level docstrings on refactored modules with concise
  responsibility text and author attribution to `Ezequiel H. Martinez`.
- Keep the refactor reviewable through curated UML artifacts and small
  behavior-preserving commits.

**Non-Goals:**

- Changing the supported CLI commands or command semantics.
- Changing the SQLite schema or dedupe semantics beyond what is required to
  preserve current behavior during the move.
- Introducing new external services or dependencies for acquisition, scheduling,
  or persistence.
- Replacing cron with an internal scheduler.
- Treating "100% OO" as a reason to remove simple pure functions that remain
  clearer as pure functions.

## Decisions

### Decision: Use `src` as the final package root

The implementation SHALL live in a direct Python package named `src` with this
module shape:

- `src/__init__.py`
- `src/core_domain_inputs.py`
- `src/linkedin_acquisition.py`
- `src/linkedin_extraction_filtering.py`
- `src/harvest_orchestration.py`
- `src/persistence_runtime_ops.py`
- `src/runtime_entrypoints.py`

Rationale:

- This matches the approved target and the current implementation.
- It keeps package boundaries aligned with the curated diagrams and tests.
- It removes the dead compatibility surface instead of preserving duplicate paths.

Alternatives considered:

- Keep the old package as a long-lived compatibility layer:
  rejected because it keeps duplicate entrypoints and stale ownership boundaries alive.

### Decision: Use six top-level responsibility modules as the main structural target

The target `src/` root SHOULD hold a small number of modules that reflect the
major system boundaries:

- `core_domain_inputs`
- `linkedin_acquisition`
- `linkedin_extraction_filtering`
- `harvest_orchestration`
- `persistence_runtime_ops`
- `runtime_entrypoints`

Rationale:

- This is strict enough to prevent the current fragmentation from reappearing.
- It maps directly to the curated class diagram and the user’s intended
  structure.
- It forces responsibility decisions rather than letting naming alone drive the
  reorganization.

Alternatives considered:

- Keep many small files under `sources/`:
  rejected because the current issue is already mixed ownership across too many
  module boundaries.
- Use nested subpackages for every concern:
  deferred because the first refactor objective is clarity, not maximum
  granularity.

### Decision: Keep runtime entrypoints as thin wrappers over class-owned behavior

Runtime entrypoints MAY remain executable modules, but they MUST delegate
immediately into classes in `runtime_entrypoints` or `persistence_runtime_ops`.

Rationale:

- The runtime still needs concrete entrypoints for cron and CLI execution.
- Python entrypoint modules are normal, but business logic in those files is
  not.
- This preserves operational usability without polluting the core model.

Alternatives considered:

- Static-class-only pseudo scripts:
  rejected as a literal design requirement because Python entrypoint modules are
  still needed by the runtime environment.
- Keep mixed logic in wrappers:
  rejected because it recreates the current problem.

### Decision: Favor composition-heavy collaborators over deep inheritance

The refactor SHOULD extract named collaborators for:

- query planning
- filter evaluation
- transport/fetch behavior
- diagnostics recording
- harvest pacing and throttle policy
- cron block creation
- repo/runtime path resolution

Rationale:

- These concerns already exist and are duplicated or entangled.
- They are composable behaviors, not a strong inheritance hierarchy.
- This matches the repository architecture guidance.

Alternatives considered:

- Use inheritance for all shared behavior:
  rejected because most of the duplication is behavioral composition, not
  subtype polymorphism.

### Decision: Treat UML artifacts as maintained review aids, not generated truth

The curated diagrams in `docs/` SHOULD be maintained alongside the refactor.
Generated diagrams from `pyreverse` remain useful for discovery but are not the
authoritative architectural view.

Rationale:

- Generated diagrams expose code relationships but not intended boundaries.
- The curated diagrams encode the boundary model that the refactor is trying to
  achieve.

Alternatives considered:

- Use only generated UML:
  rejected because it is too noisy and does not explain script/runtime
  separation.

## Risks / Trade-offs

- [Import churn during package move] -> Stage the refactor so collaborator
  extraction lands before the `src/` move, and run the full test suite after
  each structural slice.
- [Overconstraining the system to six files too early] -> Use the six-module
  target as the design boundary, but sequence internal moves carefully so the
  code stays understandable while converging there.
- [OO rewrite creates unnecessary indirection] -> Keep pure logic as pure logic
  where that is clearer, and move stateful behavior into classes only when the
  responsibility is real.
- [Operational scripts regress during runtime-helper consolidation] -> Keep
  direct regression coverage on cron/status/log entrypoints and preserve their
  observable behavior before renaming modules.
- [Curated docs drift from code] -> Update the UML artifacts as each refactor
  slice lands, rather than treating them as a one-time planning artifact.

## Migration Plan

1. Create the delta specs and task list for the structural target.
2. Introduce or tighten the main collaborator classes in the current layout.
3. Reduce duplication inside acquisition, harvest orchestration, and runtime
   ops while preserving imports and entrypoint behavior.
4. Rehome modules into `src/` with the six target responsibility files.
5. Update CLI wiring and runtime wrappers to import from the new locations.
6. Update README and architecture documentation to reflect the new structure.
7. Run the full test suite and OpenSpec validation after each meaningful slice.

Rollback strategy:

- Because this is a structural refactor, rollback is expected to happen at the git
  commit level rather than through runtime feature flags.
- Each step should therefore stay small enough that reverting a single commit
  restores the prior stable state.

## Open Questions

- Should `cli.py` remain a standalone module outside the six responsibility
  modules, or be absorbed entirely into `runtime_entrypoints`?
- Should `services.py` survive as a separate composition boundary, or should
  its behavior be redistributed into the six target modules during the move?
