## Change Summary

Introduce a Linux-first unattended harvest path that supports LinkedIn, Indeed, and Wellfound in one scheduled run, with explicit preflight checks and per-source fault isolation.

## Context

Current unattended harvest orchestration is centered on `harvest-linkedin` and does not provide a unified multi-source unattended command. On pop!_OS/Linux, this creates two operational gaps:

1. Users expect unattended extraction to include Indeed and Wellfound.
2. Runtime dependency failures (for example browser/driver/runtime mismatches) are not surfaced through a single preflight and status model.

## Goals

- Add a multi-source unattended harvest command surface.
- Keep existing single-source commands intact.
- Make Linux runtime failures actionable before acquisition starts.
- Ensure one failing source does not abort the entire unattended run.

## Non-Goals

- Replacing existing source adapters with a new scraping stack.
- Adding autonomous apply/outreach behavior.
- Building distributed or remote orchestration infrastructure.

## Design

### 1) New orchestration flow

Add a new runtime command (working name: `harvest-all`) that:

- loads compass and schedule/config once
- resolves enabled sources (LinkedIn/Indeed/Wellfound)
- executes source harvest workers with per-source boundaries
- persists results to the existing SQLite repository
- prints a consolidated summary plus per-source diagnostics

The orchestration pattern mirrors `ingest-all` behavior semantics:
- parallel or staged source execution
- failure isolation by source
- normalized summary output at the end

### 2) Linux preflight checks

Before starting unattended source execution, run a preflight validator with source-aware checks:

- Python dependency availability (`yaml`, `selenium`, and other required imports)
- browser runtime availability for browser-backed adapters (Chrome/Chromedriver/Selenium manager path viability)
- required local files (`profiles/professional_compass.json`, schedule config path)
- writable paths for logs/captures/db parent

Preflight returns structured failures:
- `source`
- `check`
- `severity`
- `action`

Blocking checks prevent that source from starting, but do not block other sources unless the failure is global (for example DB unavailable).

### 3) Source fault isolation

Each source run is wrapped so adapter or runtime exceptions produce a structured source error:

- source name
- exception class
- error message
- stage (`preflight`, `acquire`, `persist`, `summarize`)

The run continues for healthy sources. Final output includes:
- per-source `stored/inserted/updated`
- per-source `status=ok|failed|skipped`
- error payloads for failed/skipped sources

### 4) Backward compatibility

Keep these commands unchanged:
- `harvest-linkedin`
- existing cron install/remove/status helpers
- ingestion commands (`ingest-*`, `ingest-all`)

Additive extension only: new multi-source unattended command and supporting helpers.

### 5) Observability and ops

Expose clearer runtime visibility via:

- enriched `harvest-status` output for multi-source runs
- per-source counters in stdout summary
- continued log tail compatibility through existing runtime support entrypoints

## Data + Persistence

No schema-breaking changes required. Use existing `jobs` table and dedupe behavior:

- prefer `source + external_job_id`
- fallback to normalized source link

Any new runtime status persistence should be additive and optional.

## Risks and Mitigations

- **Linux browser variance**: Preflight checks and explicit error actions reduce blind failures.
- **Higher resource usage in multi-source runs**: configurable worker/source enable flags.
- **Noisy failures from one source**: isolation + structured summaries prevent full-run collapse.

## Validation Strategy

- Unit tests for:
  - preflight pass/fail classification
  - source failure isolation
  - multi-source summary output shape
- Regression tests:
  - existing LinkedIn harvest command behavior unchanged
  - existing ingestion command behavior unchanged
- Manual verification on Linux:
  - run new multi-source command with one intentionally broken source and confirm others still run

