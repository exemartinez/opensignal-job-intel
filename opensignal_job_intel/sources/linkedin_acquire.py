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

from opensignal_job_intel.llm import LocalLlmClient
from opensignal_job_intel.models import JobRecord, JobSource, ProfessionalCompass, utc_now
from opensignal_job_intel.sources.base import JobSourceAdapter
from opensignal_job_intel.sources.linkedin_extraction import (
    LinkedInExtractionSpec,
    extract_job_from_detail_html,
    extract_job_ids_from_search_html,
    load_extraction_spec,
)


@dataclass(slots=True)
class LinkedInAcquisitionDiagnostics:
    requests: int = 0
    search_pages: int = 0
    job_detail_pages: int = 0
    parse_failures: int = 0
    dropped: int = 0
    drops: list[str] = field(default_factory=list)
    extraction_mode_counts: dict[str, int] = field(default_factory=dict)

    def record_extraction_mode(self, mode: str) -> None:
        self.extraction_mode_counts[mode] = self.extraction_mode_counts.get(mode, 0) + 1

    def as_dict(self) -> dict[str, object]:
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
    """Live LinkedIn acquisition (scrape) adapter.

    This adapter:
    - derives search queries from the compass
    - scrapes search pages to collect job ids
    - scrapes job detail pages to obtain full descriptions
    - uses deterministic JSON-LD extraction first
    - optionally uses a local LLM endpoint as a fallback extraction mechanism
    """

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
        collected_at = utc_now()
        queries = _derive_queries(self._compass, limit=self._max_queries)
        job_ids: list[str] = []
        for query in queries:
            for page in range(self._max_pages_per_query):
                search_url = _build_search_url(query=query, start=page * 25)
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
                job = self._llm_fallback_extract(html=html, collected_at=collected_at, fallback_link=link)

            if job is None:
                self.diagnostics.dropped += 1
                self.diagnostics.drops.append(f"parse_failed:{job_id}")
                if self._capture_dir:
                    _write_capture(self._capture_dir, f"job_{job_id}.html", html)
                continue

            jobs.append(job)
            raw_fixture.append(
                {
                    "id": job.external_job_id or job_id,
                    "company": job.company,
                    "title": job.title,
                    "description": job.description,
                    "posted_at": job.post_datetime.isoformat() if job.post_datetime else None,
                    "salary": job.salary_text,
                    "link": job.link,
                }
            )

        if self._write_fixture_path:
            self._write_fixture_path.parent.mkdir(parents=True, exist_ok=True)
            self._write_fixture_path.write_text(
                json.dumps(raw_fixture, ensure_ascii=True, indent=2), encoding="utf-8"
            )

        return jobs

    def _fetch_text(self, url: str, kind: str) -> str | None:
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
            self.diagnostics.drops.append(f"ssl_verify_failed:{kind}:{exc}")
            return None
        except urllib.error.URLError as exc:
            self.diagnostics.dropped += 1
            self.diagnostics.drops.append(f"url_error:{kind}:{exc}")
            return None
        finally:
            if self._request_delay_seconds > 0:
                time.sleep(self._request_delay_seconds)

    def _llm_fallback_extract(
        self, html: str, collected_at: datetime, fallback_link: str
    ) -> JobRecord | None:
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
        # Avoid sending extremely large payloads.
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


def _derive_queries(compass: ProfessionalCompass, limit: int) -> list[str]:
    # Minimal heuristic: use target roles, plus "remote" if requested.
    base = [role for role in compass.target_roles if role.strip()]
    queries = []
    for role in base:
        q = role
        if compass.remote_only:
            q = f"{q} remote"
        queries.append(q)
    # Deduplicate while keeping order.
    return list(dict.fromkeys(queries))[:limit]


def _build_search_url(query: str, start: int) -> str:
    params = {
        "keywords": query,
        "start": str(start),
    }
    return "https://www.linkedin.com/jobs/search/?" + urllib.parse.urlencode(params)


def _write_capture(dir_path: Path, name: str, content: str) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / name).write_text(content, encoding="utf-8")


def _ssl_context() -> ssl.SSLContext:
    """Return a verifying SSL context, preferring certifi when available.

    Some Python distributions on macOS/conda can lack a usable default CA bundle.
    """

    if os.environ.get("LINKEDIN_INSECURE_SSL") == "1":
        # Explicit opt-in only. Not recommended.
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    cafile_override = os.environ.get("LINKEDIN_SSL_CAFILE")
    if cafile_override:
        return ssl.create_default_context(cafile=cafile_override)

    try:
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()
