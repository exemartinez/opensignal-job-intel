from __future__ import annotations

import re
from dataclasses import asdict

from opensignal_job_intel.models import JobEvaluation, JobRecord, ProfessionalCompass

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
    def __init__(self, compass: ProfessionalCompass) -> None:
        self._compass = compass

    def evaluate(self, job: JobRecord) -> JobEvaluation:
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
        return asdict(evaluation)

    def _extract_techs(self, job: JobRecord) -> list[str]:
        haystack = f"{job.title} {job.description}".lower()
        found = [keyword.upper() if keyword == "llm" else keyword.title() for keyword in TECH_KEYWORDS if keyword in haystack]
        return sorted(dict.fromkeys(found))

    def _classify_responsibility(self, job: JobRecord) -> str:
        haystack = f"{job.title} {job.description}".lower()
        if any(term in haystack for term in ("manager", "head of", "director", "people management")):
            return "manager"
        if any(term in haystack for term in ("lead", "principal", "staff", "tech lead")):
            return "lead"
        if "senior" in haystack:
            return "senior"
        if any(term in haystack for term in ("architect", "engineer", "scientist", "individual contributor", "hands-on")):
            return "ic"
        return "unknown"

    def _classify_company_type(self, job: JobRecord) -> str:
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
        tech_summary = ", ".join(techs[:4]) if techs else "general data stack"
        sentence = (
            f"{job.title} at {job.company}: {responsibility_level} role in a "
            f"{company_type} context focused on {tech_summary} and production data or AI systems."
        )
        return sentence[:240]
