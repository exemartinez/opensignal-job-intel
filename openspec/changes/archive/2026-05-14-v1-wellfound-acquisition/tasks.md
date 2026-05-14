## 1. Scaffolding

- [x] 1.1 Add `JobSource.WELLFOUND` and ensure canonical normalization/dedupe rules cover it
- [x] 1.2 Add CLI command wiring (`ingest-wellfound`) in `main.py` and `src/runtime_entrypoints.py`

## 2. Wellfound Adapter (Fixture)

- [x] 2.1 Implement `WellfoundJsonFileAdapter` to load fixture rows and normalize into canonical `JobRecord`
- [ ] 2.2 Add a small representative fixture file under repo root for local development (ignored by default if needed) and/or test fixtures embedded in unit tests

## 3. Wellfound Adapter (Live)

- [x] 3.1 Implement `WellfoundScrapeAdapter` skeleton with diagnostics, pacing, and optional capture directory
- [x] 3.2 Implement Wellfound search/list page acquisition and job-id/link extraction
- [x] 3.3 Implement job detail fetch and deterministic extraction into canonical fields (company/title/description/link/external_job_id when available)
- [x] 3.4 Ensure `post_datetime` remains unset unless Wellfound provides a trustworthy timestamp
- [x] 3.5 Ensure compass filters are applied best-effort without fabricating missing fields
- [x] 3.6 Add human-like throttling (jitter/scroll) and early-stop block detection for restriction pages
- [x] 3.7 Derive `post_age_days` from `post_datetime` when the relative-age label is missing

## 4. Tests

- [x] 4.1 Add adapter unit tests for URL canonicalization and external id extraction (where available)
- [x] 4.2 Add adapter unit tests for fixture normalization into canonical `JobRecord`
- [x] 4.3 Add adapter unit tests for filter policy behavior (age/workplace/region when signals exist)
- [x] 4.4 Add CLI wiring tests mirroring the LinkedIn/Indeed patterns

## 5. Docs + Validation

- [x] 5.1 Update `README.md` with the new `ingest-wellfound` command and expected inputs
- [x] 5.2 Update `CHANGELOG.md` with the new capability and any dependency changes
- [x] 5.3 Run `openspec validate v1-wellfound-acquisition` and `python3.11 -m unittest discover -s tests -v`
