## 1. Coverage Audit and Test Suite Structure

- [ ] 1.1 Audit current test coverage by module and identify critical, moderate, and smoke-only coverage tiers
- [ ] 1.2 Split the current monolithic LinkedIn-oriented test module into subsystem-oriented test files
- [ ] 1.3 Establish shared test helpers/fixtures needed for deterministic offline testing across subsystems

## 2. Critical Regression Coverage

- [ ] 2.1 Add CLI wiring tests for supported ingestion and harvest command flows
- [ ] 2.2 Add regression tests for `linkedin_acquire.py` covering URL construction, filter behavior, and failure paths
- [ ] 2.3 Add regression tests for `linkedin_harvest.py` covering query planning, stop conditions, state transitions, and throttle/error handling
- [ ] 2.4 Add regression tests for `linkedin_harvest_ops.py` covering cron block generation, schedule/config path behavior, and operational helper workflows
- [ ] 2.5 Add repository tests for additive schema evolution, harvest state persistence, and known-ID lookup behavior

## 3. Moderate and Smoke Coverage

- [ ] 3.1 Add focused edge-case tests for `models.py`, `evaluation.py`, `compass.py`, and `linkedin_extraction.py`
- [ ] 3.2 Add smoke tests for source-local Python entrypoints so dispatch/import wiring is protected without overfitting wrapper internals
- [ ] 3.3 Add focused tests for any remaining support modules whose behavior would materially affect the planned architecture refactor

## 4. Documentation and Validation

- [ ] 4.1 Update README test/setup guidance so it matches the supported contributor bootstrap and validation workflow
- [ ] 4.2 Run `python3.11 -m unittest discover -s tests -v`
- [ ] 4.3 Run `openspec change validate test-coverage-foundation`
