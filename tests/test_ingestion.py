from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from opensignal_job_intel.compass import load_professional_compass
from opensignal_job_intel.evaluation import JobCompassEvaluator
from opensignal_job_intel.models import JobRecord, JobSource, utc_now
from opensignal_job_intel.repositories.sqlite_jobs import SQLiteJobRepository
from opensignal_job_intel.sources.linkedin import LinkedInJsonFileAdapter


class CompassTests(unittest.TestCase):
    def test_loads_professional_compass_from_json(self) -> None:
        compass = load_professional_compass("profiles/professional_compass.json")
        self.assertTrue(compass.remote_only)
        self.assertEqual(6000, compass.min_monthly_usd)
        self.assertIn("AI Architect (hands-on)", compass.target_roles)


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
            {"dedupe_key", "source", "salary_text", "seen", "applied"}.issubset(columns)
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


class EvaluationTests(unittest.TestCase):
    def test_scores_job_against_professional_compass(self) -> None:
        compass = load_professional_compass("profiles/professional_compass.json")
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


if __name__ == "__main__":
    unittest.main()
