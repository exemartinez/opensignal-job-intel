"""LinkedIn extraction, fallback extraction, and filtering helpers.

Author: Ezequiel H. Martinez
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.core_domain_inputs import JobRecord, JobSource

REQUIRED_CANONICAL_FIELDS = {"company", "title", "description", "link"}


@dataclass(slots=True)
class LlmJsonResult:
    """Represent the success or failure of one LLM JSON extraction call."""

    ok: bool
    data: dict[str, Any] | None
    error: str | None


class LocalLlmClient:
    """Very small HTTP client for a locally running LLM server."""

    def __init__(
        self,
        base_url: str,
        model: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        """Bind the local LLM endpoint, model, and request timeout."""
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds

    def extract_json(self, system_prompt: str, user_prompt: str) -> LlmJsonResult:
        """Try chat and completion endpoints until one yields JSON text."""
        chat_url = f"{self._base_url}/v1/chat/completions"
        payload: dict[str, Any] = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
        }
        if self._model:
            payload["model"] = self._model
        chat = self._post_json(chat_url, payload)
        if chat.ok:
            return _parse_json_from_text(_extract_openai_content(chat.data))
        completion_url = f"{self._base_url}/completion"
        payload2: dict[str, Any] = {
            "prompt": f"{system_prompt}\n\n{user_prompt}",
            "temperature": 0,
        }
        completion = self._post_json(completion_url, payload2)
        if completion.ok:
            text = (completion.data or {}).get("content") or ""
            return _parse_json_from_text(str(text))
        return LlmJsonResult(ok=False, data=None, error=chat.error or completion.error)

    def _post_json(self, url: str, payload: dict[str, Any]) -> LlmJsonResult:
        """POST JSON to the local LLM endpoint and decode the response."""
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return LlmJsonResult(ok=True, data=data, error=None)
        except urllib.error.HTTPError as exc:
            return LlmJsonResult(
                ok=False,
                data=None,
                error=f"HTTP {exc.code} calling LLM endpoint {url}",
            )
        except urllib.error.URLError as exc:
            return LlmJsonResult(
                ok=False,
                data=None,
                error=f"Failed to reach LLM endpoint {url}: {exc}",
            )
        except Exception as exc:  # pragma: no cover
            return LlmJsonResult(ok=False, data=None, error=str(exc))


class LinkedInFallbackExtractor:
    """Perform LLM-based fallback extraction from LinkedIn detail HTML."""

    def __init__(self, client: LocalLlmClient | None) -> None:
        """Bind the optional local LLM client used for fallback parsing."""
        self._client = client

    def extract(
        self, html: str, collected_at: datetime, fallback_link: str
    ) -> JobRecord | None:
        """Recover a canonical job record from HTML through the local LLM."""
        if not self._client:
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
        result = self._client.extract_json(system_prompt=system, user_prompt=user + html[:30000])
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


@dataclass(slots=True)
class LinkedInExtractionSpec:
    """Hold the deterministic extraction configuration for LinkedIn HTML."""

    version: int
    search_job_id_regex: str


class LinkedInExtractionService:
    """Provide deterministic extraction operations for LinkedIn HTML."""

    def __init__(self, spec: LinkedInExtractionSpec) -> None:
        """Bind the deterministic extraction spec."""
        self._spec = spec

    def extract_job_ids_from_search_html(self, html: str) -> list[str]:
        """Extract distinct LinkedIn job ids from one search page."""
        ids = re.findall(self._spec.search_job_id_regex, html)
        return sorted({str(value) for value in ids if str(value).isdigit()})

    def extract_job_from_detail_html(
        self,
        html: str,
        collected_at: datetime,
        fallback_link: str | None = None,
    ) -> JobRecord | None:
        """Extract one canonical job record from a detail page HTML payload."""
        posting = _extract_jobposting_jsonld(html)
        if posting:
            title = _get_path(posting, "title")
            company = _get_path(posting, "hiringOrganization.name")
            description = _html_to_text(_get_path(posting, "description") or "")
            link = _get_path(posting, "url") or fallback_link
            if not title or not company or not description or not link:
                return None
            external_job_id = (
                _get_path(posting, "identifier.value")
                or _get_path(posting, "identifier")
                or None
            )
            post_datetime = _parse_optional_datetime(_get_path(posting, "datePosted"))
            salary_text = _extract_salary_text(posting)
            return JobRecord(
                source=JobSource.LINKEDIN,
                external_job_id=str(external_job_id) if external_job_id else None,
                company=str(company),
                title=str(title),
                description=str(description),
                post_datetime=post_datetime,
                link=str(link),
                salary_text=salary_text,
                location_text=_extract_location_text(html),
                workplace_type=_extract_workplace_type(html),
                post_age_text=_extract_post_age_text(html),
                post_age_days=_parse_post_age_days(_extract_post_age_text(html)),
                collected_at=collected_at,
            )

        title = _extract_text(html, r"<h1[^>]*topcard__title[^>]*>(.*?)</h1>")
        company = _extract_text(html, r"topcard__org-name-link[^>]*>(.*?)</a>")
        description_html = _extract_raw(
            html,
            r"<div class=\"show-more-less-html__markup[^\"]*\"[^>]*>(.*?)</div>",
        )
        description = _html_to_text(description_html or "")
        link = (
            _extract_attr(html, r'<meta property="lnkd:url" content="([^"]+)"')
            or _extract_attr(html, r'<link rel="canonical" href="([^"]+)"')
            or fallback_link
        )
        external_job_id = _extract_job_id_from_link(link) if link else None
        location_text = _extract_location_text(html)
        workplace_type = _extract_workplace_type(html)
        post_age_text = _extract_post_age_text(html)
        post_age_days = _parse_post_age_days(post_age_text)
        if not title or not company or not description or not link:
            return None
        return JobRecord(
            source=JobSource.LINKEDIN,
            external_job_id=external_job_id,
            company=str(company),
            title=str(title),
            description=str(description),
            link=str(link),
            location_text=location_text,
            workplace_type=workplace_type,
            post_age_text=post_age_text,
            post_age_days=post_age_days,
            collected_at=collected_at,
        )


class LinkedInFilterEvaluator:
    """Evaluate best-effort LinkedIn filter conditions on canonical jobs."""

    @staticmethod
    def parse_post_age_days(value: str | None) -> int | None:
        """Parse a relative-age string into coarse day count."""
        return _parse_post_age_days(value)

    @staticmethod
    def derive_region(location_text: str) -> str | None:
        """Map a free-form location string into the normalized region bucket."""
        value = location_text.strip().lower()
        if not value:
            return None
        if "united states" in value or value.endswith(", us") or value.endswith(", usa"):
            return "us"
        if "canada" in value or value.endswith(", ca"):
            return "ca"
        if "argentina" in value or value.endswith(", ar"):
            return "ar"
        latam = [
            "mexico",
            "brazil",
            "chile",
            "colombia",
            "peru",
            "uruguay",
            "paraguay",
            "bolivia",
            "ecuador",
            "venezuela",
            "costa rica",
            "panama",
            "guatemala",
            "el salvador",
            "honduras",
            "nicaragua",
            "dominican republic",
            "latin america",
        ]
        if any(country in value for country in latam):
            return "latam"
        emea = [
            "united kingdom",
            "uk",
            "ireland",
            "germany",
            "france",
            "spain",
            "portugal",
            "italy",
            "netherlands",
            "sweden",
            "norway",
            "denmark",
            "finland",
            "poland",
            "switzerland",
            "austria",
            "belgium",
        ]
        if any(country in value for country in emea):
            return "emea"
        return None


def load_extraction_spec(path: str) -> LinkedInExtractionSpec:
    """Load and validate the LinkedIn extraction spec JSON file."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    spec = LinkedInExtractionSpec(
        version=int(payload.get("version", 1)),
        search_job_id_regex=str(payload.get("search", {}).get("job_id_regex", "")),
    )
    validate_extraction_spec(spec)
    return spec


def validate_extraction_spec(spec: LinkedInExtractionSpec) -> None:
    """Reject extraction specs that the deterministic parser cannot use."""
    if spec.version != 1:
        raise ValueError(f"Unsupported extraction spec version: {spec.version}")
    if not spec.search_job_id_regex:
        raise ValueError("Extraction spec missing search.job_id_regex")
    try:
        re.compile(spec.search_job_id_regex)
    except re.error as exc:
        raise ValueError(f"Invalid search.job_id_regex: {exc}")


def extract_job_ids_from_search_html(html: str, spec: LinkedInExtractionSpec) -> list[str]:
    """Convenience wrapper for deterministic search-page id extraction."""
    return LinkedInExtractionService(spec).extract_job_ids_from_search_html(html)


def extract_job_from_detail_html(
    html: str,
    collected_at: datetime,
    fallback_link: str | None = None,
) -> JobRecord | None:
    """Convenience wrapper for deterministic detail-page extraction."""
    spec = LinkedInExtractionSpec(version=1, search_job_id_regex=r"\d+")
    return LinkedInExtractionService(spec).extract_job_from_detail_html(
        html, collected_at=collected_at, fallback_link=fallback_link
    )


def _extract_openai_content(payload: dict[str, Any] | None) -> str:
    """Pull the message content field from an OpenAI-style response body."""
    if not payload:
        return ""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return str(content) if content is not None else ""


def _parse_json_from_text(text: str) -> LlmJsonResult:
    """Parse the first JSON object found inside arbitrary model output."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return LlmJsonResult(ok=False, data=None, error="LLM did not return JSON")
    snippet = text[start : end + 1]
    try:
        return LlmJsonResult(ok=True, data=json.loads(snippet), error=None)
    except Exception as exc:
        return LlmJsonResult(ok=False, data=None, error=f"Invalid JSON from LLM: {exc}")


def _extract_text(html: str, pattern: str) -> str | None:
    """Extract and normalize text captured by one regex pattern."""
    raw = _extract_raw(html, pattern)
    return _html_to_text(raw) if raw is not None else None


def _extract_raw(html: str, pattern: str) -> str | None:
    """Extract the raw first regex capture group from HTML."""
    match = re.search(pattern, html, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else None


def _extract_attr(html: str, pattern: str) -> str | None:
    """Extract one HTML attribute value through a regex capture group."""
    match = re.search(pattern, html, flags=re.IGNORECASE)
    return match.group(1).strip() if match else None


def _extract_job_id_from_link(link: str) -> str | None:
    """Extract the numeric LinkedIn job id from a canonical job URL."""
    match = re.search(r"/jobs/view/(?:[^/]*-)?(\d+)", link)
    return match.group(1) if match else None


def _extract_location_text(html: str) -> str | None:
    """Extract the displayed location text from a detail page."""
    return _extract_text(html, r"<span[^>]*topcard__flavor--bullet[^>]*>(.*?)</span>")


def _extract_post_age_text(html: str) -> str | None:
    """Extract the displayed relative posting age from a detail page."""
    return _extract_text(html, r"<span[^>]*posted-time-ago__text[^>]*>(.*?)</span>")


def _extract_workplace_type(html: str) -> str | None:
    """Infer workplace type from the detail page body."""
    lowered = html.lower()
    if "workplace type" in lowered:
        value = _extract_text(html, r"Workplace type\s*</h3>\s*<span[^>]*>(.*?)</span>")
        if value:
            return value.lower()
    if "remote" in lowered:
        return "remote"
    if "hybrid" in lowered:
        return "hybrid"
    if "on-site" in lowered or "onsite" in lowered:
        return "onsite"
    return None


def _parse_post_age_days(value: str | None) -> int | None:
    """Convert a human-readable post age into a coarse day count."""
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


def _parse_optional_datetime(value: str | None) -> datetime | None:
    """Parse an ISO-like datetime or date value when present."""
    if not value:
        return None
    try:
        if len(value) == 10 and value[4] == "-":
            return datetime.fromisoformat(value)
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except Exception:
        return None


def _html_to_text(value: str) -> str:
    """Collapse HTML markup into compact plain text."""
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"</p>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _extract_salary_text(posting: dict[str, Any]) -> str | None:
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


__all__ = [
    "LlmJsonResult",
    "LinkedInExtractionSpec",
    "LinkedInExtractionService",
    "LinkedInFallbackExtractor",
    "LinkedInFilterEvaluator",
    "LocalLlmClient",
    "extract_job_from_detail_html",
    "extract_job_ids_from_search_html",
    "load_extraction_spec",
    "validate_extraction_spec",
]
