## Context

The repository currently contains only OpenSpec scaffolding and a project-level intent to build a Python, CLI-first, human-in-the-loop job discovery system. The first implementation step needs to create stable boundaries for collecting jobs from LinkedIn without coupling the project to any single acquisition mechanism, especially not an assumed official API.

This change also needs to establish a canonical job model, a professional compass input, and SQLite-backed persistence because later qualification, ranking, and shortlist generation depend on normalized historical job data and a stable candidate profile. The design should remain small enough to implement quickly while preserving extension points for additional sources and future evaluation workflows.

## Goals / Non-Goals

**Goals:**
- Define a canonical job record that is independent of any specific source payload.
- Define a professional compass input model that acts as the user-facing configuration for early qualification.
- Introduce a source adapter boundary for ingestion, with LinkedIn as the first supported source.
- Persist normalized jobs in SQLite with simple repository-style access.
- Track workflow status fields needed for later exclusion of seen or applied jobs.
- Add a local rule-based evaluation step that produces structured summaries and first-pass fit scores.
- Keep the CLI and module structure ready for future evaluators and ranking components.

**Non-Goals:**
- Implement browser automation, scraping infrastructure, or partner-gated LinkedIn API access.
- Build production-grade LinkedIn acquisition, shortlist orchestration, or LLM evaluation in this change.
- Support every future job source now.
- Design a generic plugin framework or other heavy abstraction before real need exists.

## Decisions

### Use a canonical `JobRecord` model at the ingestion boundary

All ingestion flows will normalize incoming source data into a single canonical record before persistence. The canonical shape will include source, source job identifier when available, company, title, description, post datetime when available, source link, optional salary text, collected timestamp, stored timestamp, and workflow markers such as seen/applied.

Rationale:
- Keeps storage and later evaluators independent from source-specific payloads.
- Lets multiple source adapters reuse the same repository and downstream qualification pipeline.

Alternatives considered:
- Persist raw source payloads first and normalize later. Rejected because it pushes source-specific complexity downstream and weakens deduplication.
- Model separate tables per source. Rejected because v1 needs extensibility with minimal schema churn.

### Add a separate `ProfessionalCompass` input model

The user-facing input will be a professional compass JSON profile stored locally. It captures candidate context, positioning, target roles, hard filters, and compensation constraints. The first CLI workflow loads this compass and uses it to evaluate ingested jobs.

Rationale:
- Separates user intent from collected job records.
- Matches the product goal of reviewing jobs against a configurable candidate profile rather than manually crafted per-job input.

Alternatives considered:
- Reuse raw job fixture files as the only CLI input. Rejected because that makes source fixtures look like product input.
- Delay the compass until LLM evaluation exists. Rejected because even rule-based qualification needs an explicit candidate profile boundary.

### Introduce a minimal adapter contract for source ingestion

The ingestion layer will expose a small interface such as `JobSourceAdapter.fetch_jobs(...) -> list[JobRecord]` or equivalent iterator-based behavior. The first concrete adapter will represent LinkedIn ingestion as a boundary only. Its implementation remains fixture-backed for this change so callers depend on the contract instead of a hardcoded acquisition mechanism.

Rationale:
- Protects the system from early lock-in to scraping, browser automation, HTML parsing, or a private API.
- Keeps the first change honest about what is known and what is intentionally deferred.

Alternatives considered:
- Hardcode LinkedIn acquisition directly into the CLI or repository path. Rejected because it mixes source mechanics with business boundaries.
- Build a generalized provider registry. Rejected because it adds ceremony before a second source exists.

### Use SQLite-first persistence with one primary jobs table

SQLite will be the v1 storage engine. A primary `jobs` table will store the canonical job fields plus workflow status markers and timestamps. Uniqueness will be enforced with a stable source-origin key when possible, typically `source + external_job_id` or `source + link` as a fallback.

Rationale:
- Matches the project’s local-first constraint.
- Simple enough to inspect manually, back up easily, and evolve without operational burden.

Alternatives considered:
- SQLAlchemy or a heavier ORM. Rejected for the first change because the repository is still small and schema understanding matters more than abstraction.
- PostgreSQL from the start. Rejected because it adds operational weight without helping the v1 use case.

### Separate storage access behind a repository class

SQLite operations will be concentrated in a repository class responsible for schema initialization, insert/upsert behavior, and retrieval methods needed by the CLI. This is a meaningful class boundary because it isolates SQL and future storage evolution from the rest of the application.

Rationale:
- Makes later changes such as filtering unseen jobs or adding ranking metadata straightforward.
- Avoids scattering SQL across adapters and CLI commands.

Alternatives considered:
- Inline SQL in command handlers. Rejected because it couples CLI flow to persistence details and becomes hard to extend.

### Add a lightweight rule-based evaluation layer

The first CLI workflow will run a local evaluator after ingestion. The evaluator uses simple string heuristics plus the professional compass to extract techs, classify responsibility level, classify company type, normalize salary text, and compute a first-pass fit score. It returns structured JSON-like output per job.

Rationale:
- Makes the first increment useful for human review without introducing LLM dependencies.
- Creates a clean seam for replacing local heuristics with richer evaluation later.

Alternatives considered:
- Add evaluation tables now. Rejected because evaluation outputs can remain transient in v1.
- Wait to add any evaluation until an LLM backend exists. Rejected because the repo would remain storage-only and not yet useful for triage.

## Risks / Trade-offs

- [LinkedIn acquisition remains fixture-backed] -> Mitigation: state clearly in specs and README that the adapter currently consumes local fixtures and does not fetch from LinkedIn yet.
- [Deduplication may be imperfect when source identifiers are missing] -> Mitigation: use a stable fallback such as canonicalized link and make deduplication strategy explicit in the repository.
- [Canonical schema may need expansion soon] -> Mitigation: keep the initial table narrow but additive-friendly, with future changes extending the schema rather than overfitting now.
- [SQLite can become limiting at larger scale] -> Mitigation: hide persistence behind a repository boundary so a later storage migration is localized.
- [Rule-based evaluation is brittle] -> Mitigation: treat it as a first-pass local heuristic layer and keep the evaluator isolated for later replacement.

## Migration Plan

This is the first product-facing change, so migration is limited to creating the initial SQLite schema, adding the salary text column if missing, adding the local professional compass template, and wiring a CLI path that stores and evaluates normalized jobs. If the change is rolled back, the code can be removed and the local database file discarded without external system impact.

## Open Questions

- Should the next change add raw payload snapshot storage for parser debugging, or keep the database limited to canonical records?
- Should the first real acquisition mechanism be HTML ingestion, manual exports, or browser automation?
