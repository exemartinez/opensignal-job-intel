## 1. Acquisition Scaffolding

- [x] 1.1 Add a live LinkedIn acquisition adapter (keep existing JSON fixture adapter)
- [x] 1.2 Derive a small set of LinkedIn search queries from `ProfessionalCompass` (compass-only input)
- [x] 1.3 Add acquisition diagnostics output (requests, parse failures, drop reasons)

## 2. Parsing / Extraction Model

- [x] 2.1 Define the JSON extraction spec format (required canonical fields + extraction rules)
- [x] 2.2 Implement extraction spec validation (fail fast with actionable errors)
- [x] 2.3 Implement deterministic extraction from acquired payloads into canonical `JobRecord`

## 3. Full Description Acquisition

- [x] 3.1 Implement two-stage acquisition: search results -> job detail fetch
- [x] 3.2 Ensure canonical `description` is populated with full job text and `link` is canonicalized
- [x] 3.3 Capture stable identifiers when available (`external_job_id`)

## 4. Authenticated Scraping (Optional)

- [x] 4.1 Support attaching locally supplied cookies/CSRF to requests (no repo-stored secrets)
- [x] 4.2 Add conservative request pacing and clear error messages for blocked/rate-limited responses

## 5. Raw Capture + Debuggability

- [x] 5.1 Add optional raw capture persistence under `data/` (gitignored) for failing pages/responses
- [x] 5.2 Add a fixture regeneration/debug path (save captures that can be re-ingested offline)

## 6. LLM Fallback Extraction

- [x] 6.1 Implement an LLM client for a locally configured endpoint (for fallback extraction only)
- [x] 6.2 Invoke LLM fallback when deterministic extraction cannot produce required canonical fields
- [x] 6.3 Record extraction mode (deterministic vs LLM fallback) in diagnostics

## 7. CLI + Tests

- [x] 7.1 Update `ingest-linkedin` CLI to support live acquisition mode while retaining `--source-file` fixture mode
- [x] 7.2 Add tests for extraction spec validation and deterministic extraction on representative captured payloads
- [x] 7.3 Add a smoke test path to confirm SQLite stores full descriptions and dedupe still works
