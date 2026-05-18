from __future__ import annotations

import argparse
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src import runtime_entrypoints as cli
from src.core_domain_inputs import JobRecord, JobSource


class CliTests(unittest.TestCase):
    def test_main_dispatches_ingest_command(self) -> None:
        parser = Mock()
        parser.parse_args.return_value = argparse.Namespace(command="ingest-linkedin")

        with (
            patch("src.runtime_entrypoints.build_parser", return_value=parser),
            patch("src.runtime_entrypoints._run_ingest", return_value=7) as run_ingest,
        ):
            result = cli.main()

        self.assertEqual(7, result)
        run_ingest.assert_called_once_with(parser.parse_args.return_value)

    def test_main_dispatches_harvest_command(self) -> None:
        parser = Mock()
        parser.parse_args.return_value = argparse.Namespace(command="harvest-linkedin")

        with (
            patch("src.runtime_entrypoints.build_parser", return_value=parser),
            patch("src.runtime_entrypoints._run_harvest", return_value=9) as run_harvest,
        ):
            result = cli.main()

        self.assertEqual(9, result)
        run_harvest.assert_called_once_with(parser.parse_args.return_value)

    def test_main_dispatches_indeed_ingest_command(self) -> None:
        parser = Mock()
        parser.parse_args.return_value = argparse.Namespace(command="ingest-indeed")

        with (
            patch("src.runtime_entrypoints.build_parser", return_value=parser),
            patch("src.runtime_entrypoints._run_indeed_ingest", return_value=5) as run_ingest,
        ):
            result = cli.main()

        self.assertEqual(5, result)
        run_ingest.assert_called_once_with(parser.parse_args.return_value)

    def test_main_dispatches_wellfound_ingest_command(self) -> None:
        parser = Mock()
        parser.parse_args.return_value = argparse.Namespace(command="ingest-wellfound")

        with (
            patch("src.runtime_entrypoints.build_parser", return_value=parser),
            patch("src.runtime_entrypoints._run_wellfound_ingest", return_value=6) as run_ingest,
        ):
            result = cli.main()

        self.assertEqual(6, result)
        run_ingest.assert_called_once_with(parser.parse_args.return_value)

    def test_main_dispatches_ingest_all_command(self) -> None:
        parser = Mock()
        parser.parse_args.return_value = argparse.Namespace(command="ingest-all")

        with (
            patch("src.runtime_entrypoints.build_parser", return_value=parser),
            patch("src.runtime_entrypoints._run_all_ingest", return_value=4) as run_ingest,
        ):
            result = cli.main()

        self.assertEqual(4, result)
        run_ingest.assert_called_once_with(parser.parse_args.return_value)

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
        compass = SimpleNamespace(search_max_post_age_days=None)
        result = SimpleNamespace(fetched=2, stored=2, inserted=1, updated=1, evaluations=[])

        with (
            patch("src.runtime_entrypoints.SQLiteJobRepository", return_value=repository),
            patch("src.runtime_entrypoints.load_professional_compass", return_value=compass),
            patch("src.runtime_entrypoints.LinkedInJsonFileAdapter", return_value="fixture-adapter") as json_adapter,
            patch("src.runtime_entrypoints.LinkedInScrapeAdapter") as scrape_adapter,
            patch("src.runtime_entrypoints.JobCompassEvaluator", return_value="evaluator") as evaluator,
            patch("src.runtime_entrypoints.JobIngestionService") as service_cls,
            patch("builtins.print") as print_mock,
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
        self.assertEqual(2, print_mock.call_count)

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
        compass = SimpleNamespace(search_max_post_age_days=None)
        result = SimpleNamespace(fetched=0, stored=0, inserted=0, updated=0, evaluations=[])

        with (
            patch("src.runtime_entrypoints.SQLiteJobRepository", return_value=repository),
            patch("src.runtime_entrypoints.load_professional_compass", return_value=compass),
            patch("src.runtime_entrypoints.LinkedInJsonFileAdapter") as json_adapter,
            patch("src.runtime_entrypoints.LinkedInScrapeAdapter", return_value="scrape-adapter") as scrape_adapter,
            patch("src.runtime_entrypoints.JobCompassEvaluator", return_value="evaluator"),
            patch("src.runtime_entrypoints.JobIngestionService") as service_cls,
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
        compass = SimpleNamespace(search_max_post_age_days=None)
        schedule = object()
        result = SimpleNamespace(as_dict=lambda: {"stored": 4})

        with (
            patch("src.runtime_entrypoints.SQLiteJobRepository", return_value=repository),
            patch("src.runtime_entrypoints.load_professional_compass", return_value=compass),
            patch("src.runtime_entrypoints.resolve_harvest_schedule_path", return_value="config/extraction_schedule.yaml") as resolve_schedule,
            patch("src.runtime_entrypoints.load_harvest_schedule", return_value=schedule) as load_schedule,
            patch("src.runtime_entrypoints.LinkedInNightlyHarvester") as harvester_cls,
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

    def test_run_all_ingest_acquires_in_parallel_and_persists_sequentially(self) -> None:
        args = argparse.Namespace(
            compass_file="profiles/professional_compass.json",
            extraction_spec="config/linkedin_extraction.template.json",
            max_jobs=30,
            capture_dir=None,
            schedule_file=None,
            db_path="data/jobs.db",
            limit=10,
            workers=3,
        )

        now = datetime(2026, 5, 15, tzinfo=timezone.utc)
        linkedin_job = JobRecord(
            source=JobSource.LINKEDIN,
            company="Co",
            title="T",
            description="D",
            link="https://www.linkedin.com/jobs/view/1",
            collected_at=now,
            external_job_id="1",
        )
        indeed_job = JobRecord(
            source=JobSource.INDEED,
            company="Co2",
            title="T2",
            description="D2",
            link="https://www.indeed.com/viewjob?jk=abc",
            collected_at=now,
            external_job_id="abc",
        )
        wellfound_job = JobRecord(
            source=JobSource.WELLFOUND,
            company="Co3",
            title="T3",
            description="D3",
            link="https://wellfound.com/jobs/123-job",
            collected_at=now,
            external_job_id="123",
        )

        repository = Mock()
        repository.count_jobs.return_value = 3
        repository.upsert_job.side_effect = [True, False, True]
        compass = SimpleNamespace(search_max_post_age_days=None)
        evaluator = Mock()
        evaluator.evaluate.side_effect = [object(), object(), object()]
        evaluator.as_dict.return_value = {"company": "x"}

        class DummyProcessPoolExecutor:
            def __init__(self, *args, **kwargs) -> None:
                pass

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> bool:
                return False

            def submit(self, fn, **kwargs):
                future = Mock()
                source = kwargs["source"]
                if source == "LinkedIn":
                    future.result.return_value = ("LinkedIn", [linkedin_job], None)
                elif source == "Indeed":
                    future.result.return_value = ("Indeed", [indeed_job], None)
                elif source == "Wellfound":
                    future.result.return_value = ("Wellfound", [wellfound_job], None)
                else:
                    future.result.return_value = (source, [], None)
                return future

        with (
            patch("src.runtime_entrypoints.SQLiteJobRepository", return_value=repository),
            patch("src.runtime_entrypoints.load_professional_compass", return_value=compass),
            patch("src.runtime_entrypoints.JobCompassEvaluator", return_value=evaluator),
            patch("src.runtime_entrypoints.concurrent.futures.ProcessPoolExecutor", DummyProcessPoolExecutor),
            patch("src.runtime_entrypoints.concurrent.futures.as_completed", lambda futures: list(futures)),
            patch("builtins.print"),
        ):
            exit_code = cli._run_all_ingest(args)

        self.assertEqual(0, exit_code)
        repository.initialize.assert_called_once_with()
        self.assertEqual(3, repository.upsert_job.call_count)
        evaluator.evaluate.assert_called()

    def test_build_parser_defaults_harvest_schedule_help_to_config_paths(self) -> None:
        parser = cli.build_parser()
        schedule_actions = [
            action
            for action in parser._actions  # type: ignore[attr-defined]
            if getattr(action, "dest", None) == "command"
        ]

        self.assertTrue(schedule_actions)
        self.assertIsInstance(Path("config/extraction_schedule.yaml"), Path)

    def test_run_indeed_ingest_uses_fixture_adapter_when_source_file_is_provided(self) -> None:
        args = argparse.Namespace(
            compass_file="profiles/professional_compass.json",
            source_file="sample_indeed_jobs.json",
            max_jobs=30,
            capture_dir=None,
            write_fixture=None,
            db_path="data/jobs.db",
            limit=10,
        )
        repository = Mock()
        repository.count_jobs.return_value = 3
        compass = SimpleNamespace(search_max_post_age_days=None)
        result = SimpleNamespace(fetched=2, stored=2, inserted=1, updated=1, evaluations=[])

        with (
            patch("src.runtime_entrypoints.SQLiteJobRepository", return_value=repository),
            patch("src.runtime_entrypoints.load_professional_compass", return_value=compass),
            patch("src.runtime_entrypoints.IndeedJsonFileAdapter", return_value="fixture-adapter") as json_adapter,
            patch("src.runtime_entrypoints.IndeedScrapeAdapter") as scrape_adapter,
            patch("src.runtime_entrypoints.JobCompassEvaluator", return_value="evaluator") as evaluator,
            patch("src.runtime_entrypoints.JobIngestionService") as service_cls,
            patch("builtins.print"),
        ):
            service = service_cls.return_value
            service.ingest.return_value = result
            exit_code = cli._run_indeed_ingest(args)

        self.assertEqual(0, exit_code)
        repository.initialize.assert_called_once_with()
        json_adapter.assert_called_once_with("sample_indeed_jobs.json")
        scrape_adapter.assert_not_called()
        evaluator.assert_called_once_with(compass)
        service_cls.assert_called_once_with(
            adapter="fixture-adapter",
            repository=repository,
            evaluator="evaluator",
        )
        service.ingest.assert_called_once_with()

    def test_run_indeed_ingest_uses_live_scrape_adapter_without_source_file(self) -> None:
        args = argparse.Namespace(
            compass_file="profiles/professional_compass.json",
            source_file=None,
            max_jobs=25,
            capture_dir="data/captures",
            write_fixture="data/fixture.json",
            db_path="data/jobs.db",
            limit=10,
        )
        repository = Mock()
        repository.count_jobs.return_value = 0
        compass = SimpleNamespace(search_max_post_age_days=None)
        result = SimpleNamespace(fetched=0, stored=0, inserted=0, updated=0, evaluations=[])

        with (
            patch("src.runtime_entrypoints.SQLiteJobRepository", return_value=repository),
            patch("src.runtime_entrypoints.load_professional_compass", return_value=compass),
            patch("src.runtime_entrypoints.IndeedJsonFileAdapter") as json_adapter,
            patch("src.runtime_entrypoints.IndeedScrapeAdapter", return_value="scrape-adapter") as scrape_adapter,
            patch("src.runtime_entrypoints.JobCompassEvaluator", return_value="evaluator"),
            patch("src.runtime_entrypoints.JobIngestionService") as service_cls,
            patch("builtins.print"),
        ):
            service_cls.return_value.ingest.return_value = result
            exit_code = cli._run_indeed_ingest(args)

        self.assertEqual(0, exit_code)
        json_adapter.assert_not_called()
        scrape_adapter.assert_called_once_with(
            compass=compass,
            max_jobs=25,
            capture_dir="data/captures",
            write_fixture_path="data/fixture.json",
        )

    def test_run_wellfound_ingest_uses_fixture_adapter_when_source_file_is_provided(self) -> None:
        args = argparse.Namespace(
            compass_file="profiles/professional_compass.json",
            source_file="sample_wellfound_jobs.json",
            max_jobs=30,
            capture_dir=None,
            write_fixture=None,
            schedule_file=None,
            db_path="data/jobs.db",
            limit=10,
        )
        repository = Mock()
        repository.count_jobs.return_value = 3
        compass = SimpleNamespace(search_max_post_age_days=None)
        result = SimpleNamespace(fetched=2, stored=2, inserted=1, updated=1, evaluations=[])

        with (
            patch("src.runtime_entrypoints.SQLiteJobRepository", return_value=repository),
            patch("src.runtime_entrypoints.load_professional_compass", return_value=compass),
            patch("src.runtime_entrypoints.WellfoundJsonFileAdapter", return_value="fixture-adapter") as json_adapter,
            patch("src.runtime_entrypoints.WellfoundScrapeAdapter") as scrape_adapter,
            patch("src.runtime_entrypoints.JobCompassEvaluator", return_value="evaluator") as evaluator,
            patch("src.runtime_entrypoints.JobIngestionService") as service_cls,
            patch("builtins.print"),
        ):
            service = service_cls.return_value
            service.ingest.return_value = result
            exit_code = cli._run_wellfound_ingest(args)

        self.assertEqual(0, exit_code)
        repository.initialize.assert_called_once_with()
        json_adapter.assert_called_once_with("sample_wellfound_jobs.json")
        scrape_adapter.assert_not_called()
        evaluator.assert_called_once_with(compass)
        service_cls.assert_called_once_with(
            adapter="fixture-adapter",
            repository=repository,
            evaluator="evaluator",
        )
        service.ingest.assert_called_once_with()

    def test_run_wellfound_ingest_uses_live_scrape_adapter_without_source_file(self) -> None:
        args = argparse.Namespace(
            compass_file="profiles/professional_compass.json",
            source_file=None,
            max_jobs=25,
            capture_dir="data/captures",
            write_fixture="data/fixture.json",
            schedule_file=None,
            db_path="data/jobs.db",
            limit=10,
        )
        repository = Mock()
        repository.count_jobs.return_value = 0
        compass = SimpleNamespace(search_max_post_age_days=None)
        result = SimpleNamespace(fetched=0, stored=0, inserted=0, updated=0, evaluations=[])

        with (
            patch("src.runtime_entrypoints.SQLiteJobRepository", return_value=repository),
            patch("src.runtime_entrypoints.load_professional_compass", return_value=compass),
            patch("src.runtime_entrypoints.WellfoundJsonFileAdapter") as json_adapter,
            patch("src.runtime_entrypoints.WellfoundScrapeAdapter", return_value="scrape-adapter") as scrape_adapter,
            patch("src.runtime_entrypoints.JobCompassEvaluator", return_value="evaluator"),
            patch("src.runtime_entrypoints.JobIngestionService") as service_cls,
            patch("builtins.print"),
        ):
            service_cls.return_value.ingest.return_value = result
            exit_code = cli._run_wellfound_ingest(args)

        self.assertEqual(0, exit_code)
        json_adapter.assert_not_called()
        scrape_adapter.assert_called_once_with(
            compass=compass,
            max_jobs=25,
            capture_dir="data/captures",
            write_fixture_path="data/fixture.json",
            schedule_path=None,
        )

    def test_run_indeed_ingest_reports_inserted_and_updated_counts(self) -> None:
        args = argparse.Namespace(
            compass_file="profiles/professional_compass.json",
            source_file="sample_indeed_jobs.json",
            max_jobs=30,
            capture_dir=None,
            write_fixture=None,
            db_path="data/jobs.db",
            limit=1,
        )
        repository = Mock()
        repository.count_jobs.return_value = 12
        compass = SimpleNamespace(search_max_post_age_days=None)
        evaluator = Mock()
        evaluator.as_dict.return_value = {"company": "Example"}
        result = SimpleNamespace(
            fetched=2,
            stored=2,
            inserted=2,
            updated=0,
            evaluations=[object()],
        )

        with (
            patch("src.runtime_entrypoints.SQLiteJobRepository", return_value=repository),
            patch("src.runtime_entrypoints.load_professional_compass", return_value=compass),
            patch("src.runtime_entrypoints.IndeedJsonFileAdapter", return_value="fixture-adapter"),
            patch("src.runtime_entrypoints.JobCompassEvaluator", return_value=evaluator),
            patch("src.runtime_entrypoints.JobIngestionService") as service_cls,
            patch("builtins.print") as print_mock,
        ):
            service_cls.return_value.ingest.return_value = result
            exit_code = cli._run_indeed_ingest(args)

        self.assertEqual(0, exit_code)
        self.assertEqual(
            "Loaded compass from profiles/professional_compass.json. "
            "Persisted 2 Indeed jobs into data/jobs.db (new: 2, updated: 0). "
            "Stored records: 12.",
            print_mock.call_args_list[0].args[0],
        )

    def test_run_ingest_reports_inserted_and_updated_counts(self) -> None:
        args = argparse.Namespace(
            compass_file="profiles/professional_compass.json",
            source_file="sample_linkedin_jobs.json",
            extraction_spec="config/linkedin_extraction.template.json",
            max_jobs=30,
            capture_dir=None,
            write_fixture=None,
            db_path="data/jobs.db",
            limit=1,
        )
        repository = Mock()
        repository.count_jobs.return_value = 1728
        compass = SimpleNamespace(search_max_post_age_days=None)
        evaluator = Mock()
        evaluator.as_dict.return_value = {"company": "Synchro"}
        result = SimpleNamespace(
            fetched=3,
            stored=3,
            inserted=0,
            updated=3,
            evaluations=[object()],
        )

        with (
            patch("src.runtime_entrypoints.SQLiteJobRepository", return_value=repository),
            patch("src.runtime_entrypoints.load_professional_compass", return_value=compass),
            patch("src.runtime_entrypoints.LinkedInJsonFileAdapter", return_value="fixture-adapter"),
            patch("src.runtime_entrypoints.JobCompassEvaluator", return_value=evaluator),
            patch("src.runtime_entrypoints.JobIngestionService") as service_cls,
            patch("builtins.print") as print_mock,
        ):
            service_cls.return_value.ingest.return_value = result
            exit_code = cli._run_ingest(args)

        self.assertEqual(0, exit_code)
        self.assertEqual(
            "Loaded compass from profiles/professional_compass.json. "
            "Persisted 3 LinkedIn jobs into data/jobs.db (new: 0, updated: 3). "
            "Stored records: 1728.",
            print_mock.call_args_list[0].args[0],
        )
        self.assertEqual(
            '{"persistence_summary": {"persisted": 3, "inserted": 0, "updated": 3, "stored_records": 1728}}',
            print_mock.call_args_list[1].args[0],
        )


if __name__ == "__main__":
    unittest.main()
