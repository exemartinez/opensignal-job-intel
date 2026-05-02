from __future__ import annotations

import argparse
import json
from pathlib import Path

from opensignal_job_intel.compass import load_professional_compass
from opensignal_job_intel.evaluation import JobCompassEvaluator
from opensignal_job_intel.repositories.sqlite_jobs import SQLiteJobRepository
from opensignal_job_intel.services import JobIngestionService
from opensignal_job_intel.sources.linkedin_harvest import (
    LinkedInNightlyHarvester,
    load_harvest_schedule,
    resolve_harvest_schedule_path,
)
from opensignal_job_intel.sources.linkedin import (
    LinkedInJsonFileAdapter,
    LinkedInScrapeAdapter,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="opensignal-job-intel",
        description="CLI for local-first job ingestion and storage.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser(
        "ingest-linkedin",
        help="Ingest LinkedIn jobs (fixture mode or live acquisition) into SQLite and score them.",
    )
    ingest.add_argument(
        "--compass-file",
        default="profiles/professional_compass.json",
        help="Path to the professional compass JSON file.",
    )
    ingest.add_argument(
        "--source-file",
        help=(
            "Optional path to a local LinkedIn JSON fixture file. "
            "If omitted, the CLI runs live acquisition mode."
        ),
    )
    ingest.add_argument(
        "--extraction-spec",
        default="config/linkedin_extraction.template.json",
        help="Path to the LinkedIn extraction spec JSON used for live acquisition.",
    )
    ingest.add_argument(
        "--max-jobs",
        type=int,
        default=30,
        help="Maximum number of jobs to acquire in live mode.",
    )
    ingest.add_argument(
        "--capture-dir",
        default=None,
        help="Optional directory to persist raw HTML captures (gitignored via data/).",
    )
    ingest.add_argument(
        "--write-fixture",
        default=None,
        help="Optional JSON path to write an offline fixture extracted from live acquisition.",
    )
    ingest.add_argument(
        "--db-path",
        default="data/jobs.db",
        help="SQLite database path. Defaults to data/jobs.db.",
    )
    ingest.add_argument(
        "--limit",
        type=int,
        default=10,
        help="How many stored jobs to print after ingestion.",
    )

    harvest = subparsers.add_parser(
        "harvest-linkedin",
        help="Run the nightly LinkedIn harvest orchestrator into SQLite.",
    )
    harvest.add_argument(
        "--compass-file",
        default="profiles/professional_compass.json",
        help="Path to the professional compass JSON file.",
    )
    harvest.add_argument(
        "--extraction-spec",
        default="config/linkedin_extraction.template.json",
        help="Path to the LinkedIn extraction spec JSON used for acquisition.",
    )
    harvest.add_argument(
        "--schedule-file",
        default=None,
        help=(
            "Optional path to the harvest schedule YAML. "
            "Defaults to config/extraction_schedule.yaml when present, "
            "otherwise config/extraction_schedule.template.yaml."
        ),
    )
    harvest.add_argument(
        "--capture-dir",
        default=None,
        help="Optional directory to persist raw HTML captures (gitignored via data/).",
    )
    harvest.add_argument(
        "--db-path",
        default="data/jobs.db",
        help="SQLite database path. Defaults to data/jobs.db.",
    )
    harvest.add_argument(
        "--max-jobs",
        type=int,
        default=None,
        help="Optional cap on how many new jobs to store during this run.",
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "ingest-linkedin":
        return _run_ingest(args)
    if args.command == "harvest-linkedin":
        return _run_harvest(args)
    raise ValueError(f"Unsupported command: {args.command}")


def _run_ingest(args: argparse.Namespace) -> int:
    repository = SQLiteJobRepository(Path(args.db_path))
    repository.initialize()
    compass = load_professional_compass(args.compass_file)

    if args.source_file:
        adapter = LinkedInJsonFileAdapter(args.source_file)
    else:
        adapter = LinkedInScrapeAdapter(
            compass=compass,
            extraction_spec_path=args.extraction_spec,
            max_jobs=args.max_jobs,
            capture_dir=args.capture_dir,
            write_fixture_path=args.write_fixture,
        )
    evaluator = JobCompassEvaluator(compass)
    service = JobIngestionService(
        adapter=adapter, repository=repository, evaluator=evaluator
    )
    result = service.ingest()

    print(
        f"Loaded compass from {args.compass_file}. "
        f"Ingested {result.fetched} LinkedIn jobs into {args.db_path}. "
        f"Stored records: {repository.count_jobs()}."
    )
    if hasattr(adapter, "diagnostics"):
        try:
            diag = adapter.diagnostics.as_dict()  # type: ignore[attr-defined]
            print(json.dumps({"acquisition_diagnostics": diag}, ensure_ascii=True))
        except Exception:
            pass
    for evaluation in result.evaluations[: args.limit]:
        print(json.dumps(evaluator.as_dict(evaluation), ensure_ascii=True))
    return 0


def _run_harvest(args: argparse.Namespace) -> int:
    repository = SQLiteJobRepository(Path(args.db_path))
    repository.initialize()
    compass = load_professional_compass(args.compass_file)
    schedule_path = resolve_harvest_schedule_path(args.schedule_file)
    schedule = load_harvest_schedule(schedule_path)
    harvester = LinkedInNightlyHarvester(
        compass=compass,
        repository=repository,
        extraction_spec_path=args.extraction_spec,
        schedule=schedule,
        capture_dir=args.capture_dir,
        max_jobs=args.max_jobs,
    )
    result = harvester.run()
    print(
        json.dumps(
            {
                "harvest_summary": result.as_dict(),
                "db_path": args.db_path,
                "stored_records": repository.count_jobs(),
                "schedule_file": schedule_path,
            },
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
