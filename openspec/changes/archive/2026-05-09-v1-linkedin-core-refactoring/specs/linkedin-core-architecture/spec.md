## ADDED Requirements

### Requirement: Six-module core architecture target
The refactor SHALL converge the current LinkedIn implementation toward a
`src/` package root organized around six top-level responsibility modules:
`core_domain_inputs`, `linkedin_acquisition`,
`linkedin_extraction_filtering`, `harvest_orchestration`,
`persistence_runtime_ops`, and `runtime_entrypoints`.

#### Scenario: Refactor target is reviewable
- **WHEN** a contributor inspects the LinkedIn core implementation after the
  refactor
- **THEN** the main LinkedIn runtime behavior is organized around those six
  module responsibilities
- **AND** responsibility placement can be explained without referring to the
  legacy `sources/` layout

### Requirement: Behavior is owned by explicit collaborators
The refactor SHALL move stateful runtime behavior into explicit classes with
coherent responsibilities rather than leaving it spread across mixed-purpose
modules and script bodies.

#### Scenario: Core behavior is class-owned
- **WHEN** a contributor inspects acquisition, harvest, runtime-ops, or
  persistence coordination logic
- **THEN** the main behavior is owned by named classes with narrow
  responsibilities
- **AND** those classes expose collaborators explicitly rather than hiding the
  behavior in free-function orchestration

### Requirement: Runtime entrypoints remain operationally thin
Runtime entrypoints SHALL remain executable, but they MUST delegate immediately
into class-owned behavior and MUST NOT accumulate domain logic.

#### Scenario: Runtime wrapper delegates immediately
- **WHEN** a runtime entrypoint is invoked for cron installation, harvest
  execution, status inspection, log tailing, or recent-job viewing
- **THEN** the entrypoint module delegates into class-owned behavior
- **AND** the entrypoint does not contain harvest-domain decision logic beyond
  argument forwarding and process exit behavior

### Requirement: Refactor preserves current observable behavior
The architectural refactor SHALL preserve externally visible CLI, harvest,
ingestion, persistence, and operational-helper behavior unless a separate
OpenSpec change explicitly modifies it.

#### Scenario: Structural move does not change command behavior
- **WHEN** the implementation is reorganized into the new module layout
- **THEN** existing supported commands and operational helpers continue to
  behave as before
- **AND** any intentional behavior change is captured by a separate spec delta
  rather than being hidden inside cleanup
