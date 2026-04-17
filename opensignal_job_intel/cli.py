from __future__ import annotations

import argparse
import json
from pathlib import Path

from opensignal_job_intel.compass import load_professional_compass
from opensignal_job_intel.evaluation import JobCompassEvaluator
from opensignal_job_intel.repositories.sqlite_jobs import SQLiteJobRepository
from opensignal_job_intel.services import JobIngestionService
from opensignal_job_intel.sources.linkedin import LinkedInJsonFileAdapter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="opensignal-job-intel",
        description="CLI for local-first job ingestion and storage.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser(
        "ingest-linkedin",
        help="Use a professional compass plus a local LinkedIn fixture to store and score jobs.",
    )
    ingest.add_argument(
        "--compass-file",
        default="profiles/professional_compass.json",
        help="Path to the professional compass JSON file.",
    )
    ingest.add_argument(
        "--source-file",
        required=True,
        help="Path to the local LinkedIn JSON fixture file used by the v1 adapter.",
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

    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command != "ingest-linkedin":
        raise ValueError(f"Unsupported command: {args.command}")

    repository = SQLiteJobRepository(Path(args.db_path))
    repository.initialize()
    compass = load_professional_compass(args.compass_file)
    adapter = LinkedInJsonFileAdapter(args.source_file)
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
    for evaluation in result.evaluations[: args.limit]:
        print(json.dumps(evaluator.as_dict(evaluation), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
