"""Indeed acquisition and extraction for the refactored system.

Author: Ezequiel H. Martinez
"""

from __future__ import annotations

import html
import json
import os
import re
import time
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from src.core_domain_inputs import (
    JobRecord,
    JobSource,
    JobSourceAdapter,
    ProfessionalCompass,
    utc_now,
)
from src.linkedin_extraction_filtering import LinkedInFilterEvaluator


@dataclass(slots=True)
class IndeedAcquisitionDiagnostics:
    """Track request, parse, and filter counts for one Indeed acquisition run."""

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


class IndeedBrowserSession:
    """Manage a reusable Selenium browser session for live Indeed scraping."""

    def __init__(
        self,
        *,
        browser_name: str,
        request_delay_seconds: float,
        wait_seconds: float,
        cookie_header: str | None,
    ) -> None:
        """Bind the browser type, pacing, wait policy, and optional cookies."""
        self._browser_name = browser_name
        self._request_delay_seconds = request_delay_seconds
        self._wait_seconds = wait_seconds
        self._cookie_header = cookie_header
        self._driver = None
        self._cookies_loaded = False

    def __enter__(self) -> "IndeedBrowserSession":
        """Open the browser driver when entering the scraping session."""
        self._driver = self._build_driver()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """Close the browser driver when leaving the scraping session."""
        self.close()

    def fetch_text(self, url: str, kind: str) -> str:
        """Load one Indeed page through Selenium and return the page HTML."""
        driver = self._require_driver()
        if self._cookie_header and not self._cookies_loaded:
            self._prime_cookies(driver)
        driver.get(url)
        WebDriverWait(driver, self._wait_seconds).until(
            lambda current: current.execute_script("return document.readyState") == "complete"
        )
        WebDriverWait(driver, self._wait_seconds).until(
            lambda current: bool(current.find_elements(By.TAG_NAME, "body"))
        )
        if self._request_delay_seconds > 0:
            time.sleep(self._request_delay_seconds)
        return driver.page_source

    def close(self) -> None:
        """Quit the active Selenium driver when present."""
        if self._driver is not None:
            self._driver.quit()
            self._driver = None

    def _build_driver(self):
        """Create the configured Selenium WebDriver instance."""
        browser = self._browser_name.strip().lower()
        if browser == "safari":
            return webdriver.Safari()
        if browser == "chrome":
            options = webdriver.ChromeOptions()
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--window-size=1440,1200")
            options.add_argument(
                "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
            )
            return webdriver.Chrome(options=options)
        if browser == "firefox":
            options = webdriver.FirefoxOptions()
            options.set_preference("general.useragent.override", _browser_user_agent())
            return webdriver.Firefox(options=options)
        raise ValueError(f"Unsupported Indeed browser: {self._browser_name}")

    def _prime_cookies(self, driver) -> None:
        """Load optional user-supplied cookies into the live browser session."""
        driver.get("https://www.indeed.com/")
        WebDriverWait(driver, self._wait_seconds).until(
            lambda current: current.execute_script("return document.readyState") == "complete"
        )
        for cookie in _parse_cookie_header(self._cookie_header):
            try:
                driver.add_cookie(cookie)
            except WebDriverException:
                continue
        self._cookies_loaded = True

    def _require_driver(self):
        """Return the live driver or fail if the session is not open."""
        if self._driver is None:
            raise RuntimeError("Indeed browser session is not open.")
        return self._driver


class IndeedScrapeAdapter(JobSourceAdapter):
    """Live Indeed acquisition adapter."""

    def __init__(
        self,
        compass: ProfessionalCompass,
        max_queries: int = 6,
        max_pages_per_query: int = 2,
        max_jobs: int = 30,
        request_delay_seconds: float = 1.0,
        capture_dir: str | None = None,
        write_fixture_path: str | None = None,
    ) -> None:
        """Bind compass, paging, pacing, and local debug output settings."""
        self._compass = compass
        self._max_queries = max_queries
        self._max_pages_per_query = max_pages_per_query
        self._max_jobs = max_jobs
        self._request_delay_seconds = request_delay_seconds
        self._capture_dir = Path(capture_dir) if capture_dir else None
        self._write_fixture_path = Path(write_fixture_path) if write_fixture_path else None
        self._cookies = os.environ.get("INDEED_COOKIES")
        self._browser_name = os.environ.get("INDEED_BROWSER", "chrome")
        self._wait_seconds = float(os.environ.get("INDEED_BROWSER_WAIT_SECONDS", "15"))
        self.diagnostics = IndeedAcquisitionDiagnostics()

    def fetch_jobs(self) -> list[JobRecord]:
        """Fetch, extract, filter, and optionally serialize live Indeed jobs."""
        collected_at = utc_now()
        max_age_days = self._compass.search_max_post_age_days
        allowed_workplace = _normalize_str_list(self._compass.search_workplace_types)
        allowed_regions = _normalize_str_list(self._compass.search_regions)
        queries = _derive_queries(self._compass, limit=self._max_queries)
        jobs: list[JobRecord] = []
        raw_fixture: list[dict[str, object]] = []
        try:
            with self._browser_session() as session:
                for query in queries:
                    for page in range(self._max_pages_per_query):
                        search_url = _build_search_url(query=query, start=page * 10)
                        html = self._fetch_text(search_url, kind="search", session=session)
                        if not html:
                            continue
                        self.diagnostics.search_pages += 1
                        for job, extraction_mode in _extract_jobs_from_search_html(
                            html,
                            collected_at=collected_at,
                            limit=self._max_jobs - len(jobs),
                        ):
                            self.diagnostics.record_extraction_mode(extraction_mode)
                            if not _passes_filters(
                                job,
                                max_post_age_days=max_age_days,
                                allowed_workplace_types=allowed_workplace,
                                allowed_regions=allowed_regions,
                            ):
                                self.diagnostics.dropped += 1
                                self.diagnostics.drops.append(
                                    f"filtered:{job.external_job_id or job.dedupe_key}"
                                )
                                continue
                            jobs.append(job)
                            raw_fixture.append(_job_to_fixture_item(job))
                            if len(jobs) >= self._max_jobs:
                                break
                    if len(jobs) >= self._max_jobs:
                        break
        except Exception as exc:
            self.diagnostics.dropped += 1
            self.diagnostics.drops.append(
                f"browser_session_failed:{self._browser_name}:{type(exc).__name__}:{exc}"
            )

        if self._write_fixture_path:
            self._write_fixture_path.parent.mkdir(parents=True, exist_ok=True)
            self._write_fixture_path.write_text(
                json.dumps(raw_fixture, ensure_ascii=True, indent=2),
                encoding="utf-8",
            )

        return jobs

    def _browser_session(self) -> IndeedBrowserSession:
        """Create the browser-backed fetch session for one live run."""
        return IndeedBrowserSession(
            browser_name=self._browser_name,
            request_delay_seconds=self._request_delay_seconds,
            wait_seconds=self._wait_seconds,
            cookie_header=self._cookies,
        )

    def _fetch_text(
        self,
        url: str,
        *,
        kind: str,
        session: IndeedBrowserSession,
    ) -> str | None:
        """Fetch one Indeed document through Selenium and record diagnostics."""
        self.diagnostics.requests += 1
        try:
            text = session.fetch_text(url, kind)
            if self._capture_dir and kind == "search":
                safe = urllib.parse.quote_plus(url)[:120]
                _write_capture(self._capture_dir, f"indeed_search_{safe}.html", text)
            return text
        except WebDriverException as exc:
            self.diagnostics.dropped += 1
            self.diagnostics.drops.append(
                f"webdriver_error:{kind}:{url}:{type(exc).__name__}:{exc}"
            )
            return None
        except Exception as exc:
            self.diagnostics.dropped += 1
            self.diagnostics.drops.append(
                f"browser_error:{kind}:{url}:{type(exc).__name__}:{exc}"
            )
            return None


class IndeedJsonFileAdapter(JobSourceAdapter):
    """Fixture-backed Indeed acquisition adapter."""

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
        """Convert one fixture row into the canonical Indeed job shape."""
        return JobRecord(
            source=JobSource.INDEED,
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


class IndeedQueryBuilder:
    """Derive and serialize live Indeed search queries from the compass."""

    def __init__(self, compass: ProfessionalCompass, limit: int) -> None:
        """Bind the compass and maximum query count."""
        self._compass = compass
        self._limit = limit

    def derive_queries(self) -> list[str]:
        """Build the live Indeed search queries from the compass."""
        return _derive_queries(self._compass, self._limit)

    @staticmethod
    def build_search_url(query: str, start: int) -> str:
        """Serialize one live Indeed search URL."""
        return _build_search_url(query=query, start=start)


class IndeedFilterPolicy:
    """Evaluate acquisition filters for best-effort live Indeed jobs."""

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


class IndeedFixtureSerializer:
    """Serialize and persist canonical Indeed fixture records."""

    @staticmethod
    def item_from_job(job: JobRecord) -> dict[str, object]:
        """Convert one canonical job into the fixture export row shape."""
        return _job_to_fixture_item(job)

    @staticmethod
    def write(path: str | Path, jobs: list[JobRecord]) -> None:
        """Write canonical fixture rows to disk."""
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = [IndeedFixtureSerializer.item_from_job(job) for job in jobs]
        destination.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8"
        )


def parse_optional_datetime(value: str | None) -> datetime | None:
    """Parse an ISO-like datetime string when present."""
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _browser_user_agent() -> str:
    """Return the browser-like user agent used for Indeed automation."""
    return (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    )


def _parse_cookie_header(cookie_header: str | None) -> list[dict[str, object]]:
    """Convert a raw cookie header string into Selenium cookie dictionaries."""
    if not cookie_header:
        return []
    cookies: list[dict[str, object]] = []
    for fragment in cookie_header.split(";"):
        if "=" not in fragment:
            continue
        name, value = fragment.split("=", 1)
        normalized_name = name.strip()
        if not normalized_name:
            continue
        cookies.append(
            {
                "name": normalized_name,
                "value": value.strip(),
                "domain": ".indeed.com",
                "path": "/",
            }
        )
    return cookies


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


def _coerce_workplace_type(location_text: str | None) -> str | None:
    """Infer a workplace type from the visible Indeed location text."""
    if not location_text:
        return None
    text = location_text.strip().lower()
    if "hybrid" in text:
        return "hybrid"
    if "remote" in text or "work from home" in text:
        return "remote"
    return "onsite"


def _passes_filters(
    job: JobRecord,
    *,
    max_post_age_days: int | None,
    allowed_workplace_types: list[str] | None,
    allowed_regions: list[str] | None,
) -> bool:
    """Apply best-effort age, workplace, and region filters to an Indeed job."""
    if max_post_age_days is not None and job.post_age_days is not None:
        if job.post_age_days > max_post_age_days:
            return False

    if allowed_workplace_types is not None and job.workplace_type is not None:
        if job.workplace_type.strip().lower() not in allowed_workplace_types:
            return False

    if allowed_regions is not None and job.location_text:
        region = LinkedInFilterEvaluator.derive_region(job.location_text)
        if region is not None and region.lower() not in allowed_regions:
            return False

    return True


def _build_search_url(query: str, start: int) -> str:
    """Build the Indeed search URL for one query page."""
    params = {
        "q": query,
        "start": str(start),
    }
    return "https://www.indeed.com/jobs?" + urllib.parse.urlencode(params)


def _extract_job_ids_from_search_html(html: str) -> list[str]:
    """Extract distinct Indeed job ids from one search page."""
    ids = re.findall(r"(?:data-jk|jk)=['\"]?([A-Za-z0-9]+)", html, flags=re.IGNORECASE)
    return list(dict.fromkeys(ids))


def _extract_jobs_from_search_html(
    html_text: str,
    *,
    collected_at: datetime,
    limit: int,
) -> list[tuple[JobRecord, str]]:
    """Extract canonical jobs from one Indeed search page."""
    results: list[tuple[JobRecord, str]] = []
    payload = _extract_initial_data_payload(html_text)
    full_job = _extract_auto_open_job_from_search_html(
        html_text,
        collected_at=collected_at,
        payload=payload,
    )
    full_job_id = full_job.external_job_id if full_job is not None else None
    search_card_metadata = _extract_search_card_metadata_by_job_id(payload)
    if full_job is not None:
        results.append((full_job, "search_payload"))

    for card in _extract_search_card_jobs(
        html_text,
        collected_at=collected_at,
        metadata_by_job_id=search_card_metadata,
    ):
        if card.external_job_id == full_job_id:
            continue
        results.append((card, "search_card"))
        if len(results) >= limit:
            break

    return results[:limit]


def _extract_auto_open_job_from_search_html(
    html_text: str,
    *,
    collected_at: datetime,
    payload: dict[str, Any] | None = None,
) -> JobRecord | None:
    """Extract the auto-opened Indeed job body embedded in the search page."""
    if payload is None:
        payload = _extract_initial_data_payload(html_text)
    if payload is None:
        return None
    body = (
        payload.get("autoOpenTwoPaneViewjobResponse", {})
        .get("body", {})
    )
    if not body:
        return None
    title = _get_path(body, "jobInfoHeaderModel.jobTitle")
    company = _get_path(body, "jobInfoHeaderModel.companyName")
    description = (
        _get_path(body, "job.description.text")
        or _get_path(body, "sanitizedJobDescription")
    )
    job_key = _get_path(body, "jobKey") or _get_path(payload, "autoOpenTwoPaneJobKey")
    if not title or not company or not description or not job_key:
        return None
    location_text = _get_path(body, "jobInfoHeaderModel.companyLocation")
    salary_text = _extract_salary_from_auto_open_body(body)
    post_age_text = (
        _get_path(body, "hiringInsightsModel.age")
        or _get_path(body, "jobInfoHeaderModel.jobMetaInfo")
    )
    workplace_type = _coerce_workplace_type(
        _get_path(body, "jobInfoHeaderModel.companyLocation") or ""
    )
    return JobRecord(
        source=JobSource.INDEED,
        external_job_id=str(job_key),
        company=str(company),
        title=str(title),
        description=str(description),
        post_datetime=parse_optional_datetime(_get_path(body, "datePublished")),
        link=f"https://www.indeed.com/viewjob?jk={job_key}",
        salary_text=salary_text,
        location_text=location_text,
        workplace_type=workplace_type,
        post_age_text=post_age_text,
        post_age_days=_parse_post_age_days(post_age_text),
        collected_at=collected_at,
    )


def _extract_initial_data_payload(html_text: str) -> dict[str, Any] | None:
    """Parse the large `window._initialData` JSON object from a search page."""
    marker = "window._initialData="
    start = html_text.find(marker)
    if start == -1:
        return None
    start += len(marker)
    depth = 0
    in_string = False
    escaped = False
    end = None
    for index, char in enumerate(html_text[start:], start=start):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    if end is None:
        return None
    try:
        return json.loads(html_text[start:end])
    except json.JSONDecodeError:
        return None


def _extract_search_card_metadata_by_job_id(
    payload: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Index search-result payload job metadata by Indeed job key."""
    if not payload:
        return {}
    results = _get_path(payload, "hostQueryExecutionResult.data.jobData.results")
    if not isinstance(results, list):
        return {}
    indexed: dict[str, dict[str, Any]] = {}
    for result in results:
        if not isinstance(result, dict):
            continue
        job = result.get("job")
        if not isinstance(job, dict):
            continue
        job_key = job.get("key")
        if isinstance(job_key, str) and job_key.strip():
            indexed[job_key] = job
    return indexed


def _parse_payload_job_datetime(metadata: dict[str, Any]) -> datetime | None:
    """Extract the best available posting datetime from Indeed search payload metadata."""
    if not metadata:
        return None
    for key in ("datePublished", "dateOnIndeed"):
        parsed = _parse_epoch_millis_datetime(metadata.get(key))
        if parsed is not None:
            return parsed
    return None


def _parse_epoch_millis_datetime(value: Any) -> datetime | None:
    """Parse an epoch-millis timestamp into a UTC datetime."""
    if value is None:
        return None
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return None
    if numeric <= 0:
        return None
    return datetime.fromtimestamp(numeric / 1000, tz=timezone.utc)


def _extract_search_card_jobs(
    html_text: str,
    *,
    collected_at: datetime,
    metadata_by_job_id: dict[str, dict[str, Any]] | None = None,
) -> list[JobRecord]:
    """Extract job cards from the visible Indeed search result markup."""
    cards: list[JobRecord] = []
    pattern = re.compile(
        r'<div[^>]*data-testid="slider_item"[^>]*>.*?<div[^>]*data-testid="slider_sub_item"[^>]*>.*?</div>\s*</div>',
        flags=re.DOTALL,
    )
    for block in pattern.findall(html_text):
        job = _extract_job_from_search_card(
            block,
            collected_at=collected_at,
            metadata_by_job_id=metadata_by_job_id,
        )
        if job is not None:
            cards.append(job)
    return cards


def _extract_job_from_search_card(
    card_html: str,
    *,
    collected_at: datetime,
    metadata_by_job_id: dict[str, dict[str, Any]] | None = None,
) -> JobRecord | None:
    """Convert one search-result card into a canonical Indeed job record."""
    link = _extract_search_card_link(card_html)
    job_id = _extract_verified_search_card_job_id(card_html, link)
    title = html.unescape(_extract_raw(card_html, r'<span title="([^"]+)"'))
    company = html.unescape(
        _html_to_text(_extract_raw(card_html, r'data-testid="company-name"[^>]*>(.*?)</span>'))
    )
    location_text = html.unescape(
        _html_to_text(
            _extract_raw(card_html, r'data-testid="text-location"[^>]*>(.*?)</div>')
        )
    )
    snippet = html.unescape(
        _html_to_text(_extract_raw(card_html, r'data-testid="belowJobSnippet"[^>]*>(.*?)</div>'))
    )
    if not job_id or not title or not company or not snippet:
        return None
    metadata = (metadata_by_job_id or {}).get(job_id, {})
    post_age_text = _extract_raw(card_html, r'(\d+\+?\s+(?:day|days|hour|hours)\s+ago)')
    workplace_type = _coerce_workplace_type(location_text)
    return JobRecord(
        source=JobSource.INDEED,
        external_job_id=job_id,
        company=company,
        title=title,
        description=snippet,
        post_datetime=_parse_payload_job_datetime(metadata),
        link=link,
        salary_text=_extract_salary_text(card_html),
        location_text=location_text or None,
        workplace_type=workplace_type,
        post_age_text=post_age_text,
        post_age_days=_parse_post_age_days(post_age_text),
        collected_at=collected_at,
    )


def _extract_search_card_link(card_html: str) -> str | None:
    """Extract a canonical Indeed viewjob URL from one search result card."""
    raw_href = _extract_raw(card_html, r'<a[^>]*href="([^"]+)"')
    if not raw_href:
        return None
    return _canonicalize_indeed_job_link(raw_href)


def _extract_verified_search_card_job_id(card_html: str, link: str | None) -> str | None:
    """Extract a search-card job id only when it is backed by a real href-derived `jk`."""
    link_job_id = _extract_job_id_from_link(link or "")
    data_job_id = _extract_raw(card_html, r'data-jk="([A-Za-z0-9]+)"')
    dom_job_ids = _extract_search_card_dom_job_ids(card_html)
    if link_job_id and data_job_id and data_job_id != link_job_id:
        return None
    if link_job_id and dom_job_ids and any(dom_job_id != link_job_id for dom_job_id in dom_job_ids):
        return None
    return link_job_id


def _canonicalize_indeed_job_link(raw_href: str) -> str | None:
    """Return a canonical Indeed viewjob URL only when the href yields a plausible real job id."""
    absolute = urllib.parse.urljoin("https://www.indeed.com", html.unescape(raw_href))
    job_id = _extract_job_id_from_link(absolute)
    if not _looks_like_live_indeed_job_id(job_id):
        return None
    return f"https://www.indeed.com/viewjob?jk={job_id}"


def _looks_like_live_indeed_job_id(job_id: str | None) -> bool:
    """Return whether a live Indeed job id matches the stable hexadecimal `jk` shape."""
    if not job_id:
        return False
    return bool(re.fullmatch(r"[0-9a-f]{16}", job_id, flags=re.IGNORECASE))


def _extract_search_card_dom_job_ids(card_html: str) -> list[str]:
    """Extract DOM element ids that should agree with the live Indeed job key."""
    dom_ids: list[str] = []
    for pattern in (
        r'<a[^>]*id="job_([A-Za-z0-9]+)"',
        r'<span[^>]*id="jobTitle-([A-Za-z0-9]+)"',
    ):
        value = _extract_raw(card_html, pattern)
        if value:
            dom_ids.append(value)
    return dom_ids


def _extract_salary_from_auto_open_body(body: dict[str, Any]) -> str | None:
    """Extract a best-effort salary string from the auto-open viewjob payload."""
    salary_model = body.get("salaryInfoModel")
    if isinstance(salary_model, dict):
        for key in ("salaryText", "estimatedSalary", "formattedSalary"):
            value = salary_model.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _extract_job_from_detail_html(
    html: str,
    *,
    collected_at: datetime,
    fallback_link: str,
) -> JobRecord | None:
    """Extract one canonical Indeed job record from a detail page HTML payload."""
    posting = _extract_jobposting_jsonld(html)
    if posting:
        title = _get_path(posting, "title")
        company = _get_path(posting, "hiringOrganization.name")
        description = _html_to_text(_get_path(posting, "description") or "")
        link = _get_path(posting, "url") or fallback_link
        if not title or not company or not description or not link:
            return None
        post_datetime = parse_optional_datetime(_get_path(posting, "datePosted"))
        location_text = _extract_location_from_jsonld(posting)
        salary_text = _extract_salary_text_from_posting(posting)
        post_age_text = _extract_post_age_text(html)
        return JobRecord(
            source=JobSource.INDEED,
            external_job_id=_extract_job_id_from_link(str(link)),
            company=str(company),
            title=str(title),
            description=str(description),
            post_datetime=post_datetime,
            link=str(link),
            salary_text=salary_text,
            location_text=location_text,
            workplace_type=_extract_workplace_type(html),
            post_age_text=post_age_text,
            post_age_days=_parse_post_age_days(post_age_text),
            collected_at=collected_at,
        )

    title = _extract_text(html, r"<h1[^>]*jobsearch-JobInfoHeader-title[^>]*>(.*?)</h1>")
    company = _extract_text(html, r"data-company-name=\"true\"[^>]*>(.*?)</a>")
    if not company:
        company = _extract_text(html, r"jobsearch-InlineCompanyRating[^>]*>\s*<div[^>]*>(.*?)</div>")
    description_html = _extract_raw(
        html,
        r"<div[^>]*id=\"jobDescriptionText\"[^>]*>(.*?)</div>",
    )
    description = _html_to_text(description_html or "")
    location_text = _extract_text(html, r"jobsearch-JobInfoHeader-subtitle[^>]*>.*?<div[^>]*>(.*?)</div>.*?<div[^>]*>(.*?)</div>")
    if not location_text:
        location_text = _extract_text(html, r"data-testid=\"job-location\"[^>]*>(.*?)</div>")
    link = fallback_link
    post_age_text = _extract_post_age_text(html)
    if not title or not company or not description:
        return None
    return JobRecord(
        source=JobSource.INDEED,
        external_job_id=_extract_job_id_from_link(link),
        company=str(company),
        title=str(title),
        description=str(description),
        link=link,
        salary_text=_extract_text(html, r"salaryInfoAndJobType[^>]*>(.*?)</div>"),
        location_text=location_text,
        workplace_type=_extract_workplace_type(html),
        post_age_text=post_age_text,
        post_age_days=_parse_post_age_days(post_age_text),
        collected_at=collected_at,
    )


def _extract_openai_content(payload: dict[str, Any] | None) -> str:
    """Preserve module parity for future LLM fallback expansion."""
    if not payload:
        return ""
    return str(payload)


def _extract_text(html: str, pattern: str) -> str | None:
    """Extract and normalize text captured by one regex pattern."""
    raw = _extract_raw(html, pattern)
    return _html_to_text(raw) if raw is not None else None


def _extract_raw(html: str, pattern: str) -> str | None:
    """Extract the raw first regex capture group from HTML."""
    match = re.search(pattern, html, flags=re.DOTALL | re.IGNORECASE)
    if not match:
        return None
    if match.lastindex and match.lastindex > 1:
        return " ".join(group.strip() for group in match.groups() if group)
    return match.group(1).strip()


def _extract_jobposting_jsonld(html: str) -> dict[str, Any] | None:
    """Return the first JobPosting JSON-LD object found in the page."""
    matches = re.findall(
        r"<script[^>]*type=\"application/ld\+json\"[^>]*>(.*?)</script>",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    for raw in matches:
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            continue
        if isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict) and _is_jobposting(item):
                    return item
        if isinstance(obj, dict) and _is_jobposting(obj):
            return obj
    return None


def _is_jobposting(obj: dict[str, Any]) -> bool:
    """Return whether a JSON-LD object declares the JobPosting type."""
    value = obj.get("@type")
    if value == "JobPosting":
        return True
    if isinstance(value, list) and "JobPosting" in value:
        return True
    return False


def _get_path(obj: dict[str, Any], path: str) -> Any:
    """Traverse a dotted dict path and return the nested value when present."""
    cur: Any = obj
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _extract_location_from_jsonld(posting: dict[str, Any]) -> str | None:
    """Build a readable location string from Indeed JobPosting JSON-LD."""
    location = posting.get("jobLocation")
    if isinstance(location, list):
        location = location[0] if location else None
    if not isinstance(location, dict):
        return None
    address = location.get("address")
    if not isinstance(address, dict):
        return None
    parts = [
        str(address.get("addressLocality") or "").strip(),
        str(address.get("addressRegion") or "").strip(),
        str(address.get("addressCountry") or "").strip(),
    ]
    values = [part for part in parts if part]
    return ", ".join(values) if values else None


def _extract_post_age_text(html: str) -> str | None:
    """Extract the displayed relative posting age from a detail page."""
    return _extract_text(html, r"jobsearch-JobMetadataFooter[^>]*>(.*?)</div>")


def _extract_salary_text(html: str) -> str | None:
    """Extract a best-effort salary string from visible Indeed HTML."""
    return _extract_text(
        html,
        r"salaryInfoAndJobType[^>]*>(.*?)</div>",
    ) or _extract_text(
        html,
        r"Salary(?: Estimate)?[^<]*</span>\s*<span[^>]*>(.*?)</span>",
    )


def _extract_workplace_type(html: str) -> str | None:
    """Infer workplace type from the Indeed detail page body."""
    lowered = html.lower()
    if "remote" in lowered:
        return "remote"
    if "hybrid" in lowered:
        return "hybrid"
    if "on-site" in lowered or "onsite" in lowered or "in person" in lowered:
        return "onsite"
    return None


def _parse_post_age_days(value: str | None) -> int | None:
    """Convert a human-readable post age into a coarse day count."""
    if not value:
        return None
    normalized = re.sub(r"\s+", " ", value.strip().lower())
    if normalized in {"just posted", "today", "just now"}:
        return 0
    match = re.search(r"(\d+)\s+(minute|hour|day|week|month|year)s?\s+ago", normalized)
    if not match:
        return None
    count = int(match.group(1))
    unit = match.group(2)
    if unit in {"minute", "hour"}:
        return 0
    if unit == "day":
        return count
    if unit == "week":
        return count * 7
    if unit == "month":
        return count * 30
    if unit == "year":
        return count * 365
    return None


def _extract_salary_text_from_posting(posting: dict[str, Any]) -> str | None:
    """Extract the coarse salary string from JobPosting JSON-LD."""
    salary = posting.get("baseSalary")
    if not isinstance(salary, dict):
        return None
    value = salary.get("value")
    if not isinstance(value, dict):
        return None
    amount = value.get("value")
    currency = value.get("currency")
    unit = value.get("unitText")
    parts = []
    if amount is not None:
        parts.append(str(amount))
    if currency:
        parts.append(str(currency))
    if unit:
        parts.append(str(unit))
    return " ".join(parts) if parts else None


def _extract_job_id_from_link(link: str) -> str | None:
    """Extract the `jk` identifier from an Indeed job URL."""
    match = re.search(r"[?&]jk=([A-Za-z0-9]+)", link)
    return match.group(1) if match else None


def _html_to_text(value: str) -> str:
    """Collapse HTML markup into compact plain text."""
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"</p>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


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


__all__ = [
    "IndeedAcquisitionDiagnostics",
    "IndeedFilterPolicy",
    "IndeedFixtureSerializer",
    "IndeedJsonFileAdapter",
    "IndeedQueryBuilder",
    "IndeedScrapeAdapter",
    "parse_optional_datetime",
]
