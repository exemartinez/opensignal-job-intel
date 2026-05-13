from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.core_domain_inputs import JobRecord, JobSource, utc_now
from src.indeed_acquisition import (
    IndeedJsonFileAdapter,
    IndeedScrapeAdapter,
    _build_search_url,
    _canonicalize_indeed_job_link,
    _derive_queries,
    _extract_job_from_detail_html,
    _extract_job_ids_from_search_html,
    _extract_jobs_from_search_html,
    _job_to_fixture_item,
    _parse_cookie_header,
    _passes_filters,
)
from tests.helpers import load_default_compass


class IndeedAdapterTests(unittest.TestCase):
    def test_normalizes_local_json_payload_into_canonical_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "indeed.json"
            input_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "abc123",
                            "company": "Example Corp ",
                            "title": " Staff Data Architect ",
                            "description": " Build data systems ",
                            "posted_at": "2026-04-15T12:00:00Z",
                            "salary": "$7,000 - $10,000 monthly",
                            "link": "https://www.indeed.com/viewjob?jk=abc123",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            jobs = IndeedJsonFileAdapter(input_path).fetch_jobs()

        self.assertEqual(1, len(jobs))
        job = jobs[0].normalized()
        self.assertEqual(JobSource.INDEED, job.source)
        self.assertEqual("abc123", job.external_job_id)
        self.assertEqual("Example Corp", job.company)
        self.assertEqual("Staff Data Architect", job.title)
        self.assertEqual("Build data systems", job.description)
        self.assertEqual("$7,000 - $10,000 monthly", job.salary_text)
        self.assertEqual("https://www.indeed.com/viewjob?jk=abc123", job.link)
        self.assertIsNotNone(job.post_datetime)

    def test_live_fetch_diagnostics_include_url_and_reason_type_for_browser_errors(self) -> None:
        adapter = IndeedScrapeAdapter(
            compass=load_default_compass(),
            max_queries=1,
            max_pages_per_query=1,
            max_jobs=1,
            request_delay_seconds=0.0,
        )

        class FakeSession:
            def fetch_text(self, url: str, kind: str) -> str:
                raise RuntimeError("challenge blocked")

        result = adapter._fetch_text(
            "https://www.indeed.com/jobs?q=test",
            kind="search",
            session=FakeSession(),
        )

        self.assertIsNone(result)
        self.assertEqual(1, adapter.diagnostics.dropped)
        self.assertEqual(1, len(adapter.diagnostics.drops))
        drop = adapter.diagnostics.drops[0]
        self.assertIn("browser_error:search:https://www.indeed.com/jobs?q=test", drop)
        self.assertIn("RuntimeError", drop)

    def test_fixture_export_uses_canonical_job_record_shape(self) -> None:
        job = JobRecord(
            source=JobSource.INDEED,
            external_job_id="abc123",
            company=" Example Corp ",
            title=" Staff Data Architect ",
            description=" Build data systems ",
            link="https://www.indeed.com/viewjob?jk=abc123",
            salary_text="$7,000 - $10,000 monthly",
            location_text=" Remote in United States ",
            workplace_type=" remote ",
            post_age_text=" 2 days ago ",
            post_age_days=2,
            collected_at=datetime(2026, 5, 7, 12, 0, tzinfo=timezone.utc),
            post_datetime=datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc),
        )

        item = _job_to_fixture_item(job)

        self.assertEqual("indeed", item["source"])
        self.assertEqual("indeed:abc123", item["dedupe_key"])
        self.assertEqual("abc123", item["external_job_id"])
        self.assertEqual("Example Corp", item["company"])
        self.assertEqual("Staff Data Architect", item["title"])

    def test_live_query_builder_deduplicates_roles_and_appends_remote(self) -> None:
        compass = load_default_compass()

        queries = _derive_queries(compass, limit=10)

        self.assertEqual(len(queries), len(set(queries)))
        self.assertTrue(all("remote" in query.lower() for query in queries))

    def test_live_search_url_builder_encodes_keywords_and_start(self) -> None:
        url = _build_search_url(query="AI Architect remote", start=20)

        self.assertIn("q=AI+Architect+remote", url)
        self.assertIn("start=20", url)

    def test_live_filters_reject_jobs_outside_age_workplace_and_region_rules(self) -> None:
        job = JobRecord(
            source=JobSource.INDEED,
            company="Example",
            title="Title",
            description="Desc",
            link="https://www.indeed.com/viewjob?jk=abc123",
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

    def test_extracts_job_ids_and_detail_html_into_canonical_job(self) -> None:
        search_html = """
        <html>
          <body>
            <a data-jk="abc123" href="/viewjob?jk=abc123">Role</a>
            <a href="/rc/clk?jk=def456&from=vj">Role 2</a>
          </body>
        </html>
        """
        detail_html = """
        <html>
          <head>
            <script type="application/ld+json">
            {
              "@context": "https://schema.org",
              "@type": "JobPosting",
              "title": "AI Architect",
              "description": "<p>Design data and AI systems with Python and SQL.</p>",
              "datePosted": "2026-05-01T12:00:00Z",
              "url": "https://www.indeed.com/viewjob?jk=abc123",
              "hiringOrganization": {"name": "Example Corp"},
              "jobLocation": {
                "@type": "Place",
                "address": {
                  "@type": "PostalAddress",
                  "addressLocality": "Austin",
                  "addressRegion": "TX",
                  "addressCountry": "US"
                }
              }
            }
            </script>
          </head>
          <body>
            <div class="jobsearch-JobMetadataFooter">2 days ago</div>
            <div>Remote</div>
          </body>
        </html>
        """

        ids = _extract_job_ids_from_search_html(search_html)
        job = _extract_job_from_detail_html(
            detail_html,
            collected_at=datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc),
            fallback_link="https://www.indeed.com/viewjob?jk=abc123",
        )

        self.assertEqual(["abc123", "def456"], ids)
        self.assertIsNotNone(job)
        assert job is not None
        self.assertEqual(JobSource.INDEED, job.source)
        self.assertEqual("abc123", job.external_job_id)
        self.assertEqual("Example Corp", job.company)
        self.assertEqual("AI Architect", job.title)
        self.assertEqual("Design data and AI systems with Python and SQL.", job.description)
        self.assertEqual("Austin, TX, US", job.location_text)
        self.assertEqual("remote", job.workplace_type)
        self.assertEqual(2, job.post_age_days)

    def test_parse_cookie_header_builds_selenium_cookie_dicts(self) -> None:
        cookies = _parse_cookie_header("cf_clearance=abc123; session-id=xyz789")

        self.assertEqual(2, len(cookies))
        self.assertEqual("cf_clearance", cookies[0]["name"])
        self.assertEqual("abc123", cookies[0]["value"])
        self.assertEqual(".indeed.com", cookies[0]["domain"])

    def test_extracts_jobs_from_search_result_cards(self) -> None:
        search_html = """
        <html>
          <head>
            <script>
              window._initialData={"hostQueryExecutionResult":{"data":{"jobData":{"results":[{"job":{"key":"b9caa3fe330a68d9","datePublished":1778587200000}}]}}}};
            </script>
          </head>
          <body>
            <li>
              <div class="cardOutline tapItem dd-privacy-allow result">
                <div class="slider_container" data-testid="slider_container">
                  <div class="slider_list">
                    <div data-testid="slider_item" class="slider_item">
                      <div>
                        <h2 class="jobTitle">
                          <a data-jk="b9caa3fe330a68d9" href="/viewjob?jk=b9caa3fe330a68d9">
                            <span title="AI Architect">AI Architect</span>
                          </a>
                        </h2>
                        <span data-testid="company-name">Example Corp</span>
                        <div data-testid="text-location">Remote in Austin, TX</div>
                      </div>
                    </div>
                    <div data-testid="slider_sub_item" class="slider_sub_item">
                      <div data-testid="belowJobSnippet">
                        <ul><li>Design AI systems with Python and SQL.</li></ul>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </li>
          </body>
        </html>
        """

        jobs = _extract_jobs_from_search_html(
            search_html,
            collected_at=datetime(2026, 5, 12, 12, 0, tzinfo=timezone.utc),
            limit=5,
        )

        self.assertEqual(1, len(jobs))
        job, mode = jobs[0]
        self.assertEqual("search_card", mode)
        self.assertEqual("b9caa3fe330a68d9", job.external_job_id)
        self.assertEqual("Example Corp", job.company)
        self.assertEqual("AI Architect", job.title)
        self.assertIn("Python and SQL", job.description)
        self.assertEqual("remote", job.workplace_type)
        self.assertEqual("https://www.indeed.com/viewjob?jk=b9caa3fe330a68d9", job.link)
        self.assertIsNotNone(job.post_datetime)
        assert job.post_datetime is not None
        self.assertEqual(datetime(2026, 5, 12, 12, 0, tzinfo=timezone.utc), job.post_datetime)

    def test_rejects_search_cards_without_verified_href_backed_job_ids(self) -> None:
        search_html = """
        <html>
          <body>
            <li>
              <div data-testid="slider_item" class="slider_item">
                <div>
                  <h2 class="jobTitle">
                    <a data-jk="a1b2c3d4e5f67890"><span title="AI Architect">AI Architect</span></a>
                  </h2>
                  <span data-testid="company-name">Example Corp</span>
                  <div data-testid="text-location">Remote in Austin, TX</div>
                </div>
                <div data-testid="slider_sub_item" class="slider_sub_item">
                  <div data-testid="belowJobSnippet">Design AI systems with Python and SQL.</div>
                </div>
              </div>
            </li>
            <li>
              <div data-testid="slider_item" class="slider_item">
                <div>
                  <h2 class="jobTitle">
                    <a id="job_a1b2c3d4e5f67890" data-jk="a1b2c3d4e5f67890" href="/viewjob?jk=a1b2c3d4e5f67890">
                      <span title="AI Architect" id="jobTitle-b9caa3fe330a68d9">AI Architect</span>
                    </a>
                  </h2>
                  <span data-testid="company-name">Example Corp</span>
                  <div data-testid="text-location">Remote in Austin, TX</div>
                </div>
                <div data-testid="slider_sub_item" class="slider_sub_item">
                  <div data-testid="belowJobSnippet">Design AI systems with Python and SQL.</div>
                </div>
              </div>
            </li>
          </body>
        </html>
        """

        jobs = _extract_jobs_from_search_html(
            search_html,
            collected_at=datetime(2026, 5, 12, 12, 0, tzinfo=timezone.utc),
            limit=5,
        )

        self.assertEqual([], jobs)

    def test_canonicalizes_only_real_indeed_job_links(self) -> None:
        self.assertEqual(
            "https://www.indeed.com/viewjob?jk=b9caa3fe330a68d9",
            _canonicalize_indeed_job_link("/rc/clk?jk=b9caa3fe330a68d9&from=vj"),
        )
        self.assertIsNone(_canonicalize_indeed_job_link("/viewjob"))
        self.assertIsNone(_canonicalize_indeed_job_link("/viewjob?jk=a1b2c3d4e5f6789x"))


if __name__ == "__main__":
    unittest.main()
