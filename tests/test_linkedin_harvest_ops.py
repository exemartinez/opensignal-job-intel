from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from opensignal_job_intel.sources import linkedin_harvest_ops as ops


class FakeCrontabManager:
    def __init__(self, lines: list[str] | None = None) -> None:
        self.lines = [] if lines is None else list(lines)
        self.last_upsert_block: ops.CronBlock | None = None
        self.last_removed_markers: list[tuple[str, str]] | None = None

    def read_lines(self) -> list[str]:
        return list(self.lines)

    def upsert_block(self, block: ops.CronBlock) -> list[str]:
        self.last_upsert_block = block
        self.lines = [block.begin_marker, *block.entries, block.end_marker]
        return list(self.lines)

    def remove_block(self, markers: list[tuple[str, str]]) -> list[str]:
        self.last_removed_markers = markers
        self.lines = []
        return []


class HarvestOpsTests(unittest.TestCase):
    def test_repo_paths_use_config_schedule_override(self) -> None:
        paths = ops.RepoPaths(Path("/tmp/example"))
        self.assertEqual(Path("/tmp/example/config/extraction_schedule.yaml"), paths.schedule_override_path)

    def test_install_continuous_hourly_harvest_uses_python_entrypoint_and_config_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_script = root / "opensignal_job_intel" / "sources" / "run_harvest_cron.py"
            run_script.parent.mkdir(parents=True, exist_ok=True)
            run_script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

            with patch.object(ops, "_python_executable", return_value="/abs/python3.11"):
                tool = ops.HarvestCronScripts(run_script)
            tool._paths = ops.RepoPaths(root_dir=root)
            tool._crontab = FakeCrontabManager()
            tool._cron_entries = ops.HarvestCronEntryBuilder(tool._paths, "/abs/python3.11")

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = tool.install_continuous_hourly_harvest()

            self.assertEqual(0, result)
            assert isinstance(tool._crontab, FakeCrontabManager)
            block = tool._crontab.last_upsert_block
            assert block is not None
            self.assertEqual("# opensignal-job-intel continuous hourly harvest BEGIN", block.begin_marker)
            self.assertEqual(
                (
                    f"0 * * * * /abs/python3.11 {tool._paths.run_script_path} >> {tool._paths.cron_log_path} 2>&1",
                ),
                block.entries,
            )
            self.assertIn(str(tool._paths.schedule_override_path), output.getvalue())
            self.assertTrue(os.access(run_script, os.X_OK))

    def test_remove_nightly_harvest_reports_empty_crontab(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_script = Path(temp_dir) / "opensignal_job_intel" / "sources" / "remove_harvest_cron.py"
            run_script.parent.mkdir(parents=True, exist_ok=True)
            run_script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
            tool = ops.HarvestCronScripts(run_script)
            tool._crontab = FakeCrontabManager()

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = tool.remove_nightly_harvest()

            self.assertEqual(0, result)
            self.assertIn("Crontab is now empty", output.getvalue())

    def test_run_once_clears_pid_file_after_subprocess_finishes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ops.RepoPaths(root_dir=Path(temp_dir))
            manager = ops.HarvestProcessManager(paths)
            with patch("opensignal_job_intel.sources.linkedin_harvest_ops.subprocess.run", return_value=SimpleNamespace(returncode=7)) as mock_run, patch.object(ops, "_python_executable", return_value="/abs/python3.11"):
                result = manager.run_once()

            self.assertEqual(7, result)
            self.assertFalse(paths.runner_pid_path.exists())
            mock_run.assert_called_once()

    def test_harvest_status_reports_not_running_for_stale_pid_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            script_path = Path(temp_dir) / "opensignal_job_intel" / "sources" / "harvest_status.py"
            script_path.parent.mkdir(parents=True, exist_ok=True)
            script_path.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
            tool = ops.HarvestCronScripts(script_path)
            tool._paths.data_dir.mkdir(parents=True, exist_ok=True)
            tool._paths.runner_pid_path.write_text("999999\n", encoding="utf-8")

            output = io.StringIO()
            with patch("opensignal_job_intel.sources.linkedin_harvest_ops._pid_is_running", return_value=False), contextlib.redirect_stdout(output):
                result = tool.harvest_status()

            self.assertEqual(0, result)
            self.assertIn("Harvest is not running.", output.getvalue())
            self.assertFalse(tool._paths.runner_pid_path.exists())

    def test_show_recent_jobs_fails_cleanly_when_db_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            viewer = ops.HarvestDatabaseViewer(ops.RepoPaths(root_dir=Path(temp_dir)))
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = viewer.show_recent_jobs(10)

            self.assertEqual(1, result)
            self.assertIn("Database not found", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
