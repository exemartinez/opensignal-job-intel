"""Runtime entrypoints and command dispatch for the refactored system.

Author: Ezequiel H. Martinez
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shutil
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

try:
    from src.indeed_acquisition import IndeedJsonFileAdapter, IndeedScrapeAdapter
    _INDEED_IMPORT_ERROR: Exception | None = None
except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
    IndeedJsonFileAdapter = None  # type: ignore[assignment]
    IndeedScrapeAdapter = None  # type: ignore[assignment]
    _INDEED_IMPORT_ERROR = exc

try:
    from src.wellfound_acquisition import WellfoundJsonFileAdapter, WellfoundScrapeAdapter
    _WELLFOUND_IMPORT_ERROR: Exception | None = None
except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
    WellfoundJsonFileAdapter = None  # type: ignore[assignment]
    WellfoundScrapeAdapter = None  # type: ignore[assignment]
    _WELLFOUND_IMPORT_ERROR = exc

SUPPORTED_HARVEST_ALL_SOURCES = ("linkedin", "indeed", "wellfound")


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

        harvest_all = subparsers.add_parser(
            "harvest-all",
            help="Run unattended multi-source harvest (LinkedIn + Indeed + Wellfound) with source-isolated failures.",
        )
        harvest_all.add_argument("--compass-file", default="profiles/professional_compass.json")
        harvest_all.add_argument(
            "--extraction-spec",
            default="config/linkedin_extraction.template.json",
        )
        harvest_all.add_argument("--schedule-file", default=None)
        harvest_all.add_argument("--capture-dir", default=None)
        harvest_all.add_argument("--db-path", default="data/jobs.db")
        harvest_all.add_argument("--max-jobs", type=int, default=30)
        harvest_all.add_argument(
            "--sources",
            default="linkedin,indeed,wellfound",
            help="Comma-separated sources to run from: linkedin,indeed,wellfound",
        )

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
        if args.command == "harvest-all":
            return _run_harvest_all(args)
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
        if IndeedJsonFileAdapter is None or IndeedScrapeAdapter is None:
            raise RuntimeError(f"Indeed source unavailable: {_INDEED_IMPORT_ERROR}")
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
        if WellfoundJsonFileAdapter is None or WellfoundScrapeAdapter is None:
            raise RuntimeError(f"Wellfound source unavailable: {_WELLFOUND_IMPORT_ERROR}")
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
    def run_harvest_all(args: argparse.Namespace) -> int:
        """Run unattended multi-source harvest with Linux preflight and isolation."""
        sources = _parse_harvest_sources(args.sources)
        global_errors, source_preflight_errors = _run_linux_harvest_preflight(
            sources=sources,
            db_path=args.db_path,
            compass_file=args.compass_file,
            extraction_spec=args.extraction_spec,
        )
        if global_errors:
            print(json.dumps({"harvest_all_preflight_errors": {"global": global_errors}}, ensure_ascii=True))
            return 1

        repository = SQLiteJobRepository(Path(args.db_path))
        repository.initialize()
        compass = load_professional_compass(args.compass_file)
        schedule_path = resolve_harvest_schedule_path(args.schedule_file)
        schedule = load_harvest_schedule(schedule_path)

        base_capture_dir = Path(args.capture_dir) if args.capture_dir else None
        source_results: dict[str, dict[str, object]] = {}
        total_persisted = 0
        total_inserted = 0
        total_updated = 0

        for source in sources:
            pretty = source.title() if source != "linkedin" else "LinkedIn"
            source_capture_dir = str(base_capture_dir / source) if base_capture_dir else None
            preflight_error = source_preflight_errors.get(source)
            if preflight_error:
                source_results[pretty] = {
                    "status": "skipped",
                    "fetched": 0,
                    "persisted": 0,
                    "inserted": 0,
                    "updated": 0,
                    "error": preflight_error,
                }
                continue

            try:
                if source == "linkedin":
                    harvester = LinkedInNightlyHarvester(
                        compass=compass,
                        repository=repository,
                        extraction_spec_path=args.extraction_spec,
                        schedule=schedule,
                        capture_dir=source_capture_dir,
                        max_jobs=args.max_jobs,
                    )
                    harvest_result = harvester.run()
                    persisted = int(harvest_result.stored)
                    source_results[pretty] = {
                        "status": "ok",
                        "fetched": persisted,
                        "persisted": persisted,
                        "inserted": persisted,
                        "updated": 0,
                        "harvest_summary": harvest_result.as_dict(),
                    }
                    total_persisted += persisted
                    total_inserted += persisted
                    continue

                if source == "indeed":
                    if IndeedScrapeAdapter is None:
                        raise RuntimeError(f"Indeed source unavailable: {_INDEED_IMPORT_ERROR}")
                    adapter = IndeedScrapeAdapter(
                        compass=compass,
                        max_jobs=args.max_jobs,
                        capture_dir=source_capture_dir,
                        write_fixture_path=None,
                    )
                elif source == "wellfound":
                    if WellfoundScrapeAdapter is None:
                        raise RuntimeError(f"Wellfound source unavailable: {_WELLFOUND_IMPORT_ERROR}")
                    adapter = WellfoundScrapeAdapter(
                        compass=compass,
                        max_jobs=args.max_jobs,
                        capture_dir=source_capture_dir,
                        write_fixture_path=None,
                        schedule_path=args.schedule_file,
                    )
                else:  # pragma: no cover
                    raise ValueError(f"Unsupported source: {source}")

                jobs = [job.normalized() for job in adapter.fetch_jobs()]
                inserted = 0
                updated = 0
                for job in jobs:
                    was_inserted = repository.upsert_job(job)
                    if was_inserted:
                        inserted += 1
                    else:
                        updated += 1
                persisted = inserted + updated
                diagnostics_payload = None
                source_payload: dict[str, object] = {
                    "status": "ok",
                    "fetched": len(jobs),
                    "persisted": persisted,
                    "inserted": inserted,
                    "updated": updated,
                }
                if hasattr(adapter, "diagnostics"):
                    try:
                        diagnostics_payload = adapter.diagnostics.as_dict()  # type: ignore[attr-defined]
                        source_payload["acquisition_diagnostics"] = diagnostics_payload
                    except Exception:
                        pass
                failure_reason = _diagnostics_failure_reason(diagnostics_payload)
                if failure_reason:
                    source_payload["status"] = "failed"
                    source_payload["error"] = failure_reason
                source_results[pretty] = source_payload
                if source_payload["status"] == "ok":
                    total_persisted += persisted
                    total_inserted += inserted
                    total_updated += updated
            except Exception as exc:
                source_results[pretty] = {
                    "status": "failed",
                    "fetched": 0,
                    "persisted": 0,
                    "inserted": 0,
                    "updated": 0,
                    "error": f"{type(exc).__name__}: {exc}",
                }

        print(
            json.dumps(
                {
                    "harvest_all_summary": {
                        "sources": source_results,
                        "persisted": total_persisted,
                        "inserted": total_inserted,
                        "updated": total_updated,
                        "stored_records": repository.count_jobs(),
                        "schedule_file": schedule_path,
                    }
                },
                ensure_ascii=True,
            )
        )
        has_success = any(payload.get("status") == "ok" for payload in source_results.values())
        has_failure = any(payload.get("status") in {"failed", "skipped"} for payload in source_results.values())
        if not has_success:
            return 1
        return 2 if has_failure else 0

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

def _run_harvest_all(args: argparse.Namespace) -> int:
    """Expose multi-source harvest execution at module scope for patch-friendly tests."""
    return RuntimeEntrypoints.run_harvest_all(args)


def _parse_harvest_sources(raw_sources: str) -> list[str]:
    values = [value.strip().lower() for value in raw_sources.split(",") if value.strip()]
    if not values:
        raise ValueError("At least one source must be provided to --sources.")
    unsupported = [value for value in values if value not in SUPPORTED_HARVEST_ALL_SOURCES]
    if unsupported:
        raise ValueError(
            "Unsupported sources for --sources: "
            + ", ".join(sorted(dict.fromkeys(unsupported)))
            + ". Supported: "
            + ",".join(SUPPORTED_HARVEST_ALL_SOURCES)
        )
    return list(dict.fromkeys(values))


def _run_linux_harvest_preflight(
    *,
    sources: list[str],
    db_path: str,
    compass_file: str,
    extraction_spec: str,
) -> tuple[list[str], dict[str, str]]:
    global_errors: list[str] = []
    source_errors: dict[str, str] = {}

    if not Path(compass_file).exists():
        global_errors.append(f"Missing compass file: {compass_file}")
    if not Path(extraction_spec).exists():
        source_errors["linkedin"] = f"Missing LinkedIn extraction spec: {extraction_spec}"
    try:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        global_errors.append(f"Unable to prepare db directory for {db_path}: {type(exc).__name__}: {exc}")

    if not sys.platform.startswith("linux"):
        return global_errors, source_errors

    if "indeed" in sources and (IndeedScrapeAdapter is None or IndeedJsonFileAdapter is None):
        source_errors["indeed"] = f"Missing Indeed runtime dependency: {_INDEED_IMPORT_ERROR}"
    if "wellfound" in sources and (WellfoundScrapeAdapter is None or WellfoundJsonFileAdapter is None):
        source_errors["wellfound"] = f"Missing Wellfound runtime dependency: {_WELLFOUND_IMPORT_ERROR}"

    browser_name = os.environ.get("INDEED_BROWSER", "chrome").strip().lower()
    if "indeed" in sources and browser_name == "safari":
        source_errors["indeed"] = (
            "INDEED_BROWSER=safari is unsupported on Linux. Use chrome or firefox."
        )
    if "indeed" in sources and browser_name in {"chrome", "chromium"}:
        candidates = ("google-chrome", "chromium-browser", "chromium", "chrome")
        if all(shutil.which(candidate) is None for candidate in candidates):
            source_errors["indeed"] = (
                "No Chrome/Chromium executable found in PATH for Indeed harvesting."
            )
    if "indeed" in sources and browser_name == "firefox":
        if shutil.which("firefox") is None:
            source_errors["indeed"] = "No Firefox executable found in PATH for Indeed harvesting."

    return global_errors, source_errors


def _diagnostics_failure_reason(diagnostics: dict | None) -> str | None:
    if not diagnostics:
        return None
    drops = diagnostics.get("drops")
    if not isinstance(drops, list):
        return None
    for value in drops:
        if not isinstance(value, str):
            continue
        if value.startswith("browser_session_failed:"):
            return value
        if value.startswith("browser_error:"):
            return value
    return None


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
    "_run_harvest_all",
]
