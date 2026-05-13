## MODIFIED Requirements

### Requirement: README reflects current repo behavior
The repository SHALL maintain a README that describes the current supported CLI
workflows, configuration inputs, environment setup, and canonical test
execution workflow.

#### Scenario: README documents Indeed ingestion modes
- **WHEN** a user reads the README after Indeed support is added
- **THEN** it describes how to run Indeed ingestion in fixture mode and in live
  acquisition mode
- **AND** it describes the relevant command surface and local-only runtime
  configuration for Indeed when applicable
