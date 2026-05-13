"""Core domain inputs for job ingestion and evaluation.

Author: Ezequiel H. Martinez
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, replace
from datetime import datetime, time, timezone
from enum import StrEnum
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class JobSource(StrEnum):
    """Enumerate the supported upstream job sources."""

    LINKEDIN = "linkedin"
    INDEED = "indeed"


class Clock:
    """Provide time-related values used by the domain layer."""

    @staticmethod
    def utc_now() -> datetime:
        """Return the current UTC timestamp."""
        return datetime.now(timezone.utc)


class SourceLinkNormalizer:
    """Normalize source links into a stable dedupe-friendly form."""

    @staticmethod
    def normalize(link: str) -> str:
        """Strip unstable link parts so deduplication stays stable."""
        parts = urlsplit(link.strip())
        query = ""
        if "indeed." in parts.netloc and parts.path.rstrip("/") == "/viewjob":
            params = dict(parse_qsl(parts.query, keep_blank_values=False))
            if "jk" in params:
                query = urlencode({"jk": params["jk"]})
        return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), query, ""))


def utc_now() -> datetime:
    """Expose the domain clock as a module-level helper."""
    return Clock.utc_now()


def normalize_source_link(link: str) -> str:
    """Expose source-link normalization as a module-level helper."""
    return SourceLinkNormalizer.normalize(link)


@dataclass(slots=True)
class JobRecord:
    """Represent a canonical job row before or after persistence."""

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
        """Return a trimmed copy suitable for storage and comparison."""
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
        """Build the stable key used for duplicate-safe persistence."""
        if self.external_job_id:
            return f"{self.source}:{self.external_job_id.strip()}"
        return f"{self.source}:{normalize_source_link(self.link)}"


@dataclass(slots=True)
class ProfessionalCompass:
    """Capture the user intent and search constraints for evaluation."""

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
    """Hold the scored, human-readable evaluation for a job record."""

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
    """Describe timing and pacing rules for the harvest workflow."""

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
    """Persist global harvest throttle and caution state."""

    source: str
    throttle_events: int = 0
    current_backoff_seconds: float = 0.0
    sticky_caution_enabled: bool = False
    last_throttle_at: datetime | None = None
    last_success_at: datetime | None = None


@dataclass(slots=True)
class HarvestQueryState:
    """Persist per-query resume state for harvest searches."""

    source: str
    query: str
    next_start: int = 0
    consecutive_empty_pages: int = 0
    yielded_new_ids: int = 0
    saw_stale_results: bool = False
    last_success_at: datetime | None = None


class ProfessionalCompassLoader:
    """Load and normalize the professional compass input document."""

    @staticmethod
    def load(path: str | Path) -> ProfessionalCompass:
        """Read a compass JSON document into the canonical dataclass."""
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        search = payload.get("search") or {}
        return ProfessionalCompass(
            summary_instruction=payload["summary_instruction"],
            required_output_fields=payload["required_output_fields"],
            context_about_me=payload["context_about_me"],
            positioning=payload["positioning"],
            current_situation=payload["current_situation"],
            target_roles=payload["target_roles"],
            hard_filters=payload["hard_filters"],
            min_monthly_usd=payload["compensation"]["min_monthly_usd"],
            target_monthly_usd_range=payload["compensation"]["target_monthly_usd_range"],
            remote_only=payload["constraints"]["remote_only"],
            preferred_timezone_overlap=payload["constraints"][
                "preferred_timezone_overlap"
            ],
            search_max_post_age_days=search.get("max_post_age_days"),
            search_workplace_types=search.get("workplace_types"),
            search_regions=search.get("regions"),
        )


def load_professional_compass(path: str | Path) -> ProfessionalCompass:
    """Load a professional compass from disk."""
    return ProfessionalCompassLoader.load(path)


TECH_KEYWORDS = [
    "python",
    "sql",
    "snowflake",
    "dbt",
    "airflow",
    "spark",
    "databricks",
    "llm",
    "rag",
    "aws",
    "gcp",
    "azure",
    "docker",
    "kubernetes",
    "pandas",
    "ml",
]


class JobCompassEvaluator:
    """Evaluate job records against the professional compass."""

    def __init__(self, compass: ProfessionalCompass) -> None:
        """Bind the evaluator to a single professional compass."""
        self._compass = compass

    def evaluate(self, job: JobRecord) -> JobEvaluation:
        """Score one job record and build the user-facing evaluation."""
        techs = self._extract_techs(job)
        responsibility_level = self._classify_responsibility(job)
        company_type = self._classify_company_type(job)
        salary = self._normalize_salary(job.salary_text)
        score = self._score_match(job, techs, responsibility_level, company_type, salary)
        summary = self._summarize(job, responsibility_level, company_type, techs)
        return JobEvaluation(
            company=job.company,
            position=job.title,
            job_url=job.link,
            summary=summary,
            techs=techs,
            responsibility_level=responsibility_level,
            company_type=company_type,
            salary=salary,
            score=score,
        )

    def as_dict(self, evaluation: JobEvaluation) -> dict[str, object]:
        """Convert an evaluation into a JSON-ready dictionary."""
        return asdict(evaluation)

    def _extract_techs(self, job: JobRecord) -> list[str]:
        """Extract the normalized technology tags mentioned in a job."""
        haystack = f"{job.title} {job.description}".lower()
        found = [
            keyword.upper() if keyword == "llm" else keyword.title()
            for keyword in TECH_KEYWORDS
            if keyword in haystack
        ]
        return sorted(dict.fromkeys(found))

    def _classify_responsibility(self, job: JobRecord) -> str:
        """Infer the responsibility level from title and description text."""
        haystack = f"{job.title} {job.description}".lower()
        if any(term in haystack for term in ("manager", "head of", "director", "people management")):
            return "manager"
        if any(term in haystack for term in ("lead", "principal", "staff", "tech lead")):
            return "lead"
        if "senior" in haystack:
            return "senior"
        if any(
            term in haystack
            for term in (
                "architect",
                "engineer",
                "scientist",
                "individual contributor",
                "hands-on",
            )
        ):
            return "ic"
        return "unknown"

    def _classify_company_type(self, job: JobRecord) -> str:
        """Infer the employer context from the job description text."""
        haystack = job.description.lower()
        if any(term in haystack for term in ("consulting", "consultancy", "client delivery", "advisory")):
            return "consulting"
        if any(term in haystack for term in ("staff augmentation", "body shop", "outsourcing")):
            return "body shop"
        if any(term in haystack for term in ("platform product", "saas product", "our product", "product team")):
            return "product"
        if any(term in haystack for term in ("services company", "service delivery", "managed services")):
            return "services"
        return "unknown"

    def _normalize_salary(self, salary_text: str | None) -> str:
        """Normalize salary text into a coarse monthly USD representation."""
        if not salary_text:
            return "Unknown"
        match = re.search(
            r"\$?\s*(\d[\d,]*)\s*(?:-|to)\s*\$?\s*(\d[\d,]*)",
            salary_text.lower(),
        )
        if match:
            start = int(match.group(1).replace(",", ""))
            end = int(match.group(2).replace(",", ""))
            if "year" in salary_text.lower() or "annual" in salary_text.lower():
                start //= 12
                end //= 12
            return f"{start} to {end} monthly usd"
        single = re.search(r"\$?\s*(\d[\d,]*)", salary_text)
        if single:
            amount = int(single.group(1).replace(",", ""))
            if "year" in salary_text.lower() or "annual" in salary_text.lower():
                amount //= 12
            return f"{amount} monthly usd"
        return salary_text

    def _score_match(
        self,
        job: JobRecord,
        techs: list[str],
        responsibility_level: str,
        company_type: str,
        salary: str,
    ) -> int:
        """Compute the bounded compass-fit score for a job."""
        haystack = f"{job.title} {job.description}".lower()
        score = 5
        if any(role.lower() in haystack for role in self._compass.target_roles):
            score += 2
        if any(term in haystack for term in ("ai", "data", "ml", "llm", "platform", "architect")):
            score += 1
        if len(techs) >= 3:
            score += 1
        if responsibility_level in {"lead", "ic", "senior"}:
            score += 1
        if responsibility_level == "manager":
            score -= 2
        if company_type in {"consulting", "body shop"}:
            score -= 2
        if "remote" in haystack:
            score += 1
        if salary != "Unknown":
            salary_amounts = [int(value) for value in re.findall(r"\d+", salary)]
            if salary_amounts and max(salary_amounts) >= self._compass.min_monthly_usd:
                score += 1
        return max(1, min(10, score))

    def _summarize(
        self,
        job: JobRecord,
        responsibility_level: str,
        company_type: str,
        techs: list[str],
    ) -> str:
        """Generate the short natural-language summary for a job."""
        tech_summary = ", ".join(techs[:4]) if techs else "general data stack"
        sentence = (
            f"{job.title} at {job.company}: {responsibility_level} role in a "
            f"{company_type} context focused on {tech_summary} and production data or AI systems."
        )
        return sentence[:240]


class JobSourceAdapter(ABC):
    """Abstract source adapter for canonical job acquisition."""

    @abstractmethod
    def fetch_jobs(self) -> list[JobRecord]:
        """Return canonical job records from the backing source."""
        raise NotImplementedError


@dataclass(slots=True)
class IngestionResult:
    """Summarize one ingestion run, including persistence breakdown."""

    fetched: int
    stored: int
    inserted: int
    updated: int
    evaluations: list[JobEvaluation]


class JobIngestionService:
    """Store and evaluate canonical job records from a source adapter."""

    def __init__(
        self,
        adapter: JobSourceAdapter,
        repository: object,
        evaluator: JobCompassEvaluator,
    ) -> None:
        """Bind the source adapter, repository, and evaluator collaborators."""
        self._adapter = adapter
        self._repository = repository
        self._evaluator = evaluator

    def ingest(self) -> IngestionResult:
        """Fetch, persist, and evaluate one batch of jobs."""
        jobs = [job.normalized() for job in self._adapter.fetch_jobs()]
        stored = 0
        inserted = 0
        updated = 0
        evaluations: list[JobEvaluation] = []
        for job in jobs:
            was_inserted = self._repository.upsert_job(job)
            evaluations.append(self._evaluator.evaluate(job))
            stored += 1
            if was_inserted:
                inserted += 1
            else:
                updated += 1
        return IngestionResult(
            fetched=len(jobs),
            stored=stored,
            inserted=inserted,
            updated=updated,
            evaluations=evaluations,
        )

    def list_jobs(self, limit: int = 20) -> list[JobRecord]:
        """Return the most recent persisted jobs for display."""
        return self._repository.list_jobs(limit=limit)


__all__ = [
    "Clock",
    "HarvestQueryState",
    "HarvestRunState",
    "HarvestSchedule",
    "IngestionResult",
    "JobCompassEvaluator",
    "JobEvaluation",
    "JobIngestionService",
    "JobRecord",
    "JobSource",
    "JobSourceAdapter",
    "ProfessionalCompass",
    "ProfessionalCompassLoader",
    "SourceLinkNormalizer",
    "load_professional_compass",
    "normalize_source_link",
    "utc_now",
]
