"""Wellfound acquisition and extraction for the refactored system.

This module provides both live acquisition (best-effort HTTP scraping) and
fixture-backed ingestion for Wellfound job postings.

Author: Ezequiel H. Martinez
"""

from __future__ import annotations

import html
import json
import os
import re
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
from src.linkedin_extraction_filtering import LinkedInFilterEvaluator


@dataclass(slots=True)
class WellfoundAcquisitionDiagnostics:
    """Track request, parse, and filter counts for one Wellfound acquisition run."""

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


class WellfoundScrapeAdapter(JobSourceAdapter):
    """Live Wellfound acquisition adapter (best-effort guest scraping)."""

    def __init__(
        self,
        compass: ProfessionalCompass,
        *,
        max_queries: int = 6,
        max_pages_per_query: int = 1,
        max_jobs: int = 30,
        request_delay_seconds: float = 1.0,
        capture_dir: str | None = None,
        write_fixture_path: str | None = None,
    ) -> None:
        """Bind compass, pacing, and optional capture/fixture destinations."""
        self._compass = compass
        self._max_queries = max_queries
        self._max_pages_per_query = max_pages_per_query
        self._max_jobs = max_jobs
        self._request_delay_seconds = request_delay_seconds
        self._capture_dir = Path(capture_dir) if capture_dir else None
        self._write_fixture_path = Path(write_fixture_path) if write_fixture_path else None

        # Optional cookie header for environments where guest mode is blocked.
        self._cookies = os.environ.get("WELLFOUND_COOKIES")

        self.diagnostics = WellfoundAcquisitionDiagnostics()

    def fetch_jobs(self) -> list[JobRecord]:
        """Fetch, extract, filter, and optionally serialize live Wellfound jobs."""
        collected_at = utc_now()
        max_age_days = self._compass.search_max_post_age_days
        allowed_workplace = _normalize_str_list(self._compass.search_workplace_types)
        allowed_regions = _normalize_str_list(self._compass.search_regions)

        queries = _derive_queries(self._compass, limit=self._max_queries)
        job_links: list[str] = []
        for query in queries:
            for page in range(self._max_pages_per_query):
                search_url = _build_search_url(query=query, page=page)
                html_text = self._fetch_text(search_url, kind="search")
                if not html_text:
                    continue
                self.diagnostics.search_pages += 1
                job_links.extend(extract_job_links_from_search_html(html_text))
                if len(set(job_links)) >= self._max_jobs:
                    break
            if len(set(job_links)) >= self._max_jobs:
                break

        unique_links = list(dict.fromkeys(job_links))[: self._max_jobs]
        jobs: list[JobRecord] = []
        raw_fixture: list[dict[str, object]] = []
        for link in unique_links:
            html_text = self._fetch_text(link, kind="job")
            if not html_text:
                self.diagnostics.dropped += 1
                self.diagnostics.drops.append(f"missing_detail_html:{link}")
                continue
            self.diagnostics.job_detail_pages += 1

            job = extract_job_from_detail_html(
                html_text,
                collected_at=collected_at,
                fallback_link=link,
            )
            if job is None:
                self.diagnostics.parse_failures += 1
                self.diagnostics.dropped += 1
                self.diagnostics.drops.append(f"parse_failed:{link}")
                continue
            self.diagnostics.record_extraction_mode("deterministic")

            if not _passes_filters(
                job,
                max_post_age_days=max_age_days,
                allowed_workplace_types=allowed_workplace,
                allowed_regions=allowed_regions,
            ):
                self.diagnostics.dropped += 1
                self.diagnostics.drops.append(f"filtered:{job.external_job_id or link}")
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
        """Fetch one Wellfound page and record request diagnostics."""
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; opensignal-job-intel/1.0)",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if self._cookies:
            headers["Cookie"] = self._cookies

        self.diagnostics.requests += 1
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30, context=_ssl_context()) as resp:
                text = resp.read().decode("utf-8", errors="replace")
                if self._capture_dir:
                    safe = urllib.parse.quote_plus(url)[:120]
                    _write_capture(self._capture_dir, f"{kind}_{safe}.html", text)
                return text
        except urllib.error.HTTPError as exc:
            self.diagnostics.dropped += 1
            self.diagnostics.drops.append(f"http_{exc.code}:{kind}:{url}")
            return None
        except urllib.error.URLError as exc:
            self.diagnostics.dropped += 1
            self.diagnostics.drops.append(_format_url_error(kind=kind, url=url, error=exc))
            return None
        finally:
            if self._request_delay_seconds > 0:
                time.sleep(self._request_delay_seconds)


class WellfoundJsonFileAdapter(JobSourceAdapter):
    """Fixture-backed Wellfound acquisition."""

    def __init__(self, input_path: str | Path) -> None:
        """Bind the JSON fixture path used for offline ingestion."""
        self._input_path = Path(input_path)

    def fetch_jobs(self) -> list[JobRecord]:
        """Load and normalize a Wellfound fixture file into canonical jobs."""
        collected_at = utc_now()
        payload = json.loads(self._input_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("Wellfound fixture must be a JSON array")
        jobs: list[JobRecord] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            jobs.append(self._normalize_item(item, collected_at))
        return jobs

    def _normalize_item(self, item: dict[str, Any], collected_at: datetime) -> JobRecord:
        """Normalize one fixture row into a canonical job record."""
        company = str(item.get("company") or "").strip()
        title = str(item.get("title") or "").strip()
        description = str(item.get("description") or "").strip()
        link = str(item.get("link") or "").strip()
        external_job_id = item.get("external_job_id")
        if not company or not title or not description or not link:
            raise ValueError("Fixture row missing required Wellfound fields")
        return JobRecord(
            source=JobSource.WELLFOUND,
            external_job_id=str(external_job_id).strip() if external_job_id else _extract_job_id(link),
            company=company,
            title=title,
            description=description,
            link=link,
            collected_at=collected_at,
        )


def extract_job_links_from_search_html(html_text: str) -> list[str]:
    """Extract Wellfound job detail links from a search/list page."""
    # Capture only the stable path portion of the job URL, ignoring tracking query params.
    links = re.findall(r'href="(/jobs/\d+[^"#?]*)(?:\?[^"#]*)?"', html_text)
    absolute = []
    for rel in links:
        absolute.append(urllib.parse.urljoin("https://wellfound.com", rel))
    return list(dict.fromkeys(absolute))


def extract_job_from_detail_html(
    html_text: str,
    *,
    collected_at: datetime,
    fallback_link: str,
) -> JobRecord | None:
    """Extract a canonical job record from a Wellfound job detail HTML page."""
    title = _extract_h1(html_text) or _extract_title_from_head(html_text)
    company = _extract_company_from_title(html_text)
    if not title:
        title = ""
    if not company:
        company = ""
    description = _extract_about_job_text(html_text)
    link = _extract_canonical_job_link(html_text) or fallback_link
    external_job_id = _extract_job_id(link)

    title = title.strip()
    company = company.strip()
    description = description.strip()
    link = link.strip()

    if not title or not company or not description or not link:
        return None

    return JobRecord(
        source=JobSource.WELLFOUND,
        external_job_id=external_job_id,
        company=company,
        title=title,
        description=description,
        link=link,
        collected_at=collected_at,
    )


def _extract_job_id(link: str) -> str | None:
    """Extract the numeric Wellfound job id from a job link."""
    match = re.search(r"/jobs/(\d+)", link)
    return match.group(1) if match else None


def _extract_h1(html_text: str) -> str | None:
    """Extract the first h1 text from HTML."""
    match = re.search(r"<h1[^>]*>(.*?)</h1>", html_text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return _strip_tags(match.group(1)).strip()


def _extract_title_from_head(html_text: str) -> str | None:
    """Extract job title from the document <title> fallback."""
    match = re.search(r"<title[^>]*>(.*?)</title>", html_text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    value = html.unescape(_strip_tags(match.group(1))).strip()
    if " at " in value:
        return value.split(" at ", 1)[0].strip()
    return value


def _extract_company_from_title(html_text: str) -> str | None:
    """Extract company name from the document <title> fallback."""
    match = re.search(r"<title[^>]*>(.*?)</title>", html_text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    value = html.unescape(_strip_tags(match.group(1))).strip()
    if " at " not in value:
        return None
    after = value.split(" at ", 1)[1]
    company = after.split("•", 1)[0].strip()
    company = company.split("|", 1)[0].strip()
    return company or None


def _extract_about_job_text(html_text: str) -> str:
    """Extract a best-effort job description from the 'About the job' section."""
    # Prefer the "About the job" section if present.
    match = re.search(
        r"About the job</[^>]+>(.*?)(<h2|<hr|</section>)",
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match:
        return _strip_tags(match.group(1)).strip()
    # Fallback: strip all tags (may be noisy but non-empty for fixtures/tests).
    return _strip_tags(html_text).strip()


def _extract_canonical_job_link(html_text: str) -> str | None:
    """Extract the canonical Wellfound job link when present."""
    match = re.search(
        r'<link[^>]+rel="canonical"[^>]+href="([^"]+)"',
        html_text,
        flags=re.IGNORECASE,
    )
    return match.group(1).strip() if match else None


def _strip_tags(value: str) -> str:
    """Convert HTML into plain text by dropping tags and normalizing whitespace."""
    text = re.sub(r"<script[^>]*>.*?</script>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[\t\r\n]+", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _derive_queries(compass: ProfessionalCompass, limit: int) -> list[str]:
    """Derive distinct search queries from the compass target roles."""
    base = [role for role in compass.target_roles if role.strip()]
    queries = []
    for role in base:
        query = role
        if compass.remote_only and "remote" not in query.lower():
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
    """Delegate region derivation to the shared filter evaluator."""
    return LinkedInFilterEvaluator.derive_region(location_text)


def _build_search_url(*, query: str, page: int) -> str:
    """Build a best-effort Wellfound jobs URL for a keyword query.

    Note: Wellfound's public job search is primarily UI-driven. This URL shape is
    best-effort and may need adjustment if Wellfound changes query parameters.
    """
    params = {"query": query}
    if page > 0:
        params["page"] = str(page + 1)
    return "https://wellfound.com/jobs?" + urllib.parse.urlencode(params)


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
    """Build the SSL context used for live Wellfound requests."""
    cafile_override = os.environ.get("WELLFOUND_SSL_CAFILE")
    if cafile_override:
        return ssl.create_default_context(cafile=cafile_override)
    try:
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


__all__ = [
    "WellfoundAcquisitionDiagnostics",
    "WellfoundScrapeAdapter",
    "WellfoundJsonFileAdapter",
    "extract_job_from_detail_html",
    "extract_job_links_from_search_html",
]
