from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
