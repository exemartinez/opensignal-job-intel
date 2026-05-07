from __future__ import annotations

import argparse
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from opensignal_job_intel import cli


class CliTests(unittest.TestCase):
    def test_main_dispatches_ingest_command(self) -> None:
        parser = Mock()
        parser.parse_args.return_value = argparse.Namespace(command="ingest-linkedin")

        with (
            patch("opensignal_job_intel.cli.build_parser", return_value=parser),
            patch("opensignal_job_intel.cli._run_ingest", return_value=7) as run_ingest,
        ):
            result = cli.main()

        self.assertEqual(7, result)
        run_ingest.assert_called_once_with(parser.parse_args.return_value)

    def test_main_dispatches_harvest_command(self) -> None:
        parser = Mock()
        parser.parse_args.return_value = argparse.Namespace(command="harvest-linkedin")

        with (
            patch("opensignal_job_intel.cli.build_parser", return_value=parser),
            patch("opensignal_job_intel.cli._run_harvest", return_value=9) as run_harvest,
        ):
            result = cli.main()

        self.assertEqual(9, result)
        run_harvest.assert_called_once_with(parser.parse_args.return_value)

    def test_run_ingest_uses_fixture_adapter_when_source_file_is_provided(self) -> None:
        args = argparse.Namespace(
            compass_file="profiles/professional_compass.json",
            source_file="sample_linkedin_jobs.json",
            extraction_spec="config/linkedin_extraction.template.json",
            max_jobs=30,
            capture_dir=None,
            write_fixture=None,
            db_path="data/jobs.db",
            limit=10,
        )
        repository = Mock()
        repository.count_jobs.return_value = 3
        compass = object()
        result = SimpleNamespace(fetched=2, evaluations=[])

        with (
            patch("opensignal_job_intel.cli.SQLiteJobRepository", return_value=repository),
            patch("opensignal_job_intel.cli.load_professional_compass", return_value=compass),
            patch("opensignal_job_intel.cli.LinkedInJsonFileAdapter", return_value="fixture-adapter") as json_adapter,
            patch("opensignal_job_intel.cli.LinkedInScrapeAdapter") as scrape_adapter,
            patch("opensignal_job_intel.cli.JobCompassEvaluator", return_value="evaluator") as evaluator,
            patch("opensignal_job_intel.cli.JobIngestionService") as service_cls,
            patch("builtins.print"),
        ):
            service = service_cls.return_value
            service.ingest.return_value = result
            exit_code = cli._run_ingest(args)

        self.assertEqual(0, exit_code)
        repository.initialize.assert_called_once_with()
        json_adapter.assert_called_once_with("sample_linkedin_jobs.json")
        scrape_adapter.assert_not_called()
        evaluator.assert_called_once_with(compass)
        service_cls.assert_called_once_with(
            adapter="fixture-adapter",
            repository=repository,
            evaluator="evaluator",
        )
        service.ingest.assert_called_once_with()

    def test_run_ingest_uses_live_scrape_adapter_without_source_file(self) -> None:
        args = argparse.Namespace(
            compass_file="profiles/professional_compass.json",
            source_file=None,
            extraction_spec="config/linkedin_extraction.template.json",
            max_jobs=25,
            capture_dir="data/captures",
            write_fixture="data/fixture.json",
            db_path="data/jobs.db",
            limit=10,
        )
        repository = Mock()
        repository.count_jobs.return_value = 0
        compass = object()
        result = SimpleNamespace(fetched=0, evaluations=[])

        with (
            patch("opensignal_job_intel.cli.SQLiteJobRepository", return_value=repository),
            patch("opensignal_job_intel.cli.load_professional_compass", return_value=compass),
            patch("opensignal_job_intel.cli.LinkedInJsonFileAdapter") as json_adapter,
            patch("opensignal_job_intel.cli.LinkedInScrapeAdapter", return_value="scrape-adapter") as scrape_adapter,
            patch("opensignal_job_intel.cli.JobCompassEvaluator", return_value="evaluator"),
            patch("opensignal_job_intel.cli.JobIngestionService") as service_cls,
            patch("builtins.print"),
        ):
            service_cls.return_value.ingest.return_value = result
            exit_code = cli._run_ingest(args)

        self.assertEqual(0, exit_code)
        json_adapter.assert_not_called()
        scrape_adapter.assert_called_once_with(
            compass=compass,
            extraction_spec_path="config/linkedin_extraction.template.json",
            max_jobs=25,
            capture_dir="data/captures",
            write_fixture_path="data/fixture.json",
        )

    def test_run_harvest_resolves_schedule_and_runs_harvester(self) -> None:
        args = argparse.Namespace(
            compass_file="profiles/professional_compass.json",
            extraction_spec="config/linkedin_extraction.template.json",
            schedule_file=None,
            capture_dir="data/captures",
            db_path="data/jobs.db",
            max_jobs=8,
        )
        repository = Mock()
        repository.count_jobs.return_value = 4
        compass = object()
        schedule = object()
        result = SimpleNamespace(as_dict=lambda: {"stored": 4})

        with (
            patch("opensignal_job_intel.cli.SQLiteJobRepository", return_value=repository),
            patch("opensignal_job_intel.cli.load_professional_compass", return_value=compass),
            patch("opensignal_job_intel.cli.resolve_harvest_schedule_path", return_value="config/extraction_schedule.yaml") as resolve_schedule,
            patch("opensignal_job_intel.cli.load_harvest_schedule", return_value=schedule) as load_schedule,
            patch("opensignal_job_intel.cli.LinkedInNightlyHarvester") as harvester_cls,
            patch("builtins.print") as print_mock,
        ):
            harvester_cls.return_value.run.return_value = result
            exit_code = cli._run_harvest(args)

        self.assertEqual(0, exit_code)
        resolve_schedule.assert_called_once_with(None)
        load_schedule.assert_called_once_with("config/extraction_schedule.yaml")
        harvester_cls.assert_called_once_with(
            compass=compass,
            repository=repository,
            extraction_spec_path="config/linkedin_extraction.template.json",
            schedule=schedule,
            capture_dir="data/captures",
            max_jobs=8,
        )
        print_mock.assert_called_once()

    def test_build_parser_defaults_harvest_schedule_help_to_config_paths(self) -> None:
        parser = cli.build_parser()
        schedule_actions = [
            action
            for action in parser._actions  # type: ignore[attr-defined]
            if getattr(action, "dest", None) == "command"
        ]

        self.assertTrue(schedule_actions)
        self.assertIsInstance(Path("config/extraction_schedule.yaml"), Path)


if __name__ == "__main__":
    unittest.main()
