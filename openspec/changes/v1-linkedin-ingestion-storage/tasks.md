## 1. Project Skeleton

- [x] 1.1 Create the initial Python package structure for domain models, source adapters, repositories, and CLI entrypoints
- [x] 1.2 Add the canonical job record model and any shared enums or constants required for source and workflow status fields
- [x] 1.3 Add a professional compass model and loader as the user-facing input boundary for early qualification

## 2. SQLite Persistence

- [x] 2.1 Implement SQLite schema initialization for the `jobs` table with canonical fields, timestamps, and seen/applied markers
- [x] 2.2 Implement a job repository class that stores canonical job records and enforces duplicate-safe insert or upsert behavior
- [x] 2.3 Add repository retrieval helpers needed to inspect stored jobs during early CLI-driven workflows
- [x] 2.4 Support additive schema updates for new canonical fields introduced during the change, including salary text

## 3. Ingestion Boundary

- [x] 3.1 Define the minimal source adapter contract that returns canonical job records to the application layer
- [x] 3.2 Implement the first LinkedIn adapter as a boundary-compliant fixture-backed source for v1
- [x] 3.3 Add normalization logic so LinkedIn-collected records are converted into canonical job records before persistence

## 4. CLI Workflow And Verification

- [x] 4.1 Add a CLI command that initializes storage, runs the LinkedIn ingestion flow, persists collected jobs, and loads the professional compass profile
- [x] 4.2 Add tests covering canonical normalization, duplicate-safe storage, and the repository schema behavior
- [x] 4.3 Add a rule-based evaluation step that summarizes, classifies, and scores jobs against the professional compass
- [x] 4.4 Document the first-run workflow, current implementation status, and fixture-backed LinkedIn assumption in the README
- [x] 4.5 Provide a committed professional compass template while keeping the real profile file private to the local workspace
