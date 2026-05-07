from __future__ import annotations

import runpy
import unittest
from pathlib import Path
from unittest.mock import patch


ENTRYPOINTS = [
    "harvest_status.py",
    "install_continuous_hourly_harvest_cron.py",
    "install_harvest_cron.py",
    "remove_harvest_cron.py",
    "remove_one_shot_harvest_cron.py",
    "run_harvest_cron.py",
    "schedule_harvest_next_minute.py",
    "show_recent_jobs.py",
    "tail_harvest_logs.py",
]


class SourceEntrypointSmokeTests(unittest.TestCase):
    def test_entrypoints_dispatch_to_run_script(self) -> None:
        sources_dir = Path("opensignal_job_intel/sources")
        for filename in ENTRYPOINTS:
            script_path = sources_dir / filename
            with self.subTest(filename=filename):
                with patch(
                    "opensignal_job_intel.sources.linkedin_harvest_ops.run_script",
                    return_value=17,
                ) as run_script:
                    with self.assertRaises(SystemExit) as exit_info:
                        runpy.run_path(str(script_path), run_name="__main__")
                self.assertEqual(17, exit_info.exception.code)
                run_script.assert_called_once()
                self.assertTrue(str(run_script.call_args.args[0]).endswith(filename))


if __name__ == "__main__":
    unittest.main()
