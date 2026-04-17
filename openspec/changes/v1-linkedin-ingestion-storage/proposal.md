## Why

The repository needs a concrete first increment that turns the current spec-only setup into a usable foundation for collecting, storing, and triaging jobs without prematurely committing to scraping, browser automation, or a partner-gated LinkedIn API. This change establishes the minimum stable boundaries for source ingestion, SQLite persistence, and a first-pass candidate-compass evaluation flow so later qualification, ranking, and multi-source expansion can build on a clean base.

## What Changes

- Define a canonical job record for normalized job postings, including source metadata, core job fields, collection timestamps, and human workflow status markers.
- Add a professional compass input profile that captures the candidate context and drives the first user-facing qualification workflow.
- Introduce a source-ingestion boundary that accepts LinkedIn as the first source through an adapter contract rather than a hardcoded acquisition mechanism.
- Add initial SQLite persistence for normalized jobs, including schema creation, repository-style storage/retrieval operations, and salary text support.
- Support storing collected jobs while preventing duplicate records based on stable source-origin information where available.
- Add a first-pass rule-based evaluation step that summarizes, classifies, and scores stored jobs against the professional compass.
- Keep the current LinkedIn implementation explicitly fixture-backed so the acquisition boundary is correct without claiming real LinkedIn collection yet.
- Exclude auto-apply behavior, recruiter outreach, browser automation, and OpenClaw integration from this first increment.
- Exclude LLM-based evaluation, autonomous outreach, and production-grade source acquisition from this first increment.

## Capabilities

### New Capabilities
- `job-source-ingestion`: Collect job postings from a source-specific adapter and normalize them into the system's canonical job schema, starting with a LinkedIn ingestion boundary.
- `job-storage`: Persist normalized job records in SQLite with timestamps and workflow status fields so collected jobs can be tracked and reused by later qualification workflows.
- `job-compass-evaluation`: Load a candidate professional compass, produce a structured job summary and classification, and score each ingested job with simple local heuristics.

### Modified Capabilities
- None.

## Impact

- Affected code: initial Python domain models, professional compass loader, adapter interfaces, SQLite repository layer, local evaluator, and CLI entrypoints for ingestion/storage workflows.
- Affected systems: local SQLite database and source adapter integrations.
- Dependencies: Python standard library SQLite support is sufficient for v1; no LinkedIn API dependency is introduced.
