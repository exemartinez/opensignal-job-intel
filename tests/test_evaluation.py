from __future__ import annotations

import unittest

from opensignal_job_intel.evaluation import JobCompassEvaluator
from opensignal_job_intel.models import JobRecord, JobSource, utc_now
from tests.helpers import load_default_compass


class EvaluationTests(unittest.TestCase):
    def test_scores_job_against_professional_compass(self) -> None:
        evaluator = JobCompassEvaluator(load_default_compass())
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

    def test_normalizes_annual_salary_and_penalizes_managerial_roles(self) -> None:
        evaluator = JobCompassEvaluator(load_default_compass())
        job = JobRecord(
            source=JobSource.LINKEDIN,
            external_job_id="456",
            company="Advisory Co",
            title="Director of Data",
            description=(
                "Remote consulting organization doing client delivery and people management. "
                "Annual compensation is $180,000 - $240,000."
            ),
            link="https://www.linkedin.com/jobs/view/456",
            salary_text="$180,000 - $240,000 annual",
            collected_at=utc_now(),
        )

        evaluation = evaluator.evaluate(job)

        self.assertEqual("manager", evaluation.responsibility_level)
        self.assertEqual("consulting", evaluation.company_type)
        self.assertEqual("15000 to 20000 monthly usd", evaluation.salary)
        self.assertLessEqual(evaluation.score, 6)


if __name__ == "__main__":
    unittest.main()
