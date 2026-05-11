"""Runtime entrypoints and command dispatch for the refactored system.

Author: Ezequiel H. Martinez
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core_domain_inputs import (
    JobCompassEvaluator,
    JobIngestionService,
    load_professional_compass,
)
from src.harvest_orchestration import (
    LinkedInNightlyHarvester,
    load_harvest_schedule,
    resolve_harvest_schedule_path,
)
from src.linkedin_acquisition import LinkedInJsonFileAdapter, LinkedInScrapeAdapter
from src.persistence_runtime_ops import HarvestCronScripts, SQLiteJobRepository


class RuntimeEntrypoints:
    """Own the public CLI parsing and top-level command dispatch."""

    @staticmethod
    def build_parser() -> argparse.ArgumentParser:
        """Build the top-level CLI parser and subcommands."""
        parser = argparse.ArgumentParser(
            prog="opensignal-job-intel",
            description="CLI for local-first job ingestion, harvest, and runtime operations.",
        )
        subparsers = parser.add_subparsers(dest="command", required=True)

        ingest = subparsers.add_parser(
            "ingest-linkedin",
            help="Ingest LinkedIn jobs (fixture mode or live acquisition) into SQLite and score them.",
        )
        ingest.add_argument("--compass-file", default="profiles/professional_compass.json")
        ingest.add_argument("--source-file")
        ingest.add_argument(
            "--extraction-spec",
            default="config/linkedin_extraction.template.json",
        )
        ingest.add_argument("--max-jobs", type=int, default=30)
        ingest.add_argument("--capture-dir", default=None)
        ingest.add_argument("--write-fixture", default=None)
        ingest.add_argument("--db-path", default="data/jobs.db")
        ingest.add_argument("--limit", type=int, default=10)

        harvest = subparsers.add_parser(
            "harvest-linkedin",
            help="Run the nightly LinkedIn harvest orchestrator into SQLite.",
        )
        harvest.add_argument("--compass-file", default="profiles/professional_compass.json")
        harvest.add_argument(
            "--extraction-spec",
            default="config/linkedin_extraction.template.json",
        )
        harvest.add_argument("--schedule-file", default=None)
        harvest.add_argument("--capture-dir", default=None)
        harvest.add_argument("--db-path", default="data/jobs.db")
        harvest.add_argument("--max-jobs", type=int, default=None)

        subparsers.add_parser("harvest-status")
        subparsers.add_parser("install-continuous-hourly-harvest-cron")
        subparsers.add_parser("install-harvest-cron")
        subparsers.add_parser("remove-harvest-cron")
        subparsers.add_parser("remove-one-shot-harvest-cron")
        subparsers.add_parser("run-harvest-cron")
        subparsers.add_parser("schedule-harvest-next-minute")
        show_recent = subparsers.add_parser("show-recent-jobs")
        show_recent.add_argument("limit", nargs="?", type=int, default=25)
        subparsers.add_parser("tail-harvest-logs")

        return parser

    @staticmethod
    def main(argv: list[str] | None = None) -> int:
        """Parse CLI arguments and dispatch the selected command."""
        args = build_parser().parse_args(argv)
        if args.command == "ingest-linkedin":
            return _run_ingest(args)
        if args.command == "harvest-linkedin":
            return _run_harvest(args)
        return RuntimeEntrypoints.run_runtime_command(args)

    @staticmethod
    def run_ingest(args: argparse.Namespace) -> int:
        """Run fixture or live LinkedIn ingestion and print the summary."""
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
            f"Persisted {result.stored} LinkedIn jobs into {args.db_path} "
            f"(new: {result.inserted}, updated: {result.updated}). "
            f"Stored records: {repository.count_jobs()}."
        )
        if hasattr(adapter, "diagnostics"):
            try:
                diag = adapter.diagnostics.as_dict()  # type: ignore[attr-defined]
                print(json.dumps({"acquisition_diagnostics": diag}, ensure_ascii=True))
            except Exception:
                pass
        print(
            json.dumps(
                {
                    "persistence_summary": {
                        "persisted": result.stored,
                        "inserted": result.inserted,
                        "updated": result.updated,
                        "stored_records": repository.count_jobs(),
                    }
                },
                ensure_ascii=True,
            )
        )
        for evaluation in result.evaluations[: args.limit]:
            print(json.dumps(evaluator.as_dict(evaluation), ensure_ascii=True))
        return 0

    @staticmethod
    def run_harvest(args: argparse.Namespace) -> int:
        """Run one harvest pass and print the harvest summary."""
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

    @staticmethod
    def run_runtime_command(args: argparse.Namespace) -> int:
        """Delegate operational helper commands to the runtime dispatcher."""
        dispatcher = HarvestCronScripts(Path(__file__))
        argv = [str(Path(__file__)), args.command]
        if args.command == "show-recent-jobs":
            argv.append(str(args.limit))
        return dispatcher.run(argv)


def build_parser() -> argparse.ArgumentParser:
    """Expose parser creation for tests and script execution."""
    return RuntimeEntrypoints.build_parser()


def main(argv: list[str] | None = None) -> int:
    """Expose the CLI main function at module scope."""
    return RuntimeEntrypoints.main(argv)


def _run_ingest(args: argparse.Namespace) -> int:
    """Expose ingest execution at module scope for patch-friendly tests."""
    return RuntimeEntrypoints.run_ingest(args)


def _run_harvest(args: argparse.Namespace) -> int:
    """Expose harvest execution at module scope for patch-friendly tests."""
    return RuntimeEntrypoints.run_harvest(args)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["RuntimeEntrypoints", "build_parser", "main", "_run_ingest", "_run_harvest"]
