from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from src.runtime_entrypoints import RuntimeEntrypoints


class SourceEntrypointSmokeTests(unittest.TestCase):
    def test_runtime_commands_delegate_to_harvest_cron_scripts(self) -> None:
        commands = [
            "harvest-status",
            "install-continuous-hourly-harvest-cron",
            "install-harvest-cron",
            "remove-harvest-cron",
            "remove-one-shot-harvest-cron",
            "run-harvest-cron",
            "schedule-harvest-next-minute",
            "show-recent-jobs",
            "tail-harvest-logs",
        ]
        for command in commands:
            with self.subTest(command=command):
                with patch("src.runtime_entrypoints.HarvestCronScripts") as scripts_cls:
                    scripts_cls.return_value.run.return_value = 17
                    result = RuntimeEntrypoints.main(
                        [command] if command != "show-recent-jobs" else [command, "25"]
                    )
                self.assertEqual(17, result)
                scripts_cls.assert_called_once_with(Path("src/runtime_entrypoints.py").resolve())


if __name__ == "__main__":
    unittest.main()
