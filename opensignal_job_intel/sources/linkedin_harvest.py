from __future__ import annotations

import json
import os
import random
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, time as time_of_day
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode

import yaml

from opensignal_job_intel.llm import LocalLlmClient
from opensignal_job_intel.models import (
    HarvestQueryState,
    HarvestRunState,
    HarvestSchedule,
    JobRecord,
    JobSource,
    ProfessionalCompass,
    utc_now,
)
from opensignal_job_intel.repositories.sqlite_jobs import SQLiteJobRepository
from opensignal_job_intel.sources.linkedin_acquire import (
    _derive_region,
    _normalize_str_list,
    _ssl_context,
)
from opensignal_job_intel.sources.linkedin_extraction import (
    extract_job_from_detail_html,
    extract_job_ids_from_search_html,
    load_extraction_spec,
)


DEFAULT_SCHEDULE_PATH = "config/extraction_schedule.template.yaml"
LOCAL_SCHEDULE_OVERRIDE_PATH = "config/extraction_schedule.yaml"
HARVEST_SOURCE = JobSource.LINKEDIN.value


@dataclass(slots=True)
class FetchResponse:
    url: str
    kind: str
    text: str | None
    status_code: int | None = None
    error: str | None = None


@dataclass(slots=True)
class HarvestResult:
    queries_processed: int = 0
    search_pages: int = 0
    detail_pages: int = 0
    requests: int = 0
    stored: int = 0
    skipped_known_ids: int = 0
    dropped_filtered: int = 0
    dropped_parse_failures: int = 0
    stale_stream_stops: int = 0
    throttles: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "queries_processed": self.queries_processed,
            "search_pages": self.search_pages,
            "detail_pages": self.detail_pages,
            "requests": self.requests,
            "stored": self.stored,
            "skipped_known_ids": self.skipped_known_ids,
            "dropped_filtered": self.dropped_filtered,
            "dropped_parse_failures": self.dropped_parse_failures,
            "stale_stream_stops": self.stale_stream_stops,
            "throttles": self.throttles,
        }


@dataclass(slots=True)
class JobFetchOutcome:
    job: JobRecord | None
    throttled: bool = False


@dataclass(slots=True)
class HarvestSearchPlan:
    query: str
    location: str | None = None

    @property
    def key(self) -> str:
        return f"{self.query}::{self.location or ''}"


@dataclass(slots=True)
class FilterDecision:
    allowed: bool
    reason: str | None = None


class HarvestLogger:
    def __init__(self, file_path: str | Path) -> None:
        self._file_path = Path(file_path)
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, message: str) -> None:
        line = f"{datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S')} {message}"
        print(line)
        with self._file_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


class LinkedInNightlyHarvester:
    def __init__(
        self,
        *,
        compass: ProfessionalCompass,
        repository: SQLiteJobRepository,
        extraction_spec_path: str,
        schedule: HarvestSchedule,
        capture_dir: str | None = None,
        max_jobs: int | None = None,
        fetcher: Callable[[str, str], FetchResponse] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._compass = compass
        self._repository = repository
        self._spec = load_extraction_spec(extraction_spec_path)
        self._schedule = schedule
        self._capture_dir = Path(capture_dir) if capture_dir else None
        self._max_jobs = max_jobs
        self._fetcher = fetcher or self._fetch_text
        self._sleep = sleep
        self._cookies = os.environ.get("LINKEDIN_COOKIES")
        self._csrf = os.environ.get("LINKEDIN_CSRF")
        llm_url = os.environ.get("LOCAL_LLM_BASE_URL")
        self._llm = LocalLlmClient(llm_url) if llm_url else None
        self._logger = HarvestLogger(schedule.log_path)
        self._run_state = repository.get_harvest_run_state(HARVEST_SOURCE)
        self._result = HarvestResult()

    def run(self) -> HarvestResult:
        queries = _derive_search_plans(self._compass, limit=self._schedule.max_queries)
        self._logger.log(
            f"harvest start query_count={len(queries)} window={self._schedule.window_start.strftime('%H:%M')}-{self._schedule.window_end.strftime('%H:%M')}"
        )
        if not self._within_window():
            self._logger.log("harvest skipped current time is outside configured window")
            return self._result

        for query in queries:
            if not self._within_window() or self._hit_max_jobs():
                break
            self._result.queries_processed += 1
            self._run_query(query)

        self._repository.save_harvest_run_state(self._run_state)
        self._logger.log("harvest complete " + json.dumps(self._result.as_dict(), ensure_ascii=True))
        return self._result

    def _run_query(self, plan: HarvestSearchPlan) -> None:
        state = self._repository.get_harvest_query_state(HARVEST_SOURCE, plan.key)
        self._logger.log(
            f"query start query={json.dumps(plan.query)} location={json.dumps(plan.location)} next_start={state.next_start} empty_pages={state.consecutive_empty_pages} yielded_new_ids={state.yielded_new_ids}"
        )
        pages_seen = 0
        while self._within_window() and not self._hit_max_jobs():
            if pages_seen >= self._schedule.max_pages_per_query:
                self._logger.log(
                    f"query stop query={json.dumps(plan.query)} location={json.dumps(plan.location)} reason=max_pages limit={self._schedule.max_pages_per_query}"
                )
                break
            url = _build_harvest_search_url(plan, state.next_start, self._compass)
            search = self._request(url, kind="search")
            if search.status_code == 403:
                self._handle_throttle()
                self._repository.save_harvest_query_state(state)
                if not self._within_window():
                    break
                continue
            if not search.text:
                self._repository.save_harvest_query_state(state)
                break

            pages_seen += 1
            self._result.search_pages += 1
            job_ids = extract_job_ids_from_search_html(search.text, self._spec)
            known_ids = self._repository.existing_external_job_ids(JobSource.LINKEDIN, job_ids)
            new_ids = [job_id for job_id in job_ids if job_id not in known_ids]
            self._result.skipped_known_ids += len(known_ids)
            state.yielded_new_ids += len(new_ids)
            if new_ids:
                state.consecutive_empty_pages = 0
            else:
                state.consecutive_empty_pages += 1

            stale_results = self._search_page_has_stale_results(search.text)
            state.saw_stale_results = state.saw_stale_results or stale_results
            self._logger.log(
                f"search page query={json.dumps(plan.query)} location={json.dumps(plan.location)} start={state.next_start} ids={len(job_ids)} new_ids={len(new_ids)} known_ids={len(known_ids)} stale_results={str(stale_results).lower()}"
            )
            if state.consecutive_empty_pages >= self._schedule.empty_search_pages_threshold:
                self._result.stale_stream_stops += 1
                reason = "stale_stream" if state.saw_stale_results else "no_new_ids_exhausted"
                self._logger.log(
                    f"query stop query={json.dumps(plan.query)} location={json.dumps(plan.location)} reason={reason} empty_pages={state.consecutive_empty_pages}"
                )
                state.next_start += 25
                self._repository.save_harvest_query_state(state)
                break

            collected_at = utc_now()
            for job_id in new_ids:
                if not self._within_window() or self._hit_max_jobs():
                    break
                outcome = self._fetch_and_extract_job(job_id, collected_at)
                if outcome.throttled:
                    self._repository.save_harvest_query_state(state)
                    self._repository.save_harvest_run_state(self._run_state)
                    return
                job = outcome.job
                if job is None:
                    continue
                decision = _evaluate_harvest_filters(
                    job,
                    max_post_age_days=self._compass.search_max_post_age_days,
                    allowed_workplace_types=_normalize_str_list(self._compass.search_workplace_types),
                    allowed_regions=_normalize_region_values(self._compass.search_regions),
                    missing_signal_policy=self._schedule.missing_signal_policy,
                )
                if not decision.allowed:
                    self._result.dropped_filtered += 1
                    derived_region = _derive_region(job.location_text) if job.location_text else None
                    self._logger.log(
                        f"detail dropped job_id={job_id} reason={decision.reason} location={json.dumps(job.location_text)} derived_region={json.dumps(derived_region)} workplace={json.dumps(job.workplace_type)} age_days={json.dumps(job.post_age_days)} max_age_days={json.dumps(self._compass.search_max_post_age_days)} allowed_regions={json.dumps(_normalize_region_values(self._compass.search_regions))} allowed_workplace_types={json.dumps(_normalize_str_list(self._compass.search_workplace_types))}"
                    )
                    continue
                self._repository.upsert_job(job.normalized())
                self._run_state.last_success_at = utc_now()
                state.last_success_at = self._run_state.last_success_at
                self._result.stored += 1
                self._logger.log(
                    f"detail stored job_id={job_id} company={json.dumps(job.company)} title={json.dumps(job.title)}"
                )

            state.next_start += 25
            self._repository.save_harvest_query_state(state)
            self._repository.save_harvest_run_state(self._run_state)
            self._maybe_log_summary()

    def _fetch_and_extract_job(self, job_id: str, collected_at: datetime) -> JobFetchOutcome:
        link = f"https://www.linkedin.com/jobs/view/{job_id}/"
        detail = self._request(link, kind="job")
        if detail.status_code == 403:
            self._handle_throttle()
            return JobFetchOutcome(job=None, throttled=True)
        if not detail.text:
            return JobFetchOutcome(job=None)
        self._result.detail_pages += 1
        job = extract_job_from_detail_html(detail.text, collected_at=collected_at, fallback_link=link)
        if job is not None:
            return JobFetchOutcome(job=job)
        job = self._llm_fallback_extract(detail.text, collected_at=collected_at, fallback_link=link)
        if job is None:
            self._result.dropped_parse_failures += 1
            self._logger.log(f"detail dropped job_id={job_id} reason=parse_failed")
            if self._capture_dir:
                _write_capture(self._capture_dir, f"job_{job_id}.html", detail.text)
        return JobFetchOutcome(job=job)

    def _request(self, url: str, kind: str) -> FetchResponse:
        self._apply_pacing_delay()
        response = self._fetcher(url, kind)
        self._result.requests += 1
        if response.text is not None:
            self._logger.log(f"request ok kind={kind} url={json.dumps(url)}")
        else:
            self._logger.log(
                f"request error kind={kind} status={json.dumps(response.status_code)} url={json.dumps(url)} error={json.dumps(response.error)}"
            )
        return response

    def _fetch_text(self, url: str, kind: str) -> FetchResponse:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; opensignal-job-intel/1.0)",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if self._cookies:
            headers["Cookie"] = self._cookies
        if self._csrf:
            headers["csrf-token"] = self._csrf

        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=30, context=_ssl_context()) as response:
                text = response.read().decode("utf-8", errors="replace")
                if self._capture_dir and kind == "search":
                    safe = urllib.parse.quote_plus(url)[:120]
                    _write_capture(self._capture_dir, f"search_{safe}.html", text)
                return FetchResponse(url=url, kind=kind, text=text, status_code=response.status)
        except urllib.error.HTTPError as exc:
            return FetchResponse(
                url=url,
                kind=kind,
                text=None,
                status_code=exc.code,
                error=f"http_{exc.code}",
            )
        except ssl.SSLCertVerificationError as exc:
            return FetchResponse(url=url, kind=kind, text=None, error=f"ssl_verify_failed:{exc}")
        except urllib.error.URLError as exc:
            return FetchResponse(url=url, kind=kind, text=None, error=f"url_error:{exc}")

    def _apply_pacing_delay(self) -> None:
        delay = self._schedule.base_delay_seconds + random.uniform(0, self._schedule.jitter_seconds)
        if self._run_state.sticky_caution_enabled:
            delay *= self._schedule.sticky_caution_multiplier
        if delay > 0:
            self._sleep(delay)

    def _handle_throttle(self) -> None:
        self._run_state.throttle_events += 1
        self._run_state.sticky_caution_enabled = True
        self._run_state.last_throttle_at = utc_now()
        if self._run_state.current_backoff_seconds <= 0:
            self._run_state.current_backoff_seconds = self._schedule.backoff_initial_seconds
        else:
            self._run_state.current_backoff_seconds = min(
                self._run_state.current_backoff_seconds * self._schedule.backoff_multiplier,
                self._schedule.backoff_max_seconds,
            )
        self._result.throttles += 1
        self._logger.log(
            f"throttle 403 backoff_seconds={self._run_state.current_backoff_seconds:.1f} throttle_events={self._run_state.throttle_events}"
        )
        if self._within_window_after(self._run_state.current_backoff_seconds):
            self._sleep(self._run_state.current_backoff_seconds)
        self._repository.save_harvest_run_state(self._run_state)

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
        result = self._llm.extract_json(system_prompt=system, user_prompt=user + html[:30000])
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
        return JobRecord(
            source=JobSource.LINKEDIN,
            external_job_id=str(external_job_id).strip() if external_job_id else None,
            company=company,
            title=title,
            description=description,
            link=link,
            collected_at=collected_at,
        )

    def _search_page_has_stale_results(self, html: str) -> bool:
        max_age_days = self._compass.search_max_post_age_days
        if max_age_days is None:
            return False
        for value in _extract_relative_age_texts(html):
            age_days = _parse_post_age_days(value)
            if age_days is not None and age_days > max_age_days:
                return True
        return False

    def _maybe_log_summary(self) -> None:
        every = self._schedule.summary_every_requests
        if every <= 0 or self._result.requests == 0 or self._result.requests % every != 0:
            return
        self._logger.log("summary " + json.dumps(self._result.as_dict(), ensure_ascii=True))

    def _within_window(self) -> bool:
        return _time_within_window(
            datetime.now().astimezone().time(),
            self._schedule.window_start,
            self._schedule.window_end,
        )

    def _within_window_after(self, delay_seconds: float) -> bool:
        future = datetime.fromtimestamp(
            datetime.now().astimezone().timestamp() + delay_seconds
        ).astimezone()
        return _time_within_window(
            future.time(), self._schedule.window_start, self._schedule.window_end
        )

    def _hit_max_jobs(self) -> bool:
        return self._max_jobs is not None and self._result.stored >= self._max_jobs


def load_harvest_schedule(path: str | Path) -> HarvestSchedule:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    window = payload.get("window") or {}
    search = payload.get("search") or {}
    pacing = payload.get("pacing") or {}
    backoff = payload.get("backoff") or {}
    progress = payload.get("progress") or {}
    logging = payload.get("logging") or {}
    return HarvestSchedule(
        window_start=_parse_clock(window.get("start", "00:00")),
        window_end=_parse_clock(window.get("end", "08:00")),
        max_queries=int(search.get("max_queries", 6)),
        max_pages_per_query=int(search.get("max_pages_per_query", 200)),
        empty_search_pages_threshold=int(search.get("empty_search_pages_threshold", 5)),
        missing_signal_policy=str(search.get("missing_signal_policy", "keep")).strip().lower(),
        base_delay_seconds=float(pacing.get("base_delay_seconds", 2.0)),
        jitter_seconds=float(pacing.get("jitter_seconds", 1.0)),
        sticky_caution_multiplier=float(pacing.get("sticky_caution_multiplier", 2.0)),
        backoff_initial_seconds=float(backoff.get("initial_delay_seconds", 60.0)),
        backoff_multiplier=float(backoff.get("multiplier", 2.0)),
        backoff_max_seconds=float(backoff.get("max_delay_seconds", 14400.0)),
        summary_every_requests=int(progress.get("summary_every_requests", 25)),
        log_path=str(logging.get("file_path", "data/harvest-linkedin.log")),
    )


def resolve_harvest_schedule_path(path: str | None) -> str:
    if path:
        return path
    local = Path(LOCAL_SCHEDULE_OVERRIDE_PATH)
    if local.exists():
        return str(local)
    return DEFAULT_SCHEDULE_PATH


def _evaluate_harvest_filters(
    job: JobRecord,
    *,
    max_post_age_days: int | None,
    allowed_workplace_types: list[str] | None,
    allowed_regions: list[str] | None,
    missing_signal_policy: str,
) -> FilterDecision:
    if max_post_age_days is not None:
        if job.post_age_days is None:
            if missing_signal_policy == "drop":
                return FilterDecision(False, "missing_age")
        elif job.post_age_days > max_post_age_days:
            return FilterDecision(False, "age_exceeds_limit")

    if allowed_workplace_types is not None:
        if job.workplace_type is None:
            if missing_signal_policy == "drop":
                return FilterDecision(False, "missing_workplace_type")
        elif job.workplace_type.strip().lower() not in allowed_workplace_types:
            return FilterDecision(False, "workplace_not_allowed")

    if allowed_regions is not None:
        if not job.location_text:
            if missing_signal_policy == "drop":
                return FilterDecision(False, "missing_location")
        else:
            region = _derive_region(job.location_text)
            if region is None:
                if missing_signal_policy == "drop":
                    return FilterDecision(False, "unknown_region")
            elif region.lower() not in allowed_regions:
                return FilterDecision(False, "region_not_allowed")
    return FilterDecision(True)


def _derive_search_plans(
    compass: ProfessionalCompass, limit: int
) -> list[HarvestSearchPlan]:
    roles = [role.strip() for role in compass.target_roles if role.strip()]
    deduped_roles = list(dict.fromkeys(roles))
    locations = _derive_location_labels(compass.search_regions)
    plans: list[HarvestSearchPlan] = []
    for role in deduped_roles:
        query = role
        if compass.remote_only and "remote" not in query.lower():
            query = f"{query} remote"
        if not locations:
            plans.append(HarvestSearchPlan(query=query, location=None))
        else:
            for location in locations:
                plans.append(HarvestSearchPlan(query=query, location=location))
        if len(plans) >= limit:
            break
    return plans[:limit]


def _derive_location_labels(regions: list[str] | None) -> list[str]:
    normalized = _normalize_region_values(regions)
    if not normalized:
        return []
    labels: list[str] = []
    for region in normalized:
        if region == "latam":
            labels.append("Latin America")
        elif region == "ca":
            labels.append("Canada")
        elif region == "ar":
            labels.append("Argentina")
        elif region == "us":
            labels.append("United States")
        elif region == "emea":
            labels.append("Europe, Middle East, and Africa")
        else:
            labels.append(region)
    return list(dict.fromkeys(labels))


def _normalize_region_values(regions: list[str] | None) -> list[str] | None:
    normalized = _normalize_str_list(regions)
    if normalized is None:
        return None
    aliases = {
        "canada": "ca",
    }
    return [aliases.get(region, region) for region in normalized]


def _build_harvest_search_url(
    plan: HarvestSearchPlan, start: int, compass: ProfessionalCompass
) -> str:
    params = {
        "keywords": plan.query,
        "start": str(start),
    }
    if plan.location:
        params["location"] = plan.location
    if compass.search_max_post_age_days is not None and compass.search_max_post_age_days > 0:
        params["f_TPR"] = f"r{compass.search_max_post_age_days * 24 * 60 * 60}"
    return "https://www.linkedin.com/jobs/search/?" + urlencode(params)


def _extract_relative_age_texts(html: str) -> list[str]:
    import re

    matches = re.findall(
        r"(just now|today|\d+\s+(?:minute|hour|day|week|month|year)s?\s+ago)",
        html,
        flags=re.IGNORECASE,
    )
    return [match.strip() for match in matches]


def _parse_post_age_days(value: str | None) -> int | None:
    import re

    if not value:
        return None
    normalized = re.sub(r"\s+", " ", value.strip().lower())
    if normalized in {"just now", "today"}:
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


def _parse_clock(value: str) -> time_of_day:
    try:
        hour, minute = [int(part) for part in str(value).split(":", 1)]
    except Exception as exc:  # pragma: no cover - defensive parse error path
        raise ValueError(f"Invalid clock value: {value}") from exc
    return time_of_day(hour=hour, minute=minute)


def _time_within_window(now: time_of_day, start: time_of_day, end: time_of_day) -> bool:
    if start <= end:
        return start <= now < end
    return now >= start or now < end


def _write_capture(dir_path: Path, name: str, content: str) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / name).write_text(content, encoding="utf-8")
