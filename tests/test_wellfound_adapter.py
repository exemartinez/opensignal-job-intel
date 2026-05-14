from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.core_domain_inputs import JobSource, normalize_source_link
from src.wellfound_acquisition import (
    extract_job_from_detail_html,
    extract_job_links_from_search_html,
)


class WellfoundAdapterTests(unittest.TestCase):
    def test_extracts_job_links_from_search_html(self) -> None:
        html = """
        <html><body>
          <a href="/jobs/4209714-client-success-specialist">Client Success Specialist</a>
          <a href="/jobs/9999999-senior-data-engineer?utm=tracking">Senior Data Engineer</a>
        </body></html>
        """
        links = extract_job_links_from_search_html(html)
        self.assertEqual(
            [
                "https://wellfound.com/jobs/4209714-client-success-specialist",
                "https://wellfound.com/jobs/9999999-senior-data-engineer",
            ],
            links,
        )

    def test_extracts_detail_html_into_canonical_job(self) -> None:
        html = """
        <html>
          <head>
            <title>Client Success Specialist at 6crickets.com • Bellevue • Remote | Wellfound</title>
            <link rel="canonical" href="https://wellfound.com/jobs/4209714-client-success-specialist?ref=abc" />
          </head>
          <body>
            <h1>Client Success Specialist</h1>
            <h2>About the job</h2>
            <p>We are seeking a motivated client success specialist.</p>
            <div>Posted 3 days ago</div>
          </body>
        </html>
        """
        collected_at = datetime(2026, 5, 13, tzinfo=timezone.utc)
        job = extract_job_from_detail_html(
            html,
            collected_at=collected_at,
            fallback_link="https://wellfound.com/jobs/4209714-client-success-specialist",
        )
        assert job is not None
        self.assertEqual(JobSource.WELLFOUND, job.source)
        self.assertEqual("4209714", job.external_job_id)
        self.assertEqual("6crickets.com", job.company)
        self.assertEqual("Client Success Specialist", job.title)
        self.assertIn("motivated client success specialist", job.description.lower())
        self.assertEqual(
            "https://wellfound.com/jobs/4209714-client-success-specialist?ref=abc",
            job.link,
        )
        self.assertEqual(collected_at, job.collected_at)
        self.assertEqual(3, job.post_age_days)
        self.assertIsNotNone(job.post_datetime)

    def test_keeps_post_datetime_when_jsonld_provides_date_posted(self) -> None:
        html = """
        <html>
          <head>
            <title>Engineer at ExampleCo | Wellfound</title>
            <script type="application/ld+json">
              {"@context":"https://schema.org","@type":"JobPosting","datePosted":"2026-05-10T00:00:00Z"}
            </script>
          </head>
          <body>
            <h1>Engineer</h1>
            <h2>About the job</h2>
            <p>Build systems.</p>
          </body>
        </html>
        """
        collected_at = datetime(2026, 5, 13, tzinfo=timezone.utc)
        job = extract_job_from_detail_html(
            html,
            collected_at=collected_at,
            fallback_link="https://wellfound.com/jobs/1111-engineer",
        )
        assert job is not None
        self.assertIsNotNone(job.post_datetime)

    def test_normalize_source_link_strips_query_noise(self) -> None:
        link = "https://wellfound.com/jobs/4209714-client-success-specialist?ref=abc&utm=1#frag"
        self.assertEqual(
            "https://wellfound.com/jobs/4209714-client-success-specialist",
            normalize_source_link(link),
        )


class WellfoundBlockDetectionTests(unittest.TestCase):
    def test_detects_hard_block_page(self) -> None:
        from src.wellfound_acquisition import _looks_hard_blocked

        html = """
        <html><body>
        <h1>Access is temporarily restricted</h1>
        We detected unusual activity from your device or network.
        Need help? Submit feedback.
        </body></html>
        """
        self.assertTrue(_looks_hard_blocked(html))

    def test_detects_datadome_block_page(self) -> None:
        from src.wellfound_acquisition import _looks_hard_blocked

        html = """
        <html lang="en"><head><title>wellfound.com</title></head>
        <body><script data-cfasync="false">var dd={'rt':'c','t':'bv'};</script></body></html>
        """
        self.assertTrue(_looks_hard_blocked(html))
