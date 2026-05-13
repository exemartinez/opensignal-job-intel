# AGENTS.md

## Runtime + Tooling Gotchas
- Use Python 3.11+ for all commands. The code imports `enum.StrEnum` (`src/core_domain_inputs.py`), which fails on Python 3.9.
- This machine needs Node 20 in `PATH` for OpenSpec CLI commands:
  - `env PATH=/usr/local/opt/node@20/bin:$PATH openspec ...`

## Verified High-Value Commands
- Run tests: `python3.11 -m unittest discover -s tests -v`
- Run CLI ingestion locally:
  - `python3.11 main.py ingest-linkedin --compass-file profiles/professional_compass.template.json --source-file sample_linkedin_jobs.json --db-path data/jobs.db --limit 10`
- OpenSpec validate (change):
  - `env PATH=/usr/local/opt/node@20/bin:$PATH openspec validate v1-linkedin-acquisition`
- OpenSpec validate (repo):
  - `env PATH=/usr/local/opt/node@20/bin:$PATH openspec validate`

## Real Entrypoints + Boundaries
- CLI entrypoint is `main.py`, which calls `src/runtime_entrypoints.py:main`.
- Ingestion flow wiring is in `src/runtime_entrypoints.py`:
  - load compass (`src/core_domain_inputs.py`)
  - fetch via source adapter (`src/linkedin_acquisition.py`, `src/indeed_acquisition.py`)
  - persist via SQLite repository (`src/persistence_runtime_ops.py`)
  - evaluate via rule-based evaluator (`src/core_domain_inputs.py`)
- LinkedIn acquisition supports both local JSON fixtures and live guest-page scraping under `src/linkedin_acquisition.py`.
- Indeed acquisition supports both local JSON fixtures and live guest-page scraping under `src/indeed_acquisition.py`.
- Follow `ARCHITECTURE.md` for package boundaries, OO conventions, duplication policy, and documentation expectations.

## Data + Persistence Facts That Affect Changes
- Private user profile is `profiles/professional_compass.json` (gitignored). Committed template is `profiles/professional_compass.template.json`.
- Local DB artifacts are intentionally untracked (`data/`, `*.db`, `*.sqlite*` are gitignored).
- Deduplication rule is `JobRecord.dedupe_key`:
  - prefer `source + external_job_id`
  - fallback to normalized link (`src.core_domain_inputs.normalize_source_link` strips unstable query string and trailing slash while preserving source-essential identifiers such as Indeed `jk`)

## OpenSpec State In This Repo
- Baseline specs live in `openspec/specs/`.
- Archived v1 implementation is in `openspec/changes/archive/2026-04-20-v1-linkedin-ingestion-storage/`.
- Active next change scaffold exists at `openspec/changes/v1-linkedin-acquisition/`.
- Repo includes OpenSpec slash-skill definitions under `.codex/skills/` (`openspec-propose`, `openspec-apply-change`, `openspec-explore`, `openspec-archive-change`).

## What Not To Invent
- No lint/typecheck/build/task-runner config is present in repo today; do not fabricate `ruff`, `mypy`, `pytest`, `make`, or CI steps as if they are canonical.
