from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from opensignal_job_intel.models import JobRecord, JobSource, utc_now
from opensignal_job_intel.repositories.sqlite_jobs import SQLiteJobRepository
from opensignal_job_intel.sources.linkedin_acquire import _passes_filters
from opensignal_job_intel.sources.linkedin_extraction import (
    LinkedInExtractionSpec,
    extract_job_from_detail_html,
    extract_job_ids_from_search_html,
    validate_extraction_spec,
)


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


if __name__ == "__main__":
    unittest.main()
