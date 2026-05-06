# AGENTS.md

## Runtime + Tooling Gotchas
- Use Python 3.11+ for all commands. The code imports `enum.StrEnum` (`opensignal_job_intel/models.py`), which fails on Python 3.9.
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
- CLI entrypoint is `main.py`, which calls `opensignal_job_intel/cli.py:main`.
- Ingestion flow wiring is in `opensignal_job_intel/cli.py`:
  - load compass (`compass.py`)
  - fetch via source adapter (`sources/base.py`)
  - persist via SQLite repository (`repositories/sqlite_jobs.py`)
  - evaluate via rule-based evaluator (`evaluation.py`)
- Current LinkedIn adapter is fixture-backed only (`opensignal_job_intel/sources/linkedin.py` reads local JSON). Do not claim real LinkedIn acquisition in docs/spec text unless that change is implemented.
- Follow `ARCHITECTURE.md` for package boundaries, OO conventions, duplication policy, and documentation expectations.

## Data + Persistence Facts That Affect Changes
- Private user profile is `profiles/professional_compass.json` (gitignored). Committed template is `profiles/professional_compass.template.json`.
- Local DB artifacts are intentionally untracked (`data/`, `*.db`, `*.sqlite*` are gitignored).
- Deduplication rule is `JobRecord.dedupe_key`:
  - prefer `source + external_job_id`
  - fallback to normalized link (`models.normalize_source_link` strips query string and trailing slash)

## OpenSpec State In This Repo
- Baseline specs live in `openspec/specs/`.
- Archived v1 implementation is in `openspec/changes/archive/2026-04-20-v1-linkedin-ingestion-storage/`.
- Active next change scaffold exists at `openspec/changes/v1-linkedin-acquisition/`.
- Repo includes OpenSpec slash-skill definitions under `.codex/skills/` (`openspec-propose`, `openspec-apply-change`, `openspec-explore`, `openspec-archive-change`).

## What Not To Invent
- No lint/typecheck/build/task-runner config is present in repo today; do not fabricate `ruff`, `mypy`, `pytest`, `make`, or CI steps as if they are canonical.
