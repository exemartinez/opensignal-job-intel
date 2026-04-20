## ADDED Requirements

### Requirement: Professional compass input
The system SHALL load a locally stored professional compass profile as the primary user-facing input for the early qualification workflow.

#### Scenario: Compass profile is loaded for ingestion
- **WHEN** the user runs the LinkedIn ingestion CLI command
- **THEN** the application loads the professional compass profile from a local JSON file before evaluating ingested jobs

### Requirement: Structured rule-based evaluation output
The system SHALL produce a structured local evaluation for each ingested job using the professional compass and rule-based heuristics.

#### Scenario: Job is summarized and scored
- **WHEN** a canonical job record is ingested
- **THEN** the application outputs a structured evaluation containing company, position, job URL, summary, extracted techs, responsibility classification, company-type classification, normalized salary, and a numeric score

### Requirement: Private profile with committed template
The system SHALL support a private local professional compass file while providing a committed template file for repository users.

#### Scenario: Repository includes template but not personal profile data
- **WHEN** a user clones the repository
- **THEN** the repository contains a professional compass template file for customization and can ignore the user's real professional compass file from version control
