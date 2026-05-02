from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import time
from pathlib import Path

from opensignal_job_intel.compass import load_professional_compass
from opensignal_job_intel.evaluation import JobCompassEvaluator
from opensignal_job_intel.models import (
    HarvestSchedule,
    JobRecord,
    JobSource,
    ProfessionalCompass,
    utc_now,
)
from opensignal_job_intel.repositories.sqlite_jobs import SQLiteJobRepository
from opensignal_job_intel.sources.linkedin import LinkedInJsonFileAdapter
from opensignal_job_intel.sources.linkedin_harvest import (
    _build_harvest_search_url,
    _derive_search_plans,
    _evaluate_harvest_filters,
    FetchResponse,
    LinkedInNightlyHarvester,
    load_harvest_schedule,
)
from opensignal_job_intel.sources.linkedin_acquire import _passes_filters
from opensignal_job_intel.sources.linkedin_acquire import _derive_region
from opensignal_job_intel.sources.linkedin_extraction import (
    LinkedInExtractionSpec,
    extract_job_from_detail_html,
    extract_job_ids_from_search_html,
    validate_extraction_spec,
)


class CompassTests(unittest.TestCase):
    def test_loads_professional_compass_from_json(self) -> None:
        compass = load_professional_compass("profiles/professional_compass.template.json")
        self.assertTrue(compass.remote_only)
        self.assertEqual(6000, compass.min_monthly_usd)
        self.assertIn("AI Architect (hands-on)", compass.target_roles)
        self.assertIsNotNone(compass.search_max_post_age_days)
        self.assertIsInstance(compass.search_workplace_types, list)
        self.assertIsInstance(compass.search_regions, list)


class LinkedInAdapterTests(unittest.TestCase):
    def test_normalizes_local_json_payload_into_canonical_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "linkedin.json"
            input_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "123",
                            "company": "Example Corp ",
                            "title": " Staff Data Architect ",
                            "description": " Build data systems ",
                            "posted_at": "2026-04-15T12:00:00Z",
                            "salary": "$7,000 - $10,000 monthly",
                            "link": "https://www.linkedin.com/jobs/view/123/?refId=abc",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            jobs = LinkedInJsonFileAdapter(input_path).fetch_jobs()

        self.assertEqual(1, len(jobs))
        job = jobs[0].normalized()
        self.assertEqual(JobSource.LINKEDIN, job.source)
        self.assertEqual("123", job.external_job_id)
        self.assertEqual("Example Corp", job.company)
        self.assertEqual("Staff Data Architect", job.title)
        self.assertEqual("Build data systems", job.description)
        self.assertEqual("$7,000 - $10,000 monthly", job.salary_text)
        self.assertEqual("https://www.linkedin.com/jobs/view/123", job.link)
        self.assertIsNotNone(job.post_datetime)


class SQLiteRepositoryTests(unittest.TestCase):
    def test_initializes_jobs_table(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "jobs.db"
            repository = SQLiteJobRepository(db_path)
            repository.initialize()

            with sqlite3.connect(db_path) as connection:
                columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(jobs)").fetchall()
                }

        self.assertTrue(
            {
                "dedupe_key",
                "source",
                "salary_text",
                "location_text",
                "workplace_type",
                "post_age_text",
                "post_age_days",
                "seen",
                "applied",
            }.issubset(columns)
        )

    def test_upsert_prevents_duplicates_for_same_source_job(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = SQLiteJobRepository(Path(temp_dir) / "jobs.db")
            repository.initialize()

            first = JobRecord(
                source=JobSource.LINKEDIN,
                external_job_id="123",
                company="Example",
                title="Data Architect",
                description="First version",
                link="https://www.linkedin.com/jobs/view/123",
                collected_at=utc_now(),
                salary_text="$7,000 - $10,000 monthly",
            )
            second = JobRecord(
                source=JobSource.LINKEDIN,
                external_job_id="123",
                company="Example",
                title="Staff Data Architect",
                description="Updated version",
                link="https://www.linkedin.com/jobs/view/123?tracking=1",
                collected_at=utc_now(),
                salary_text="$8,000 - $10,000 monthly",
            )

            repository.upsert_job(first)
            repository.upsert_job(second)
            count = repository.count_jobs()
            jobs = repository.list_jobs()

        self.assertEqual(1, count)
        self.assertEqual("Staff Data Architect", jobs[0].title)
        self.assertEqual("Updated version", jobs[0].description)
        self.assertEqual("https://www.linkedin.com/jobs/view/123?tracking=1", jobs[0].link)
        self.assertEqual("$8,000 - $10,000 monthly", jobs[0].salary_text)

    def test_upsert_infers_post_datetime_from_post_age_days(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = SQLiteJobRepository(Path(temp_dir) / "jobs.db")
            repository.initialize()
            collected_at = utc_now()
            repository.upsert_job(
                JobRecord(
                    source=JobSource.LINKEDIN,
                    external_job_id="age-1",
                    company="Example",
                    title="Data Architect",
                    description="Role",
                    link="https://www.linkedin.com/jobs/view/age-1",
                    collected_at=collected_at,
                    post_age_days=14,
                )
            )

            stored = repository.list_jobs(limit=1)[0]

        self.assertIsNotNone(stored.post_datetime)
        assert stored.post_datetime is not None
        self.assertEqual(collected_at.date().toordinal() - 14, stored.post_datetime.date().toordinal())

    def test_persists_harvest_state_and_known_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = SQLiteJobRepository(Path(temp_dir) / "jobs.db")
            repository.initialize()
            repository.upsert_job(
                JobRecord(
                    source=JobSource.LINKEDIN,
                    external_job_id="123",
                    company="Example",
                    title="Known",
                    description="Role",
                    link="https://www.linkedin.com/jobs/view/123",
                    collected_at=utc_now(),
                )
            )

            self.assertEqual(
                {"123"},
                repository.existing_external_job_ids(JobSource.LINKEDIN, ["123", "999"]),
            )

            run_state = repository.get_harvest_run_state("linkedin")
            run_state.throttle_events = 2
            run_state.sticky_caution_enabled = True
            run_state.current_backoff_seconds = 120.0
            repository.save_harvest_run_state(run_state)

            query_state = repository.get_harvest_query_state("linkedin", "data architect remote")
            query_state.next_start = 50
            query_state.consecutive_empty_pages = 2
            query_state.yielded_new_ids = 8
            query_state.saw_stale_results = True
            repository.save_harvest_query_state(query_state)

            saved_run = repository.get_harvest_run_state("linkedin")
            saved_query = repository.get_harvest_query_state("linkedin", "data architect remote")

        self.assertEqual(2, saved_run.throttle_events)
        self.assertTrue(saved_run.sticky_caution_enabled)
        self.assertEqual(120.0, saved_run.current_backoff_seconds)
        self.assertEqual(50, saved_query.next_start)
        self.assertEqual(2, saved_query.consecutive_empty_pages)
        self.assertEqual(8, saved_query.yielded_new_ids)
        self.assertTrue(saved_query.saw_stale_results)


class EvaluationTests(unittest.TestCase):
    def test_scores_job_against_professional_compass(self) -> None:
        compass = load_professional_compass("profiles/professional_compass.template.json")
        evaluator = JobCompassEvaluator(compass)
        job = JobRecord(
            source=JobSource.LINKEDIN,
            external_job_id="123",
            company="CRAFTLabs",
            title="Senior Data Scientist",
            description=(
                "Remote product team building AI data products with Python, SQL, "
                "Snowflake and LLM systems. Hands-on individual contributor role."
            ),
            link="https://www.linkedin.com/jobs/view/123",
            salary_text="$7,000 - $10,000 monthly",
            collected_at=utc_now(),
        )

        evaluation = evaluator.evaluate(job)

        self.assertEqual("product", evaluation.company_type)
        self.assertEqual("senior", evaluation.responsibility_level)
        self.assertEqual("7000 to 10000 monthly usd", evaluation.salary)
        self.assertGreaterEqual(evaluation.score, 7)
        self.assertIn("Python", evaluation.techs)


class LinkedInExtractionTests(unittest.TestCase):
    def test_validates_extraction_spec(self) -> None:
        spec = LinkedInExtractionSpec(
            version=1, search_job_id_regex=r"(?:/jobs/view/(?:[^\"\?]*-)?)(\d+)"
        )
        validate_extraction_spec(spec)

    def test_extracts_job_ids_from_search_html(self) -> None:
        html = Path("tests/fixtures/linkedin_search.html").read_text(encoding="utf-8")
        spec = LinkedInExtractionSpec(
            version=1, search_job_id_regex=r"(?:/jobs/view/(?:[^\"\?]*-)?)(\d+)"
        )
        job_ids = extract_job_ids_from_search_html(html, spec)
        self.assertEqual(["123", "124", "125"], job_ids)

    def test_extracts_job_from_detail_html_using_jsonld(self) -> None:
        html = Path("tests/fixtures/linkedin_job_detail.html").read_text(encoding="utf-8")
        job = extract_job_from_detail_html(html, collected_at=utc_now())
        self.assertIsNotNone(job)
        assert job is not None
        normalized = job.normalized()
        self.assertEqual(JobSource.LINKEDIN, normalized.source)
        self.assertEqual("999", normalized.external_job_id)
        self.assertEqual("Example Corp", normalized.company)
        self.assertEqual("Staff Data Architect", normalized.title)
        self.assertIn("Build data systems", normalized.description)
        self.assertEqual("https://www.linkedin.com/jobs/view/999", normalized.link)
        self.assertEqual("Buenos Aires, Argentina", normalized.location_text)
        self.assertEqual("2 weeks ago", normalized.post_age_text)
        self.assertEqual(14, normalized.post_age_days)

    def test_sqlite_stores_extracted_full_description_and_dedupes(self) -> None:
        html = Path("tests/fixtures/linkedin_job_detail.html").read_text(encoding="utf-8")
        job = extract_job_from_detail_html(html, collected_at=utc_now())
        assert job is not None
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = SQLiteJobRepository(Path(temp_dir) / "jobs.db")
            repo.initialize()
            repo.upsert_job(job.normalized())
            repo.upsert_job(job.normalized())
            self.assertEqual(1, repo.count_jobs())
            stored = repo.list_jobs(limit=1)[0]
            self.assertIn("Build data systems", stored.description)
            self.assertEqual("999", stored.external_job_id)
            self.assertEqual("Buenos Aires, Argentina", stored.location_text)
            self.assertEqual(14, stored.post_age_days)

    def test_applies_best_effort_max_age_filter(self) -> None:
        job = JobRecord(
            source=JobSource.LINKEDIN,
            company="A",
            title="T",
            description="D",
            link="https://www.linkedin.com/jobs/view/1/",
            collected_at=utc_now(),
            post_age_days=31,
        ).normalized()
        self.assertFalse(
            _passes_filters(
                job,
                max_post_age_days=14,
                allowed_workplace_types=None,
                allowed_regions=None,
            )
        )


class HarvestScheduleTests(unittest.TestCase):
    def test_loads_harvest_schedule_from_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            schedule_path = Path(temp_dir) / "schedule.yaml"
            schedule_path.write_text(
                """
window:
  start: \"00:00\"
  end: \"08:00\"
search:
  max_queries: 4
  max_pages_per_query: 10
  empty_search_pages_threshold: 2
  missing_signal_policy: drop
pacing:
  base_delay_seconds: 1.5
  jitter_seconds: 0.5
  sticky_caution_multiplier: 3
backoff:
  initial_delay_seconds: 30
  multiplier: 4
  max_delay_seconds: 3600
progress:
  summary_every_requests: 9
logging:
  file_path: data/test.log
                """.strip(),
                encoding="utf-8",
            )

            schedule = load_harvest_schedule(schedule_path)

        self.assertEqual(time(hour=0, minute=0), schedule.window_start)
        self.assertEqual(time(hour=8, minute=0), schedule.window_end)
        self.assertEqual(4, schedule.max_queries)
        self.assertEqual(10, schedule.max_pages_per_query)
        self.assertEqual(2, schedule.empty_search_pages_threshold)
        self.assertEqual("drop", schedule.missing_signal_policy)
        self.assertEqual(9, schedule.summary_every_requests)

    def test_builds_harvest_search_url_with_location_and_recency(self) -> None:
        compass = ProfessionalCompass(
            summary_instruction="",
            required_output_fields=[],
            context_about_me=[],
            positioning="",
            current_situation=[],
            target_roles=["Data Architect"],
            hard_filters=[],
            min_monthly_usd=0,
            target_monthly_usd_range=[0, 0],
            remote_only=True,
            preferred_timezone_overlap="",
            search_max_post_age_days=7,
            search_workplace_types=["remote"],
            search_regions=["LATAM"],
        )

        plans = _derive_search_plans(compass, limit=5)
        self.assertEqual(1, len(plans))
        self.assertEqual("Data Architect remote", plans[0].query)
        self.assertEqual("Latin America", plans[0].location)

        url = _build_harvest_search_url(plans[0], 25, compass)

        self.assertIn("keywords=Data+Architect+remote", url)
        self.assertIn("location=Latin+America", url)
        self.assertIn("f_TPR=r604800", url)

    def test_builds_harvest_search_url_for_canada_region(self) -> None:
        compass = ProfessionalCompass(
            summary_instruction="",
            required_output_fields=[],
            context_about_me=[],
            positioning="",
            current_situation=[],
            target_roles=["Data Architect"],
            hard_filters=[],
            min_monthly_usd=0,
            target_monthly_usd_range=[0, 0],
            remote_only=True,
            preferred_timezone_overlap="",
            search_max_post_age_days=7,
            search_workplace_types=["remote"],
            search_regions=["CANADA"],
        )

        plans = _derive_search_plans(compass, limit=5)

        self.assertEqual("Canada", plans[0].location)
        url = _build_harvest_search_url(plans[0], 0, compass)
        self.assertIn("location=Canada", url)

    def test_filter_decision_reports_exact_failure_reason(self) -> None:
        decision = _evaluate_harvest_filters(
            JobRecord(
                source=JobSource.LINKEDIN,
                company="Example",
                title="T",
                description="D",
                link="https://www.linkedin.com/jobs/view/1",
                collected_at=utc_now(),
                location_text="Atlanta, GA",
                workplace_type="remote",
                post_age_days=21,
            ),
            max_post_age_days=14,
            allowed_workplace_types=["remote"],
            allowed_regions=["latam"],
            missing_signal_policy="keep",
        )

        self.assertFalse(decision.allowed)
        self.assertEqual("age_exceeds_limit", decision.reason)

    def test_derive_region_recognizes_canada(self) -> None:
        self.assertEqual("ca", _derive_region("Toronto, Canada"))


class NightlyHarvestTests(unittest.TestCase):
    def test_harvest_skips_known_ids_and_stores_new_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = SQLiteJobRepository(Path(temp_dir) / "jobs.db")
            repository.initialize()
            repository.upsert_job(
                JobRecord(
                    source=JobSource.LINKEDIN,
                    external_job_id="123",
                    company="Example",
                    title="Known",
                    description="Role",
                    link="https://www.linkedin.com/jobs/view/123",
                    collected_at=utc_now(),
                )
            )
            schedule = HarvestSchedule(
                window_start=time(hour=0, minute=0),
                window_end=time(hour=23, minute=59),
                max_queries=1,
                max_pages_per_query=1,
                empty_search_pages_threshold=3,
                base_delay_seconds=0.0,
                jitter_seconds=0.0,
                sticky_caution_multiplier=2.0,
                backoff_initial_seconds=0.0,
                backoff_multiplier=2.0,
                backoff_max_seconds=0.0,
                summary_every_requests=100,
                log_path=str(Path(temp_dir) / "harvest.log"),
            )
            search_html = (
                '<html><body><a href="/jobs/view/123/">Job 123</a>'
                '<a href="/jobs/view/124/">Job 124</a>'
                '<span>2 days ago</span></body></html>'
            )
            detail_html = """
<html>
  <head><link rel="canonical" href="https://www.linkedin.com/jobs/view/124/" /></head>
  <body>
    <h1 class="topcard__title">Staff Data Architect</h1>
    <a class="topcard__org-name-link">Example Corp</a>
    <span class="topcard__flavor topcard__flavor--bullet">Remote in United States</span>
    <span class="posted-time-ago__text">2 days ago</span>
    <div>Workplace type</h3><span>remote</span></div>
    <div class="show-more-less-html__markup">Build data systems with Python and SQL.</div>
  </body>
</html>
            """.strip()
            responses = [
                FetchResponse(url="search", kind="search", text=search_html, status_code=200),
                FetchResponse(url="detail", kind="job", text=detail_html, status_code=200),
            ]

            def fetcher(url: str, kind: str) -> FetchResponse:
                self.assertTrue(responses)
                response = responses.pop(0)
                return FetchResponse(
                    url=url,
                    kind=kind,
                    text=response.text,
                    status_code=response.status_code,
                    error=response.error,
                )

            harvester = LinkedInNightlyHarvester(
                compass=load_professional_compass("profiles/professional_compass.template.json"),
                repository=repository,
                extraction_spec_path="config/linkedin_extraction.template.json",
                schedule=schedule,
                fetcher=fetcher,
                sleep=lambda _: None,
                max_jobs=1,
            )

            result = harvester.run()
            stored_ids = repository.existing_external_job_ids(JobSource.LINKEDIN, ["123", "124"])

        self.assertEqual(1, result.skipped_known_ids)
        self.assertEqual(1, result.stored)
        self.assertEqual({"123", "124"}, stored_ids)

    def test_harvest_records_403_throttle_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = SQLiteJobRepository(Path(temp_dir) / "jobs.db")
            repository.initialize()
            schedule = HarvestSchedule(
                window_start=time(hour=0, minute=0),
                window_end=time(hour=23, minute=59),
                max_queries=1,
                max_pages_per_query=1,
                empty_search_pages_threshold=1,
                base_delay_seconds=0.0,
                jitter_seconds=0.0,
                sticky_caution_multiplier=2.0,
                backoff_initial_seconds=0.0,
                backoff_multiplier=2.0,
                backoff_max_seconds=0.0,
                summary_every_requests=100,
                log_path=str(Path(temp_dir) / "harvest.log"),
            )
            responses = [
                FetchResponse(url="search", kind="search", text=None, status_code=403, error="http_403"),
                FetchResponse(url="search", kind="search", text="<html><body></body></html>", status_code=200),
            ]

            def fetcher(url: str, kind: str) -> FetchResponse:
                response = responses.pop(0)
                return FetchResponse(
                    url=url,
                    kind=kind,
                    text=response.text,
                    status_code=response.status_code,
                    error=response.error,
                )

            harvester = LinkedInNightlyHarvester(
                compass=load_professional_compass("profiles/professional_compass.template.json"),
                repository=repository,
                extraction_spec_path="config/linkedin_extraction.template.json",
                schedule=schedule,
                fetcher=fetcher,
                sleep=lambda _: None,
            )

            result = harvester.run()
            run_state = repository.get_harvest_run_state("linkedin")

        self.assertEqual(1, result.throttles)
        self.assertEqual(1, run_state.throttle_events)
        self.assertTrue(run_state.sticky_caution_enabled)

    def test_harvest_stops_after_five_no_new_id_pages_without_stale_signal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = SQLiteJobRepository(Path(temp_dir) / "jobs.db")
            repository.initialize()
            repository.upsert_job(
                JobRecord(
                    source=JobSource.LINKEDIN,
                    external_job_id="123",
                    company="Example",
                    title="Known",
                    description="Role",
                    link="https://www.linkedin.com/jobs/view/123",
                    collected_at=utc_now(),
                )
            )
            schedule = HarvestSchedule(
                window_start=time(hour=0, minute=0),
                window_end=time(hour=23, minute=59),
                max_queries=1,
                max_pages_per_query=20,
                empty_search_pages_threshold=5,
                base_delay_seconds=0.0,
                jitter_seconds=0.0,
                sticky_caution_multiplier=2.0,
                backoff_initial_seconds=0.0,
                backoff_multiplier=2.0,
                backoff_max_seconds=0.0,
                summary_every_requests=100,
                log_path=str(Path(temp_dir) / "harvest.log"),
            )
            search_html = '<html><body><a href="/jobs/view/123/">Job 123</a></body></html>'
            requests_seen: list[str] = []

            def fetcher(url: str, kind: str) -> FetchResponse:
                requests_seen.append(url)
                return FetchResponse(url=url, kind=kind, text=search_html, status_code=200)

            harvester = LinkedInNightlyHarvester(
                compass=load_professional_compass("profiles/professional_compass.template.json"),
                repository=repository,
                extraction_spec_path="config/linkedin_extraction.template.json",
                schedule=schedule,
                fetcher=fetcher,
                sleep=lambda _: None,
            )

            result = harvester.run()
            query_state = repository.get_harvest_query_state(
                "linkedin", 'AI Architect (hands-on) remote::United States'
            )

        self.assertEqual(5, result.search_pages)
        self.assertEqual(5, len(requests_seen))
        self.assertEqual(1, result.stale_stream_stops)
        self.assertEqual(5, query_state.consecutive_empty_pages)


if __name__ == "__main__":
    unittest.main()
