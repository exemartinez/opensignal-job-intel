from __future__ import annotations

from abc import ABC, abstractmethod

from opensignal_job_intel.models import JobRecord


class JobSourceAdapter(ABC):
    @abstractmethod
    def fetch_jobs(self) -> list[JobRecord]:
        raise NotImplementedError

