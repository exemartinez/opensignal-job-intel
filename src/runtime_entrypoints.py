"""Runtime entrypoints and command dispatch for the refactored system.

Author: Ezequiel H. Martinez
"""

from __future__ import annotations

import argparse
import concurrent.futures
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
from src.indeed_acquisition import IndeedJsonFileAdapter, IndeedScrapeAdapter
from src.linkedin_acquisition import LinkedInJsonFileAdapter, LinkedInScrapeAdapter
from src.wellfound_acquisition import WellfoundJsonFileAdapter, WellfoundScrapeAdapter
from src.persistence_runtime_ops import HarvestCronScripts, SQLiteJobRepository


def _fetch_jobs_for_source(
    *,
    source: str,
    compass_file: str,
    extraction_spec: str,
    max_jobs: int,
    capture_dir: str | None,
    schedule_file: str | None,
) -> tuple[str, list, dict | None]:
    """Fetch canonical jobs for one source inside a child process.

    This function is module-level (not nested) so it is picklable under the
    macOS multiprocessing spawn model used by ProcessPoolExecutor.
    """
    compass = load_professional_compass(compass_file)
    if source == "LinkedIn":
        adapter = LinkedInScrapeAdapter(
            compass=compass,
            extraction_spec_path=extraction_spec,
            max_jobs=max_jobs,
            capture_dir=capture_dir,
            write_fixture_path=None,
        )
    elif source == "Indeed":
        adapter = IndeedScrapeAdapter(
            compass=compass,
            max_jobs=max_jobs,
            capture_dir=capture_dir,
            write_fixture_path=None,
        )
    elif source == "Wellfound":
        adapter = WellfoundScrapeAdapter(
            compass=compass,
            max_jobs=max_jobs,
            capture_dir=capture_dir,
            write_fixture_path=None,
            schedule_path=schedule_file,
        )
    else:
        raise ValueError(f"Unsupported source: {source}")

    jobs = adapter.fetch_jobs()
    diagnostics = None
    if hasattr(adapter, "diagnostics"):
        try:
            diagnostics = adapter.diagnostics.as_dict()  # type: ignore[attr-defined]
        except Exception:
            diagnostics = None
    return source, jobs, diagnostics


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

        indeed = subparsers.add_parser(
            "ingest-indeed",
            help="Ingest Indeed jobs (fixture mode or live acquisition) into SQLite and score them.",
        )
        indeed.add_argument("--compass-file", default="profiles/professional_compass.json")
        indeed.add_argument("--source-file")
        indeed.add_argument("--max-jobs", type=int, default=30)
        indeed.add_argument("--capture-dir", default=None)
        indeed.add_argument("--write-fixture", default=None)
        indeed.add_argument("--db-path", default="data/jobs.db")
        indeed.add_argument("--limit", type=int, default=10)

        wellfound = subparsers.add_parser(
            "ingest-wellfound",
            help="Ingest Wellfound jobs (fixture mode or live acquisition) into SQLite and score them.",
        )
        wellfound.add_argument("--compass-file", default="profiles/professional_compass.json")
        wellfound.add_argument("--source-file")
        wellfound.add_argument("--max-jobs", type=int, default=30)
        wellfound.add_argument("--capture-dir", default=None)
        wellfound.add_argument("--write-fixture", default=None)
        wellfound.add_argument(
            "--schedule-file",
            default=None,
            help="YAML schedule/config file (defaults to profiles/extraction_schedule.now.yaml when present).",
        )
        wellfound.add_argument("--db-path", default="data/jobs.db")
        wellfound.add_argument("--limit", type=int, default=10)

        ingest_all = subparsers.add_parser(
            "ingest-all",
            help="Ingest LinkedIn + Indeed + Wellfound in one run (parallel acquisition, serialized SQLite writes).",
        )
        ingest_all.add_argument("--compass-file", default="profiles/professional_compass.json")
        ingest_all.add_argument(
            "--extraction-spec",
            default="config/linkedin_extraction.template.json",
            help="LinkedIn extraction spec path (used only for LinkedIn).",
        )
        ingest_all.add_argument("--max-jobs", type=int, default=30)
        ingest_all.add_argument(
            "--capture-dir",
            default=None,
            help="Base capture directory. Per-source subfolders will be created under this directory.",
        )
        ingest_all.add_argument(
            "--schedule-file",
            default=None,
            help="Wellfound schedule/config file (defaults to profiles/extraction_schedule.now.yaml when present).",
        )
        ingest_all.add_argument("--db-path", default="data/jobs.db")
        ingest_all.add_argument("--limit", type=int, default=10)
        ingest_all.add_argument(
            "--workers",
            type=int,
            default=3,
            help="Number of parallel acquisition workers (one per source by default).",
        )

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
        if args.command == "ingest-indeed":
            return _run_indeed_ingest(args)
        if args.command == "ingest-wellfound":
            return _run_wellfound_ingest(args)
        if args.command == "ingest-all":
            return _run_all_ingest(args)
        if args.command == "harvest-linkedin":
            return _run_harvest(args)
        return RuntimeEntrypoints.run_runtime_command(args)

    @staticmethod
    def run_ingest(args: argparse.Namespace) -> int:
        """Run fixture or live LinkedIn ingestion and print the summary."""
        return RuntimeEntrypoints._run_source_ingest(
            args=args,
            source_label="LinkedIn",
            fixture_adapter_cls=LinkedInJsonFileAdapter,
            live_adapter_factory=lambda compass: LinkedInScrapeAdapter(
                compass=compass,
                extraction_spec_path=args.extraction_spec,
                max_jobs=args.max_jobs,
                capture_dir=args.capture_dir,
                write_fixture_path=args.write_fixture,
            ),
        )

    @staticmethod
    def run_indeed_ingest(args: argparse.Namespace) -> int:
        """Run fixture or live Indeed ingestion and print the summary."""
        return RuntimeEntrypoints._run_source_ingest(
            args=args,
            source_label="Indeed",
            fixture_adapter_cls=IndeedJsonFileAdapter,
            live_adapter_factory=lambda compass: IndeedScrapeAdapter(
                compass=compass,
                max_jobs=args.max_jobs,
                capture_dir=args.capture_dir,
                write_fixture_path=args.write_fixture,
            ),
        )

    @staticmethod
    def run_wellfound_ingest(args: argparse.Namespace) -> int:
        """Run fixture or live Wellfound ingestion and print the summary."""
        return RuntimeEntrypoints._run_source_ingest(
            args=args,
            source_label="Wellfound",
            fixture_adapter_cls=WellfoundJsonFileAdapter,
            live_adapter_factory=lambda compass: WellfoundScrapeAdapter(
                compass=compass,
                max_jobs=args.max_jobs,
                capture_dir=args.capture_dir,
                write_fixture_path=args.write_fixture,
                schedule_path=args.schedule_file,
            ),
        )

    @staticmethod
    def run_all_ingest(args: argparse.Namespace) -> int:
        """Run LinkedIn + Indeed + Wellfound acquisition in parallel, then persist sequentially."""
        repository = SQLiteJobRepository(Path(args.db_path))
        repository.initialize()
        compass = load_professional_compass(args.compass_file)
        evaluator = JobCompassEvaluator(compass)

        base_capture_dir = Path(args.capture_dir) if args.capture_dir else None
        linkedin_capture = str(base_capture_dir / "linkedin") if base_capture_dir else None
        indeed_capture = str(base_capture_dir / "indeed") if base_capture_dir else None
        wellfound_capture = str(base_capture_dir / "wellfound") if base_capture_dir else None

        acquisition_errors: dict[str, str] = {}
        acquired_jobs: dict[str, list] = {}
        acquisition_diagnostics: dict[str, dict] = {}

        source_args = {
            "LinkedIn": {
                "capture_dir": linkedin_capture,
                "schedule_file": None,
            },
            "Indeed": {
                "capture_dir": indeed_capture,
                "schedule_file": None,
            },
            "Wellfound": {
                "capture_dir": wellfound_capture,
                "schedule_file": args.schedule_file,
            },
        }

        # True multiprocessing: each source acquisition runs in its own process.
        with concurrent.futures.ProcessPoolExecutor(max_workers=max(1, int(args.workers))) as executor:
            futures = {}
            for source, extra in source_args.items():
                futures[
                    executor.submit(
                        _fetch_jobs_for_source,
                        source=source,
                        compass_file=args.compass_file,
                        extraction_spec=args.extraction_spec,
                        max_jobs=args.max_jobs,
                        capture_dir=extra["capture_dir"],
                        schedule_file=extra["schedule_file"],
                    )
                ] = source

            for future in concurrent.futures.as_completed(futures):
                source = futures[future]
                try:
                    returned_source, jobs, diagnostics = future.result()
                    acquired_jobs[returned_source] = jobs
                    if diagnostics is not None:
                        acquisition_diagnostics[returned_source] = diagnostics
                except Exception as exc:  # pragma: no cover
                    acquisition_errors[source] = f"{type(exc).__name__}: {exc}"
                    acquired_jobs[source] = []

        total_stored = 0
        total_inserted = 0
        total_updated = 0
        all_evaluations = []
        per_source_summary: dict[str, dict[str, int]] = {}

        # Serialize SQLite writes to avoid lock contention from concurrent writers.
        for source in ("LinkedIn", "Indeed", "Wellfound"):
            jobs = [job.normalized() for job in acquired_jobs.get(source, [])]
            stored = 0
            inserted = 0
            updated = 0
            for job in jobs:
                was_inserted = repository.upsert_job(job)
                all_evaluations.append(evaluator.evaluate(job))
                stored += 1
                if was_inserted:
                    inserted += 1
                else:
                    updated += 1
            per_source_summary[source] = {
                "fetched": len(jobs),
                "persisted": stored,
                "inserted": inserted,
                "updated": updated,
            }
            total_stored += stored
            total_inserted += inserted
            total_updated += updated

        print(
            f"Loaded compass from {args.compass_file}. "
            f"Persisted {total_stored} jobs into {args.db_path} "
            f"(new: {total_inserted}, updated: {total_updated}). "
            f"Stored records: {repository.count_jobs()}."
        )

        if acquisition_diagnostics:
            print(json.dumps({"acquisition_diagnostics": acquisition_diagnostics}, ensure_ascii=True))

        if acquisition_errors:
            print(json.dumps({"acquisition_errors": acquisition_errors}, ensure_ascii=True))

        print(
            json.dumps(
                {
                    "ingest_all_summary": {
                        "per_source": per_source_summary,
                        "persisted": total_stored,
                        "inserted": total_inserted,
                        "updated": total_updated,
                        "stored_records": repository.count_jobs(),
                    }
                },
                ensure_ascii=True,
            )
        )

        for evaluation in all_evaluations[: args.limit]:
            print(json.dumps(evaluator.as_dict(evaluation), ensure_ascii=True))
        return 0
    @staticmethod
    def _run_source_ingest(
        *,
        args: argparse.Namespace,
        source_label: str,
        fixture_adapter_cls,
        live_adapter_factory,
    ) -> int:
        """Run one source-specific ingestion flow through the shared service."""
        repository = SQLiteJobRepository(Path(args.db_path))
        repository.initialize()
        compass = load_professional_compass(args.compass_file)

        if args.source_file:
            adapter = fixture_adapter_cls(args.source_file)
        else:
            adapter = live_adapter_factory(compass)
        evaluator = JobCompassEvaluator(compass)
        service = JobIngestionService(
            adapter=adapter,
            repository=repository,
            evaluator=evaluator,
        )
        result = service.ingest()

        print(
            f"Loaded compass from {args.compass_file}. "
            f"Persisted {result.stored} {source_label} jobs into {args.db_path} "
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


def _run_indeed_ingest(args: argparse.Namespace) -> int:
    """Expose Indeed ingest execution at module scope for patch-friendly tests."""
    return RuntimeEntrypoints.run_indeed_ingest(args)

def _run_wellfound_ingest(args: argparse.Namespace) -> int:
    """Expose Wellfound ingest execution at module scope for patch-friendly tests."""
    return RuntimeEntrypoints.run_wellfound_ingest(args)

def _run_all_ingest(args: argparse.Namespace) -> int:
    """Expose the multi-source ingest execution at module scope for tests."""
    return RuntimeEntrypoints.run_all_ingest(args)


def _run_harvest(args: argparse.Namespace) -> int:
    """Expose harvest execution at module scope for patch-friendly tests."""
    return RuntimeEntrypoints.run_harvest(args)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "RuntimeEntrypoints",
    "build_parser",
    "main",
    "_run_ingest",
    "_run_indeed_ingest",
    "_run_wellfound_ingest",
    "_run_all_ingest",
    "_run_harvest",
]
