from __future__ import annotations

from datetime import time
from pathlib import Path

from opensignal_job_intel.compass import load_professional_compass
from opensignal_job_intel.models import HarvestSchedule, ProfessionalCompass


def load_default_compass() -> ProfessionalCompass:
    return load_professional_compass("profiles/professional_compass.template.json")


def make_harvest_schedule(*, log_path: str | Path, **overrides: object) -> HarvestSchedule:
    values: dict[str, object] = {
        "window_start": time(hour=0, minute=0),
        "window_end": time(hour=23, minute=59),
        "max_queries": 1,
        "max_pages_per_query": 1,
        "empty_search_pages_threshold": 3,
        "missing_signal_policy": "keep",
        "base_delay_seconds": 0.0,
        "jitter_seconds": 0.0,
        "sticky_caution_multiplier": 2.0,
        "backoff_initial_seconds": 0.0,
        "backoff_multiplier": 2.0,
        "backoff_max_seconds": 0.0,
        "summary_every_requests": 100,
        "log_path": str(log_path),
    }
    values.update(overrides)
    return HarvestSchedule(**values)
