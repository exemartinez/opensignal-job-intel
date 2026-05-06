from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from opensignal_job_intel.models import JobRecord, JobSource, utc_now
from opensignal_job_intel.repositories.sqlite_jobs import SQLiteJobRepository


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


if __name__ == "__main__":
    unittest.main()
