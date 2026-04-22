from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from opensignal_job_intel.models import JobRecord, JobSource


REQUIRED_CANONICAL_FIELDS = {"company", "title", "description", "link"}


@dataclass(slots=True)
class LinkedInExtractionSpec:
    version: int
    search_job_id_regex: str


def load_extraction_spec(path: str) -> LinkedInExtractionSpec:
    payload = json.loads(_read_text(path))
    spec = LinkedInExtractionSpec(
        version=int(payload.get("version", 1)),
        search_job_id_regex=str(payload.get("search", {}).get("job_id_regex", "")),
    )
    validate_extraction_spec(spec)
    return spec


def validate_extraction_spec(spec: LinkedInExtractionSpec) -> None:
    if spec.version != 1:
        raise ValueError(f"Unsupported extraction spec version: {spec.version}")
    if not spec.search_job_id_regex:
        raise ValueError("Extraction spec missing search.job_id_regex")
    try:
        re.compile(spec.search_job_id_regex)
    except re.error as exc:
        raise ValueError(f"Invalid search.job_id_regex: {exc}")


def extract_job_ids_from_search_html(html: str, spec: LinkedInExtractionSpec) -> list[str]:
    ids = re.findall(spec.search_job_id_regex, html)
    return sorted({str(value) for value in ids if str(value).isdigit()})


def extract_job_from_detail_html(
    html: str,
    collected_at: datetime,
    fallback_link: str | None = None,
) -> JobRecord | None:
    """Deterministic extraction from a LinkedIn job detail HTML page.

    Implementation intentionally leans on JSON-LD (`application/ld+json`) when present.
    """

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
            collected_at=collected_at,
        )

    # Guest-mode job detail pages often contain the full description but not JSON-LD.
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

    if not title or not company or not description or not link:
        return None

    return JobRecord(
        source=JobSource.LINKEDIN,
        external_job_id=external_job_id,
        company=str(company),
        title=str(title),
        description=str(description),
        link=str(link),
        collected_at=collected_at,
    )


def _extract_text(html: str, pattern: str) -> str | None:
    raw = _extract_raw(html, pattern)
    if raw is None:
        return None
    return _html_to_text(raw)


def _extract_raw(html: str, pattern: str) -> str | None:
    match = re.search(pattern, html, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else None


def _extract_attr(html: str, pattern: str) -> str | None:
    match = re.search(pattern, html, flags=re.IGNORECASE)
    return match.group(1).strip() if match else None


def _extract_job_id_from_link(link: str) -> str | None:
    match = re.search(r"/jobs/view/(?:[^/]*-)?(\d+)", link)
    return match.group(1) if match else None


def _extract_jobposting_jsonld(html: str) -> dict[str, Any] | None:
    # Grab all JSON-LD scripts and pick one that looks like a JobPosting.
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
        # Sometimes this is a list.
        if isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict) and _is_jobposting(item):
                    return item
        if isinstance(obj, dict) and _is_jobposting(obj):
            return obj
    return None


def _is_jobposting(obj: dict[str, Any]) -> bool:
    value = obj.get("@type")
    if value == "JobPosting":
        return True
    if isinstance(value, list) and "JobPosting" in value:
        return True
    return False


def _get_path(obj: dict[str, Any], path: str) -> Any:
    cur: Any = obj
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _parse_optional_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    # datePosted often comes as YYYY-MM-DD
    try:
        if len(value) == 10 and value[4] == "-":
            return datetime.fromisoformat(value)
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except Exception:
        return None


def _html_to_text(value: str) -> str:
    # Very small HTML-to-text; enough for storing readable descriptions.
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"</p>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _extract_salary_text(posting: dict[str, Any]) -> str | None:
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


def _read_text(path: str) -> str:
    from pathlib import Path

    return Path(path).read_text(encoding="utf-8")
