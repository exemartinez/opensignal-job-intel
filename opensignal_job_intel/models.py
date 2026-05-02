from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, time, timezone
from enum import StrEnum
from urllib.parse import urlsplit, urlunsplit


class JobSource(StrEnum):
    LINKEDIN = "linkedin"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_source_link(link: str) -> str:
    parts = urlsplit(link.strip())
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


@dataclass(slots=True)
class JobRecord:
    source: JobSource
    company: str
    title: str
    description: str
    link: str
    collected_at: datetime
    external_job_id: str | None = None
    post_datetime: datetime | None = None
    stored_at: datetime | None = None
    salary_text: str | None = None
    location_text: str | None = None
    workplace_type: str | None = None
    post_age_text: str | None = None
    post_age_days: int | None = None
    seen: bool = False
    applied: bool = False

    def normalized(self) -> "JobRecord":
        return replace(
            self,
            company=self.company.strip(),
            title=self.title.strip(),
            description=self.description.strip(),
            link=normalize_source_link(self.link),
            salary_text=self.salary_text.strip() if self.salary_text else None,
            location_text=self.location_text.strip() if self.location_text else None,
            workplace_type=self.workplace_type.strip() if self.workplace_type else None,
            post_age_text=self.post_age_text.strip() if self.post_age_text else None,
        )

    @property
    def dedupe_key(self) -> str:
        if self.external_job_id:
            return f"{self.source}:{self.external_job_id.strip()}"
        return f"{self.source}:{normalize_source_link(self.link)}"


@dataclass(slots=True)
class ProfessionalCompass:
    summary_instruction: str
    required_output_fields: list[str]
    context_about_me: list[str]
    positioning: str
    current_situation: list[str]
    target_roles: list[str]
    hard_filters: list[str]
    min_monthly_usd: int
    target_monthly_usd_range: list[int]
    remote_only: bool
    preferred_timezone_overlap: str
    search_max_post_age_days: int | None = None
    search_workplace_types: list[str] | None = None
    search_regions: list[str] | None = None


@dataclass(slots=True)
class JobEvaluation:
    company: str
    position: str
    job_url: str
    summary: str
    techs: list[str]
    responsibility_level: str
    company_type: str
    salary: str
    score: int


@dataclass(slots=True)
class HarvestSchedule:
    window_start: time
    window_end: time
    max_queries: int
    max_pages_per_query: int
    empty_search_pages_threshold: int
    base_delay_seconds: float
    jitter_seconds: float
    sticky_caution_multiplier: float
    backoff_initial_seconds: float
    backoff_multiplier: float
    backoff_max_seconds: float
    summary_every_requests: int
    log_path: str
    missing_signal_policy: str = "keep"


@dataclass(slots=True)
class HarvestRunState:
    source: str
    throttle_events: int = 0
    current_backoff_seconds: float = 0.0
    sticky_caution_enabled: bool = False
    last_throttle_at: datetime | None = None
    last_success_at: datetime | None = None


@dataclass(slots=True)
class HarvestQueryState:
    source: str
    query: str
    next_start: int = 0
    consecutive_empty_pages: int = 0
    yielded_new_ids: int = 0
    saw_stale_results: bool = False
    last_success_at: datetime | None = None
