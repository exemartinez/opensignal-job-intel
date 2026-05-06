from __future__ import annotations

import tempfile
import unittest
from datetime import time
from pathlib import Path

from opensignal_job_intel.models import JobRecord, JobSource, ProfessionalCompass, utc_now
from opensignal_job_intel.repositories.sqlite_jobs import SQLiteJobRepository
from opensignal_job_intel.sources.linkedin_acquire import _derive_region
from opensignal_job_intel.sources.linkedin_harvest import (
    _build_harvest_search_url,
    _derive_search_plans,
    _evaluate_harvest_filters,
    FetchResponse,
    LinkedInNightlyHarvester,
    load_harvest_schedule,
)
from tests.helpers import load_default_compass, make_harvest_schedule


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
            schedule = make_harvest_schedule(log_path=Path(temp_dir) / "harvest.log")
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
                compass=load_default_compass(),
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
            schedule = make_harvest_schedule(
                log_path=Path(temp_dir) / "harvest.log",
                empty_search_pages_threshold=1,
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
                compass=load_default_compass(),
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
            schedule = make_harvest_schedule(
                log_path=Path(temp_dir) / "harvest.log",
                max_pages_per_query=20,
                empty_search_pages_threshold=5,
            )
            search_html = '<html><body><a href="/jobs/view/123/">Job 123</a></body></html>'
            requests_seen: list[str] = []

            def fetcher(url: str, kind: str) -> FetchResponse:
                requests_seen.append(url)
                return FetchResponse(url=url, kind=kind, text=search_html, status_code=200)

            harvester = LinkedInNightlyHarvester(
                compass=load_default_compass(),
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
