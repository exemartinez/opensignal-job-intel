## 1. Structural planning

- [x] 1.1 Confirm the final `src/` package/import shape and decide whether the
      runtime package will be named directly `src` or wrapped by a repo-specific
      Python package.
- [x] 1.2 Review `docs/linkedin_core_focused_class_diagram.puml` and
      `docs/ingest_and_harvest_flow_diagram.puml` against the current code and
      adjust them if implementation sequencing requires clearer boundaries.

## 2. Collaborator extraction in current layout

- [x] 2.1 Extract or tighten explicit collaborators for LinkedIn acquisition
      concerns: transport/fetch behavior, diagnostics recording, and fixture/export
      serialization.
- [x] 2.2 Extract or tighten explicit collaborators for LinkedIn extraction and
      filtering concerns: deterministic extraction, fallback extraction, query
      derivation, and filter evaluation.
- [x] 2.3 Extract or tighten explicit collaborators for harvest orchestration:
      query planning, runtime state transitions, pacing/backoff policy, and
      persistence coordination.
- [x] 2.4 Extract or tighten explicit collaborators for runtime operations:
      path resolution, cron block generation, process/status handling, and
      monitoring helpers.

## 3. Runtime-entrypoint cleanup

- [x] 3.1 Make every runtime entrypoint a thin delegating wrapper over
      class-owned behavior.
- [x] 3.2 Add or update module-level docstrings in the refactored modules with
      responsibility text and author attribution to `Ezequiel H. Martinez`.

## 4. Package move

- [x] 4.1 Move the implementation from `opensignal_job_intel/` toward the
      approved `src/` layout in small validated slices.
- [x] 4.2 Rewire imports, CLI composition, and runtime helpers to the new module
      locations without changing command behavior.

## 5. Validation and documentation

- [x] 5.1 Keep `python3.11 -m unittest discover -s tests -v` green throughout
      the refactor and rerun it after each structural slice.
- [x] 5.2 Update `ARCHITECTURE.md`, `README.md`, and curated UML artifacts to
      reflect the final structure as the refactor lands.
- [x] 5.3 Run `env PATH=/usr/local/opt/node@20/bin:$PATH openspec validate
      v1-linkedin-core-refactoring` before implementation review or archive.
- [x] 5.4 Clarify ingestion persistence reporting so CLI output and diagnostics
      distinguish newly inserted jobs from updated deduplicated rows.
