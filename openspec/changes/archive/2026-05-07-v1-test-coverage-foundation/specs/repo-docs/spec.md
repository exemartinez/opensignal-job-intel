## MODIFIED Requirements

### Requirement: README reflects current repo behavior
The repository SHALL maintain a README that describes the current supported CLI workflows, configuration inputs, environment setup, and canonical test execution workflow.

#### Scenario: README documents LinkedIn ingestion modes
- **WHEN** a user reads the README
- **THEN** it describes how to run LinkedIn ingestion in fixture mode and in live acquisition mode
- **AND** it describes the required inputs (professional compass JSON, and extraction spec default/override)

#### Scenario: README documents local-only sensitive configuration
- **WHEN** the README references optional authenticated scraping or local LLM usage
- **THEN** it documents the configuration mechanism (env vars / gitignored local files)
- **AND** it does not require committing secrets to the repository

#### Scenario: README documents engineering bootstrap and test workflow
- **WHEN** a contributor prepares to run or extend the automated suite
- **THEN** the README documents the supported Python environment bootstrap steps
- **AND** it documents the canonical dependency installation command
- **AND** it documents the canonical automated test command used for repository validation
