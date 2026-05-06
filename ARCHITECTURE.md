# ARCHITECTURE.md

## Purpose

This document defines the architectural expectations for the
`opensignal-job-intel` repository. It is intended to guide code review, feature
work, and structural changes so the codebase evolves toward clearer object
boundaries, lower duplication, and more predictable behavior.

This file complements:
- `AGENTS.md` for runtime/tooling guidance
- `CHANGELOG.md` for release history
- `openspec/` for change-level requirements and design decisions


## Architectural Direction

The codebase should favor:

- stronger object-oriented boundaries
- smaller modules with single responsibilities
- reduced duplication across acquisition, harvest, and operational flows
- behavior-oriented tests that allow package and module structure to change safely

## Current Responsibility Boundaries

Use the current structure intentionally:

- `main.py`
  - CLI launcher only
- `opensignal_job_intel/cli.py`
  - command parsing and top-level workflow wiring
- `opensignal_job_intel/compass.py`
  - professional-compass loading and normalization
- `opensignal_job_intel/models.py`
  - canonical data models and shared domain state
- `opensignal_job_intel/evaluation.py`
  - rule-based job evaluation
- `opensignal_job_intel/repositories/sqlite_jobs.py`
  - persistence and schema evolution
- `opensignal_job_intel/sources/linkedin.py`
  - fixture-backed LinkedIn adapter
- `opensignal_job_intel/sources/linkedin_acquire.py`
  - acquisition behavior for interactive scraping
- `opensignal_job_intel/sources/linkedin_extraction.py`
  - extraction/parsing from LinkedIn search/detail HTML
- `opensignal_job_intel/sources/linkedin_harvest.py`
  - unattended harvest orchestration
- `opensignal_job_intel/sources/linkedin_harvest_ops.py`
  - operational helpers for cron/runtime support
- thin Python entrypoints in `opensignal_job_intel/sources/`
  - dispatch wrappers only


## Boundary Rules - Division of concerns 

### 1. Keep orchestration separate from parsing

Parsing and extraction logic should not own scheduling, persistence, or process
control concerns.

Examples:
- `linkedin_extraction.py` should extract data from HTML
- it should not decide cron behavior, persistence strategy, or harvest pacing

### 2. Keep persistence separate from source behavior

Repository classes should manage:
- schema
- storage
- retrieval
- update semantics

They should not contain:
- source-specific scraping logic
- CLI wiring
- cron logic

### 3. Keep entrypoints thin

Command wrappers and script-style entrypoints should:
- import the real implementation
- delegate immediately
- Support different parameters
- Keep just one entry point to the core functionality.

Entry point should NOT accumulate business logic.

### 4. Prefer explicit collaborators over mixed-responsibility modules

When a module starts handling:
- path resolution
- subprocess management
- state transitions
- reporting
- business rules

it is a candidate for decomposition into multiple collaborating objects.


## Object-Oriented Expectations

Object orientation in this repo should mean:

- objects own coherent state and behavior together
- collaborators are explicit
- responsibilities are narrow
- lifecycle/state transitions are visible in the API
- Every class has just ONE core responsibility, which is documented at class level.
- Use design patterns extensively for its design.
- Do proper use of inheritance.

This should not mean:

- adding classes for trivial wrappers
- replacing simple pure functions with unnecessary indirection
- building inheritance hierarchies where composition is clearer
- Apply design patterns out of the blue-

### Prefer composition over inheritance

Use composition when separating concerns such as:
- URL/query construction
- fetch behavior
- filter evaluation
- harvest pacing/backoff policy
- cron installation/removal
- repository-backed state access

Inheritance should be rare and justified by a real substitutable abstraction - like an strategy, builder or abstract factory pattern.

### Prefer explicit domain names

Class and module names should reflect responsibility. Do not use meaningless names.

For example:
- `QueryPlanner`
- `HarvestRunner`
- `ThrottlePolicy`
- `ExtractionSpecLoader`
- `CronInstaller`

Avoid vague names like:
- `Manager`
- `Helper`
- `Utils`

unless the role is genuinely generic and stable.
Do not pass of four words as part of the Class name.
Use pascal case for class names.


## Duplication Policy

Duplicated behavior should be removed when it represents a stable shared concept.

Good candidates for deduplication:
- repeated URL/query parameter construction
- repeated cron block creation rules
- repeated path-resolution logic
- repeated filter-decision logic
- repeated subprocess launch patterns

Do not extract a shared abstraction merely because two blocks look similar.
Extract only when:
- the behavior is conceptually the same
- the abstraction clarifies ownership
- the resulting API is simpler than the duplication

When too many features are shared, choose inheritance.


## Documentation and Comment Policy

### Public modules, classes, and methods

Public modules, public classes, and public methods should have concise docstrings
when they define stable responsibilities or are likely to be reused or extended.

The docstring should explain:
- what the object/function is responsible for
- key constraints or invariants when needed

It should not narrate obvious implementation steps.
Use clear & clever variable names and methods.

### Private helpers

Private functions and methods do not need docstrings by default.
Add one only when:
- the behavior is non-obvious
- there is tricky state logic
- there is an important invariant or side effect

They DO NEED common explanatory commentaries instead. 

### Inline comments

Inline comments should be used sparingly.

Use them for:
- invariants
- subtle edge cases
- non-obvious state transitions
- why a workaround exists

Do not use comments for:
- restating the code line by line
- obvious assignments
- generic noise
- explaining the code.


## Testing Expectations

Tests are the safety net for behavioral stability and structural change.

Prefer tests that lock:
- public behavior
- persisted state
- command behavior
- generated URLs
- stop reasons
- filter decisions
- cron block contents

Do not overfit tests to:
- current file names
- incidental method boundaries
- temporary module layout

#### Critical

These areas need strong regression protection because they define top-level
workflow behavior:
- CLI wiring
- LinkedIn acquisition
- LinkedIn harvest orchestration
- LinkedIn harvest operational helpers
- SQLite repository behavior

#### Moderate

These need focused edge-case coverage:
- models
- evaluation
- compass loading
- LinkedIn extraction
- fixture-backed adapter behavior

#### Smoke-only

Thin entrypoint wrappers usually need import/dispatch coverage only.

## Change Discipline

If a structural change also changes supported behavior, capture that through
OpenSpec instead of hiding it inside cleanup or reorganization work.

## Decision Rule

When choosing between:
- less code vs clearer ownership
- fewer abstractions vs more explicit boundaries
- a quick local fix vs a stable collaboration seam

prefer the option that makes future behavior safer to test and easier to change
without surprise regressions.
