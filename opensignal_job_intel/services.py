from __future__ import annotations

from dataclasses import dataclass

from opensignal_job_intel.evaluation import JobCompassEvaluator
from opensignal_job_intel.models import JobEvaluation, JobRecord
from opensignal_job_intel.repositories.sqlite_jobs import SQLiteJobRepository
from opensignal_job_intel.sources.base import JobSourceAdapter


@dataclass(slots=True)
class IngestionResult:
    fetched: int
    stored: int
    evaluations: list[JobEvaluation]


class JobIngestionService:
    def __init__(
        self,
        adapter: JobSourceAdapter,
        repository: SQLiteJobRepository,
        evaluator: JobCompassEvaluator,
    ) -> None:
        self._adapter = adapter
        self._repository = repository
        self._evaluator = evaluator

    def ingest(self) -> IngestionResult:
        jobs = [job.normalized() for job in self._adapter.fetch_jobs()]
        stored = 0
        evaluations: list[JobEvaluation] = []
        for job in jobs:
            self._repository.upsert_job(job)
            evaluations.append(self._evaluator.evaluate(job))
            stored += 1
        return IngestionResult(fetched=len(jobs), stored=stored, evaluations=evaluations)

    def list_jobs(self, limit: int = 20) -> list[JobRecord]:
        return self._repository.list_jobs(limit=limit)
