from __future__ import annotations

import json
from pathlib import Path

from opensignal_job_intel.models import ProfessionalCompass


def load_professional_compass(path: str | Path) -> ProfessionalCompass:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
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
    )
