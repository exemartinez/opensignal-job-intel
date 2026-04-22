from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from opensignal_job_intel.models import JobRecord, JobSource, utc_now
from opensignal_job_intel.sources.base import JobSourceAdapter

from opensignal_job_intel.sources.linkedin_acquire import (
    LinkedInAcquisitionDiagnostics,
    LinkedInScrapeAdapter,
)


def parse_optional_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


class LinkedInJsonFileAdapter(JobSourceAdapter):
    """Minimal v1 LinkedIn boundary backed by local JSON input."""

    def __init__(self, input_path: str | Path) -> None:
        self._input_path = Path(input_path)

    def fetch_jobs(self) -> list[JobRecord]:
        payload = json.loads(self._input_path.read_text(encoding="utf-8"))
        items = payload["jobs"] if isinstance(payload, dict) else payload
        collected_at = utc_now()
        return [self._normalize_item(item, collected_at) for item in items]

    def _normalize_item(
        self, item: dict[str, Any], collected_at: datetime
    ) -> JobRecord:
        return JobRecord(
            source=JobSource.LINKEDIN,
            external_job_id=item.get("id") or item.get("job_id"),
            company=item["company"],
            title=item["title"],
            description=item.get("description", ""),
            post_datetime=parse_optional_datetime(
                item.get("posted_at") or item.get("post_datetime")
            ),
            link=item["link"],
            salary_text=item.get("salary"),
            collected_at=collected_at,
        )


__all__ = [
    "LinkedInJsonFileAdapter",
    "LinkedInScrapeAdapter",
    "LinkedInAcquisitionDiagnostics",
]
