## 1. Schedule Config + Defaults

- [x] 1.1 Add `config/extraction_schedule.template.yaml` with harvest window, pacing/jitter, backoff ceiling, and progress cadence
- [x] 1.2 Add gitignored local override path (e.g., `profiles/extraction_schedule.yaml`) and document precedence
- [x] 1.3 Add YAML parsing dependency and wire schedule config loading

## 2. Harvest Entrypoint

- [x] 2.1 Add a dedicated `harvest-linkedin` orchestrator entrypoint separate from interactive ingestion
- [x] 2.2 Persist harvest run state so nightly runs resume where they left off (query position, throttling memory, last success, per-query yield)
- [x] 2.3 Ensure harvest emits verbose timestamped request/event logs plus periodic summary lines

## 3. Idempotent Harvesting (Skip Known IDs)

- [x] 3.1 Add repository method to check existence of LinkedIn `external_job_id` efficiently
- [x] 3.2 Update harvest flow to skip detail fetch for already-stored IDs

## 4. Strict Harvest Filters

- [x] 4.1 Reuse professional-compass roles as the harvest query source
- [x] 4.2 Stop scanning a search stream after the run encounters postings older than the recency window and N consecutive search pages produce no new IDs
- [x] 4.3 Ensure US+Remote matches even when city/state is absent ("United States" + "Remote")

## 5. Posting Datetime Inference

- [x] 5.1 Infer `post_datetime` when missing using `collected_at - post_age_days` and persist the inferred value
- [x] 5.2 Add tests for post_datetime inference and storage behavior

## 6. Backoff + Stop Conditions

- [x] 6.1 Implement exponential backoff on HTTP 403 only, with sticky caution for the remainder of the run and a configurable ceiling (max 4 hours)
- [x] 6.2 Log non-403 request failures and continue without treating them as throttling events
- [x] 6.3 Surface age-cutoff, empty-page stop decisions, and throttling state in diagnostics/logs

## 7. Verification

- [x] 7.1 Add a smoke test command / doc snippet for running harvest mode safely under a nightly window (e.g., 00:00 to 08:00) with low `max_jobs`
- [x] 7.2 Run unit tests and ensure `openspec validate v1-linkedin-nightly-harvest` passes
- [x] 7.3 Keep repo-owned operational entrypoints as Python files under `opensignal_job_intel/sources/` and document the supported commands
