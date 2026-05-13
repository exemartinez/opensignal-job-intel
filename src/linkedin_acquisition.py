"""LinkedIn acquisition and fixture serialization for the refactored system.

Author: Ezequiel H. Martinez
"""

from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src.core_domain_inputs import (
    JobRecord,
    JobSource,
    JobSourceAdapter,
    ProfessionalCompass,
    utc_now,
)
from src.linkedin_extraction_filtering import (
    LinkedInExtractionSpec,
    LinkedInFilterEvaluator,
    LocalLlmClient,
    extract_job_from_detail_html,
    extract_job_ids_from_search_html,
    load_extraction_spec,
)


@dataclass(slots=True)
class LinkedInAcquisitionDiagnostics:
    """Track request, parse, and filter counts for one acquisition run."""

    requests: int = 0
    search_pages: int = 0
    job_detail_pages: int = 0
    parse_failures: int = 0
    dropped: int = 0
    drops: list[str] = field(default_factory=list)
    extraction_mode_counts: dict[str, int] = field(default_factory=dict)

    def record_extraction_mode(self, mode: str) -> None:
        """Increment the counter for the extraction path that succeeded."""
        self.extraction_mode_counts[mode] = self.extraction_mode_counts.get(mode, 0) + 1

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-ready representation of the diagnostics."""
        return {
            "requests": self.requests,
            "search_pages": self.search_pages,
            "job_detail_pages": self.job_detail_pages,
            "parse_failures": self.parse_failures,
            "dropped": self.dropped,
            "drops": list(self.drops),
            "extraction_mode_counts": dict(self.extraction_mode_counts),
        }


class LinkedInScrapeAdapter(JobSourceAdapter):
    """Live LinkedIn acquisition adapter."""

    def __init__(
        self,
        compass: ProfessionalCompass,
        extraction_spec_path: str,
        max_queries: int = 6,
        max_pages_per_query: int = 2,
        max_jobs: int = 30,
        request_delay_seconds: float = 1.0,
        capture_dir: str | None = None,
        write_fixture_path: str | None = None,
        llm_base_url: str | None = None,
        llm_model: str | None = None,
    ) -> None:
        """Bind compass, extraction, pacing, and optional fallback settings."""
        self._compass = compass
        self._spec: LinkedInExtractionSpec = load_extraction_spec(extraction_spec_path)
        self._max_queries = max_queries
        self._max_pages_per_query = max_pages_per_query
        self._max_jobs = max_jobs
        self._request_delay_seconds = request_delay_seconds
        self._capture_dir = Path(capture_dir) if capture_dir else None
        self._write_fixture_path = Path(write_fixture_path) if write_fixture_path else None

        self._cookies = os.environ.get("LINKEDIN_COOKIES")
        self._csrf = os.environ.get("LINKEDIN_CSRF")

        llm_url = llm_base_url or os.environ.get("LOCAL_LLM_BASE_URL")
        self._llm = LocalLlmClient(llm_url, model=llm_model) if llm_url else None

        self.diagnostics = LinkedInAcquisitionDiagnostics()

    def fetch_jobs(self) -> list[JobRecord]:
        """Fetch, extract, filter, and optionally serialize live LinkedIn jobs."""
        collected_at = utc_now()
        max_age_days = self._compass.search_max_post_age_days
        allowed_workplace = _normalize_str_list(self._compass.search_workplace_types)
        allowed_regions = _normalize_str_list(self._compass.search_regions)
        queries = _derive_queries(self._compass, limit=self._max_queries)
        job_ids: list[str] = []
        for query in queries:
            for page in range(self._max_pages_per_query):
                search_url = _build_search_url(
                    query=query,
                    start=page * 25,
                    max_post_age_days=max_age_days,
                )
                html = self._fetch_text(search_url, kind="search")
                if not html:
                    continue
                self.diagnostics.search_pages += 1
                job_ids.extend(extract_job_ids_from_search_html(html, self._spec))
                if len(set(job_ids)) >= self._max_jobs:
                    break
            if len(set(job_ids)) >= self._max_jobs:
                break

        unique_ids = list(dict.fromkeys(job_ids))[: self._max_jobs]
        jobs: list[JobRecord] = []
        raw_fixture: list[dict[str, object]] = []
        for job_id in unique_ids:
            link = f"https://www.linkedin.com/jobs/view/{job_id}/"
            html = self._fetch_text(link, kind="job")
            if not html:
                self.diagnostics.dropped += 1
                self.diagnostics.drops.append(f"missing_detail_html:{job_id}")
                continue
            self.diagnostics.job_detail_pages += 1

            job = extract_job_from_detail_html(html, collected_at=collected_at, fallback_link=link)
            if job is not None:
                self.diagnostics.record_extraction_mode("deterministic")
            else:
                self.diagnostics.parse_failures += 1
                job = self._llm_fallback_extract(
                    html=html,
                    collected_at=collected_at,
                    fallback_link=link,
                )

            if job is None:
                self.diagnostics.dropped += 1
                self.diagnostics.drops.append(f"parse_failed:{job_id}")
                if self._capture_dir:
                    _write_capture(self._capture_dir, f"job_{job_id}.html", html)
                continue

            if not _passes_filters(
                job,
                max_post_age_days=max_age_days,
                allowed_workplace_types=allowed_workplace,
                allowed_regions=allowed_regions,
            ):
                self.diagnostics.dropped += 1
                self.diagnostics.drops.append(f"filtered:{job_id}")
                continue

            jobs.append(job)
            raw_fixture.append(_job_to_fixture_item(job))

        if self._write_fixture_path:
            self._write_fixture_path.parent.mkdir(parents=True, exist_ok=True)
            self._write_fixture_path.write_text(
                json.dumps(raw_fixture, ensure_ascii=True, indent=2),
                encoding="utf-8",
            )

        return jobs

    def _fetch_text(self, url: str, kind: str) -> str | None:
        """Fetch one guest-page HTML document and record request diagnostics."""
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; opensignal-job-intel/1.0)",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if self._cookies:
            headers["Cookie"] = self._cookies
        if self._csrf:
            headers["csrf-token"] = self._csrf

        self.diagnostics.requests += 1
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30, context=_ssl_context()) as resp:
                text = resp.read().decode("utf-8", errors="replace")
                if self._capture_dir and kind == "search":
                    safe = urllib.parse.quote_plus(url)[:120]
                    _write_capture(self._capture_dir, f"search_{safe}.html", text)
                return text
        except urllib.error.HTTPError as exc:
            self.diagnostics.dropped += 1
            self.diagnostics.drops.append(f"http_{exc.code}:{kind}:{url}")
            return None
        except ssl.SSLCertVerificationError as exc:
            self.diagnostics.dropped += 1
            self.diagnostics.drops.append(
                f"ssl_verify_failed:{kind}:{url}:{type(exc).__name__}:{exc}"
            )
            return None
        except urllib.error.URLError as exc:
            self.diagnostics.dropped += 1
            self.diagnostics.drops.append(_format_url_error(kind=kind, url=url, error=exc))
            return None
        finally:
            if self._request_delay_seconds > 0:
                time.sleep(self._request_delay_seconds)

    def _llm_fallback_extract(
        self,
        html: str,
        collected_at: datetime,
        fallback_link: str,
    ) -> JobRecord | None:
        """Ask the local LLM to recover a canonical job when parsing fails."""
        if not self._llm:
            return None
        system = (
            "You are extracting a job posting from HTML. "
            "Return ONLY a single JSON object with keys: "
            "company, title, description, link, external_job_id (optional)."
        )
        user = (
            "Extract the required fields from this HTML. "
            "description must be full text. "
            f"If link is not present, use: {fallback_link}\n\nHTML:\n"
        )
        html_snippet = html[:30000]
        result = self._llm.extract_json(system_prompt=system, user_prompt=user + html_snippet)
        if not result.ok or not result.data:
            return None
        payload = result.data
        company = str(payload.get("company") or "").strip()
        title = str(payload.get("title") or "").strip()
        description = str(payload.get("description") or "").strip()
        link = str(payload.get("link") or fallback_link).strip()
        external_job_id = payload.get("external_job_id")
        if not company or not title or not description or not link:
            return None
        self.diagnostics.record_extraction_mode("llm_fallback")
        return JobRecord(
            source=JobSource.LINKEDIN,
            external_job_id=str(external_job_id).strip() if external_job_id else None,
            company=company,
            title=title,
            description=description,
            link=link,
            collected_at=collected_at,
        )


class LinkedInQueryBuilder:
    """Derive and serialize live LinkedIn search queries from the compass."""

    def __init__(self, compass: ProfessionalCompass, limit: int) -> None:
        """Bind the compass and the maximum query count."""
        self._compass = compass
        self._limit = limit

    def derive_queries(self) -> list[str]:
        """Build the live LinkedIn search queries from the compass."""
        return _derive_queries(self._compass, self._limit)

    @staticmethod
    def build_search_url(query: str, start: int, *, max_post_age_days: int | None = None) -> str:
        """Serialize one live LinkedIn search URL.

        Note: this is the correct place to apply tenure filtering (server-side),
        not by mutating `post_datetime` when it is not extractable.
        """
        return _build_search_url(query=query, start=start, max_post_age_days=max_post_age_days)


class LinkedInFilterPolicy:
    """Evaluate acquisition filters for best-effort live LinkedIn jobs."""

    def __init__(
        self,
        *,
        max_post_age_days: int | None,
        allowed_workplace_types: list[str] | None,
        allowed_regions: list[str] | None,
    ) -> None:
        """Bind the optional best-effort filter constraints."""
        self._max_post_age_days = max_post_age_days
        self._allowed_workplace_types = _normalize_str_list(allowed_workplace_types)
        self._allowed_regions = _normalize_str_list(allowed_regions)

    def allows(self, job: JobRecord) -> bool:
        """Return whether a canonical job passes the configured filters."""
        return _passes_filters(
            job,
            max_post_age_days=self._max_post_age_days,
            allowed_workplace_types=self._allowed_workplace_types,
            allowed_regions=self._allowed_regions,
        )

    @staticmethod
    def derive_region(location_text: str) -> str | None:
        """Map a location string into the normalized region bucket."""
        return _derive_region(location_text)


class LinkedInFixtureSerializer:
    """Serialize and persist canonical LinkedIn fixture records."""

    @staticmethod
    def item_from_job(job: JobRecord) -> dict[str, object]:
        """Convert one canonical job into the fixture export row shape."""
        return _job_to_fixture_item(job)

    @staticmethod
    def write(path: str | Path, jobs: list[JobRecord]) -> None:
        """Write canonical fixture rows to disk."""
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = [LinkedInFixtureSerializer.item_from_job(job) for job in jobs]
        destination.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8"
        )


@dataclass(slots=True)
class LinkedInTransport:
    """Expose transport-oriented helpers used by live LinkedIn acquisition."""

    @staticmethod
    def ssl_context():
        """Return the SSL context used for live LinkedIn requests."""
        return _ssl_context()

    @staticmethod
    def format_url_error(*, kind: str, url: str, error) -> str:
        """Format a network failure for acquisition diagnostics."""
        return _format_url_error(kind=kind, url=url, error=error)

    @staticmethod
    def write_capture(dir_path: Path, name: str, content: str) -> None:
        """Persist a raw HTML capture for debugging."""
        _write_capture(dir_path, name, content)


class LinkedInJsonFileAdapter(JobSourceAdapter):
    """Fixture-backed LinkedIn acquisition under the refactored surface."""

    def __init__(self, input_path: str | Path) -> None:
        """Bind the JSON fixture path used for offline ingestion."""
        self._input_path = Path(input_path)

    def fetch_jobs(self) -> list[JobRecord]:
        """Load and normalize all fixture rows into canonical job records."""
        payload = json.loads(self._input_path.read_text(encoding="utf-8"))
        items = payload["jobs"] if isinstance(payload, dict) else payload
        collected_at = utc_now()
        return [self._normalize_item(item, collected_at) for item in items]

    def _normalize_item(
        self,
        item: dict[str, Any],
        collected_at: datetime,
    ) -> JobRecord:
        """Convert one fixture row into the canonical job record shape."""
        return JobRecord(
            source=JobSource.LINKEDIN,
            external_job_id=item.get("id") or item.get("job_id") or item.get("external_job_id"),
            company=item["company"],
            title=item["title"],
            description=item.get("description", ""),
            post_datetime=parse_optional_datetime(
                item.get("posted_at") or item.get("post_datetime")
            ),
            link=item["link"],
            salary_text=item.get("salary") or item.get("salary_text"),
            location_text=item.get("location_text"),
            workplace_type=item.get("workplace_type"),
            post_age_text=item.get("post_age_text"),
            post_age_days=item.get("post_age_days"),
            collected_at=collected_at,
            stored_at=parse_optional_datetime(item.get("stored_at")),
            seen=bool(item.get("seen", False)),
            applied=bool(item.get("applied", False)),
        )


class LinkedInFixtureNormalizer:
    """Normalize a raw LinkedIn fixture row into the canonical job record."""

    @staticmethod
    def normalize(item: dict[str, Any], collected_at: datetime) -> JobRecord:
        """Normalize one raw fixture row without keeping adapter state."""
        adapter = LinkedInJsonFileAdapter("__unused__")
        return adapter._normalize_item(item, collected_at)


def parse_optional_datetime(value: str | None) -> datetime | None:
    """Parse an ISO-like datetime string when present."""
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def _derive_queries(compass: ProfessionalCompass, limit: int) -> list[str]:
    """Derive distinct search queries from the compass target roles."""
    base = [role for role in compass.target_roles if role.strip()]
    queries = []
    for role in base:
        query = role
        if compass.remote_only:
            query = f"{query} remote"
        queries.append(query)
    return list(dict.fromkeys(queries))[:limit]


def _normalize_str_list(value: list[str] | None) -> list[str] | None:
    """Normalize a list of string filters for case-insensitive matching."""
    if value is None:
        return None
    normalized = [str(item).strip().lower() for item in value if str(item).strip()]
    return list(dict.fromkeys(normalized))


def _passes_filters(
    job: JobRecord,
    *,
    max_post_age_days: int | None,
    allowed_workplace_types: list[str] | None,
    allowed_regions: list[str] | None,
) -> bool:
    """Apply best-effort age, workplace, and region filters to a job."""
    if max_post_age_days is not None and job.post_age_days is not None:
        if job.post_age_days > max_post_age_days:
            return False

    if allowed_workplace_types is not None and job.workplace_type is not None:
        if job.workplace_type.strip().lower() not in allowed_workplace_types:
            return False

    if allowed_regions is not None and job.location_text:
        region = _derive_region(job.location_text)
        if region is not None and region.lower() not in allowed_regions:
            return False

    return True


def _derive_region(location_text: str) -> str | None:
    """Delegate region derivation to the shared LinkedIn filter evaluator."""
    return LinkedInFilterEvaluator.derive_region(location_text)


def _build_search_url(query: str, start: int, *, max_post_age_days: int | None = None) -> str:
    """Build the guest LinkedIn search URL for one query page."""
    params = {
        "keywords": query,
        "start": str(start),
    }
    # LinkedIn supports a "time posted" filter using `f_TPR=r<seconds>`.
    # We apply it at the search level when configured, without touching `post_datetime`.
    if max_post_age_days is not None and max_post_age_days > 0:
        params["f_TPR"] = f"r{max_post_age_days * 24 * 60 * 60}"
    return "https://www.linkedin.com/jobs/search/?" + urllib.parse.urlencode(params)


def _write_capture(dir_path: Path, name: str, content: str) -> None:
    """Write one raw HTML capture into the requested directory."""
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / name).write_text(content, encoding="utf-8")


def _job_to_fixture_item(job: JobRecord) -> dict[str, object]:
    """Convert a canonical job into the persisted fixture export shape."""
    normalized = job.normalized()
    return {
        "id": None,
        "dedupe_key": normalized.dedupe_key,
        "source": normalized.source.value,
        "external_job_id": normalized.external_job_id,
        "company": normalized.company,
        "title": normalized.title,
        "description": normalized.description,
        "post_datetime": normalized.post_datetime.isoformat() if normalized.post_datetime else None,
        "link": normalized.link,
        "salary_text": normalized.salary_text,
        "location_text": normalized.location_text,
        "workplace_type": normalized.workplace_type,
        "post_age_text": normalized.post_age_text,
        "post_age_days": normalized.post_age_days,
        "collected_at": normalized.collected_at.isoformat(),
        "stored_at": normalized.stored_at.isoformat() if normalized.stored_at else None,
        "seen": normalized.seen,
        "applied": normalized.applied,
    }


def _format_url_error(*, kind: str, url: str, error: urllib.error.URLError) -> str:
    """Format a URLError with request context for diagnostics."""
    reason = error.reason
    reason_type = type(reason).__name__ if reason is not None else "None"
    return f"url_error:{kind}:{url}:{reason_type}:{error}"


def _ssl_context() -> ssl.SSLContext:
    """Build the SSL context used by live LinkedIn requests."""
    if os.environ.get("LINKEDIN_INSECURE_SSL") == "1":
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

    cafile_override = os.environ.get("LINKEDIN_SSL_CAFILE")
    if cafile_override:
        return ssl.create_default_context(cafile=cafile_override)

    try:
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


__all__ = [
    "LinkedInAcquisitionDiagnostics",
    "LinkedInFilterPolicy",
    "LinkedInFixtureNormalizer",
    "LinkedInFixtureSerializer",
    "LinkedInJsonFileAdapter",
    "LinkedInQueryBuilder",
    "LinkedInScrapeAdapter",
    "LinkedInTransport",
    "parse_optional_datetime",
]
