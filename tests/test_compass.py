from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from opensignal_job_intel.compass import load_professional_compass

from tests.helpers import load_default_compass


class CompassTests(unittest.TestCase):
    def test_loads_professional_compass_from_json(self) -> None:
        compass = load_default_compass()
        self.assertTrue(compass.remote_only)
        self.assertEqual(6000, compass.min_monthly_usd)
        self.assertIn("AI Architect (hands-on)", compass.target_roles)
        self.assertIsNotNone(compass.search_max_post_age_days)
        self.assertIsInstance(compass.search_workplace_types, list)
        self.assertIsInstance(compass.search_regions, list)

    def test_defaults_optional_search_fields_when_search_block_is_missing(self) -> None:
        payload = {
            "summary_instruction": "summary",
            "required_output_fields": ["company"],
            "context_about_me": ["context"],
            "positioning": "positioning",
            "current_situation": ["current"],
            "target_roles": ["Data Architect"],
            "hard_filters": [],
            "compensation": {
                "min_monthly_usd": 5000,
                "target_monthly_usd_range": [5000, 9000],
            },
            "constraints": {
                "remote_only": True,
                "preferred_timezone_overlap": "americas",
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "compass.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            compass = load_professional_compass(path)

        self.assertIsNone(compass.search_max_post_age_days)
        self.assertIsNone(compass.search_workplace_types)
        self.assertIsNone(compass.search_regions)


if __name__ == "__main__":
    unittest.main()
