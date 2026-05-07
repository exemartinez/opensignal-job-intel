from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from opensignal_job_intel.llm import LlmJsonResult, LocalLlmClient, _parse_json_from_text
from opensignal_job_intel.models import JobRecord, JobSource, utc_now
from opensignal_job_intel.services import JobIngestionService


class SupportModuleTests(unittest.TestCase):
    def test_job_ingestion_service_normalizes_jobs_before_storage_and_evaluation(self) -> None:
        adapter = Mock()
        repository = Mock()
        evaluator = Mock()
        evaluator.evaluate.side_effect = lambda job: {"title": job.title}
        adapter.fetch_jobs.return_value = [
            JobRecord(
                source=JobSource.LINKEDIN,
                company=" Example ",
                title=" Staff Data Architect ",
                description=" Build systems ",
                link="https://www.linkedin.com/jobs/view/123/?ref=abc",
                collected_at=utc_now(),
            )
        ]

        result = JobIngestionService(adapter=adapter, repository=repository, evaluator=evaluator).ingest()

        self.assertEqual(1, result.fetched)
        self.assertEqual(1, result.stored)
        stored_job = repository.upsert_job.call_args.args[0]
        self.assertEqual("Example", stored_job.company)
        self.assertEqual("Staff Data Architect", stored_job.title)
        self.assertEqual("https://www.linkedin.com/jobs/view/123", stored_job.link)
        self.assertEqual([{"title": "Staff Data Architect"}], result.evaluations)

    def test_parse_json_from_text_accepts_embedded_json(self) -> None:
        result = _parse_json_from_text("prefix {\"company\": \"Example\"} suffix")

        self.assertEqual(LlmJsonResult(ok=True, data={"company": "Example"}, error=None), result)

    def test_local_llm_client_falls_back_to_completion_endpoint(self) -> None:
        client = LocalLlmClient("http://localhost:1234", model="test-model")
        responses = [
            LlmJsonResult(ok=False, data=None, error="chat failed"),
            LlmJsonResult(ok=True, data={"content": "{\"company\": \"Example\"}"}, error=None),
        ]

        with patch.object(client, "_post_json", side_effect=responses) as post_json:
            result = client.extract_json(system_prompt="system", user_prompt="user")

        self.assertTrue(result.ok)
        self.assertEqual({"company": "Example"}, result.data)
        self.assertEqual(2, post_json.call_count)


if __name__ == "__main__":
    unittest.main()
