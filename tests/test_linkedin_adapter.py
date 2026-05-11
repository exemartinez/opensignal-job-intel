from __future__ import annotations

import json
import tempfile
import unittest
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src.core_domain_inputs import JobRecord, JobSource, utc_now
from src.linkedin_acquisition import (
    LinkedInJsonFileAdapter,
    LinkedInScrapeAdapter,
    _build_search_url,
    _derive_queries,
    _job_to_fixture_item,
    _passes_filters,
)
from tests.helpers import load_default_compass


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

    def test_live_fetch_diagnostics_include_url_and_reason_type_for_url_errors(self) -> None:
        adapter = LinkedInScrapeAdapter(
            compass=load_default_compass(),
            extraction_spec_path="config/linkedin_extraction.template.json",
            max_queries=1,
            max_pages_per_query=1,
            max_jobs=1,
            request_delay_seconds=0.0,
        )

        with patch(
            "src.linkedin_acquisition.urllib.request.urlopen",
            side_effect=urllib.error.URLError(OSError(8, "nodename nor servname provided, or not known")),
        ):
            result = adapter._fetch_text("https://www.linkedin.com/jobs/search/?keywords=test", kind="search")

        self.assertIsNone(result)
        self.assertEqual(1, adapter.diagnostics.dropped)
        self.assertEqual(1, len(adapter.diagnostics.drops))
        drop = adapter.diagnostics.drops[0]
        self.assertIn("url_error:search:https://www.linkedin.com/jobs/search/?keywords=test", drop)
        self.assertIn("OSError", drop)

    def test_fixture_export_uses_canonical_job_record_shape(self) -> None:
        job = JobRecord(
            source=JobSource.LINKEDIN,
            external_job_id="123",
            company=" Example Corp ",
            title=" Staff Data Architect ",
            description=" Build data systems ",
            link="https://www.linkedin.com/jobs/view/123/?refId=abc",
            salary_text="$7,000 - $10,000 monthly",
            location_text=" Remote in United States ",
            workplace_type=" remote ",
            post_age_text=" 2 days ago ",
            post_age_days=2,
            collected_at=datetime(2026, 5, 7, 12, 0, tzinfo=timezone.utc),
            post_datetime=datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc),
        )

        item = _job_to_fixture_item(job)

        self.assertEqual(
            {
                "id",
                "dedupe_key",
                "source",
                "external_job_id",
                "company",
                "title",
                "description",
                "post_datetime",
                "link",
                "salary_text",
                "location_text",
                "workplace_type",
                "post_age_text",
                "post_age_days",
                "collected_at",
                "stored_at",
                "seen",
                "applied",
            },
            set(item),
        )
        self.assertIsNone(item["id"])
        self.assertEqual("linkedin:123", item["dedupe_key"])
        self.assertEqual("linkedin", item["source"])
        self.assertEqual("123", item["external_job_id"])
        self.assertEqual("Example Corp", item["company"])
        self.assertEqual("Staff Data Architect", item["title"])
        self.assertEqual("Build data systems", item["description"])
        self.assertEqual("https://www.linkedin.com/jobs/view/123", item["link"])
        self.assertEqual("$7,000 - $10,000 monthly", item["salary_text"])
        self.assertEqual("Remote in United States", item["location_text"])
        self.assertEqual("remote", item["workplace_type"])
        self.assertEqual("2 days ago", item["post_age_text"])
        self.assertEqual(2, item["post_age_days"])
        self.assertEqual("2026-05-07T12:00:00+00:00", item["collected_at"])
        self.assertEqual("2026-05-05T12:00:00+00:00", item["post_datetime"])
        self.assertIsNone(item["stored_at"])
        self.assertFalse(item["seen"])
        self.assertFalse(item["applied"])

    def test_live_query_builder_deduplicates_roles_and_appends_remote(self) -> None:
        compass = load_default_compass()

        queries = _derive_queries(compass, limit=10)

        self.assertEqual(len(queries), len(set(queries)))
        self.assertTrue(all("remote" in query.lower() for query in queries))
        self.assertIn("AI Architect (hands-on) remote", queries)

    def test_live_search_url_builder_encodes_keywords_and_start(self) -> None:
        url = _build_search_url(query="AI Architect remote", start=50)

        self.assertIn("keywords=AI+Architect+remote", url)
        self.assertIn("start=50", url)

    def test_live_filters_reject_jobs_outside_age_workplace_and_region_rules(self) -> None:
        job = JobRecord(
            source=JobSource.LINKEDIN,
            company="Example",
            title="Title",
            description="Desc",
            link="https://www.linkedin.com/jobs/view/1",
            collected_at=utc_now(),
            post_age_days=40,
            workplace_type="onsite",
            location_text="Berlin, Germany",
        )

        allowed = _passes_filters(
            job,
            max_post_age_days=14,
            allowed_workplace_types=["remote"],
            allowed_regions=["latam"],
        )

        self.assertFalse(allowed)


if __name__ == "__main__":
    unittest.main()
