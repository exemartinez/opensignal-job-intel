## Tasks

- [ ] Add a new runtime command for unattended multi-source harvesting (LinkedIn, Indeed, Wellfound) in `src/runtime_entrypoints.py`.
- [ ] Implement a Linux-focused preflight validator for harvest runtime dependencies and required local files.
- [ ] Add source enable/disable configuration handling for unattended runs (schedule/config-driven and/or CLI flags).
- [ ] Implement per-source execution isolation so one source failure does not abort the full harvest run.
- [ ] Emit consolidated run summary with per-source status, counters, and structured errors.
- [ ] Keep `harvest-linkedin` behavior backward compatible and covered by regression tests.
- [ ] Add unit tests for preflight checks, isolation behavior, and summary output schema.
- [ ] Update `openspec/specs/batch-harvesting/spec.md` to include multi-source unattended harvesting semantics.
- [ ] Update documentation (`README.md`, `AGENTS.md`) with Linux/pop!_OS operational guidance and new harvest command usage.
- [ ] Add a changelog entry describing Linux support and multi-source unattended harvest behavior.

## Execution Plan

1. Implement preflight + command wiring first.
2. Add source isolation + summary/reporting.
3. Extend tests for new path and regressions.
4. Update spec/docs/changelog.
5. Run validation (`openspec validate`, test suite) and finalize.

