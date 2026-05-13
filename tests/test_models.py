from __future__ import annotations

import unittest

from src.core_domain_inputs import JobRecord, JobSource, normalize_source_link, utc_now


class ModelTests(unittest.TestCase):
    def test_normalize_source_link_strips_query_and_trailing_slash(self) -> None:
        self.assertEqual(
            "https://www.linkedin.com/jobs/view/123",
            normalize_source_link(" https://www.linkedin.com/jobs/view/123/?tracking=abc "),
        )

    def test_normalize_source_link_keeps_indeed_jk_parameter(self) -> None:
        self.assertEqual(
            "https://www.indeed.com/viewjob?jk=abc123",
            normalize_source_link("https://www.indeed.com/viewjob?jk=abc123&from=shareddesktop"),
        )

    def test_job_record_normalized_trims_optional_text_fields(self) -> None:
        job = JobRecord(
            source=JobSource.LINKEDIN,
            company=" Example Corp ",
            title=" Staff Data Architect ",
            description=" Build systems ",
            link="https://www.linkedin.com/jobs/view/123/?tracking=abc",
            salary_text=" $8,000 monthly ",
            location_text=" Remote in Argentina ",
            workplace_type=" remote ",
            post_age_text=" 2 weeks ago ",
            collected_at=utc_now(),
        ).normalized()

        self.assertEqual("Example Corp", job.company)
        self.assertEqual("Staff Data Architect", job.title)
        self.assertEqual("Build systems", job.description)
        self.assertEqual("https://www.linkedin.com/jobs/view/123", job.link)
        self.assertEqual("$8,000 monthly", job.salary_text)
        self.assertEqual("Remote in Argentina", job.location_text)
        self.assertEqual("remote", job.workplace_type)
        self.assertEqual("2 weeks ago", job.post_age_text)

    def test_dedupe_key_falls_back_to_normalized_link_when_external_id_is_missing(self) -> None:
        job = JobRecord(
            source=JobSource.LINKEDIN,
            company="Example",
            title="Title",
            description="Desc",
            link="https://www.linkedin.com/jobs/view/123/?tracking=abc",
            collected_at=utc_now(),
        )

        self.assertEqual(
            "linkedin:https://www.linkedin.com/jobs/view/123",
            job.dedupe_key,
        )


if __name__ == "__main__":
    unittest.main()
