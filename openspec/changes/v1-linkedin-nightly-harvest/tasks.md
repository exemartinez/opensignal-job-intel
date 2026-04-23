## 1. Schedule Config + Defaults

- [ ] 1.1 Add `config/extraction_schedule.template.yaml` with harvest window, pacing/jitter, backoff ceiling, and progress cadence
- [ ] 1.2 Add gitignored local override path (e.g., `profiles/extraction_schedule.yaml`) and document precedence
- [ ] 1.3 Add YAML parsing dependency and wire schedule config loading

## 2. Harvest Entrypoint

- [ ] 2.1 Add a dedicated harvest entrypoint (e.g., `harvest-linkedin`) separate from interactive ingestion
- [ ] 2.2 Ensure harvest uses low-noise stdout progress (dots + periodic summary lines)

## 3. Idempotent Harvesting (Skip Known IDs)

- [ ] 3.1 Add repository method to check existence of LinkedIn `external_job_id` efficiently
- [ ] 3.2 Update harvest flow to skip detail fetch for already-stored IDs

## 4. Strict Harvest Filters

- [ ] 4.1 Implement strict filter policy and missing-field policy for harvest mode (configurable)
- [ ] 4.2 Ensure US+Remote matches even when city/state is absent ("United States" + "Remote")

## 5. Posting Datetime Inference

- [ ] 5.1 Infer `post_datetime` when missing using `collected_at - post_age_days` and persist the inferred value
- [ ] 5.2 Add tests for post_datetime inference and storage behavior

## 6. Randomized Backoff + Stop Conditions

- [ ] 6.1 Implement randomized backoff on 429/403 up to a configurable ceiling (max 4 hours)
- [ ] 6.2 Decide and implement stop conditions (e.g., after N consecutive throttling events) and surface in diagnostics

## 7. Verification

- [ ] 7.1 Add a smoke test command / doc snippet for running harvest mode safely with low `max_jobs`
- [ ] 7.2 Run unit tests and ensure `openspec validate v1-linkedin-nightly-harvest` passes
