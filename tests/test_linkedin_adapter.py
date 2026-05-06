from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from opensignal_job_intel.models import JobSource
from opensignal_job_intel.sources.linkedin import LinkedInJsonFileAdapter


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


if __name__ == "__main__":
    unittest.main()
