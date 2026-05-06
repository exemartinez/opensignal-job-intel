from __future__ import annotations

import os
import sqlite3
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True, slots=True)
class RepoPaths:
    """Resolve repository-local paths used by harvest runtime helpers."""

    root_dir: Path

    @property
    def data_dir(self) -> Path:
        return self.root_dir / "data"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "jobs.db"

    @property
    def cron_log_path(self) -> Path:
        return self.data_dir / "cron-harvest.log"

    @property
    def harvest_log_path(self) -> Path:
        return self.data_dir / "harvest-linkedin.log"

    @property
    def runner_pid_path(self) -> Path:
        return self.data_dir / "harvest-runner.pid"

    @property
    def schedule_override_path(self) -> Path:
        return self.root_dir / "config" / "extraction_schedule.yaml"

    @property
    def run_script_path(self) -> Path:
        return self.root_dir / "opensignal_job_intel" / "sources" / "run_harvest_cron.py"

    @property
    def remove_one_shot_script_path(self) -> Path:
        return (
            self.root_dir
            / "opensignal_job_intel"
            / "sources"
            / "remove_one_shot_harvest_cron.py"
        )


@dataclass(frozen=True, slots=True)
class CronBlock:
    """Represent a named crontab block that can be installed or removed atomically."""

    begin_marker: str
    end_marker: str
    entries: tuple[str, ...]


class CrontabManager:
    """Read, replace, and remove logical cron blocks from the user crontab."""

    def read_lines(self) -> list[str]:
        """Return the current crontab as lines, or an empty list when missing."""

        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return []
        return result.stdout.splitlines()

    def write_lines(self, lines: Iterable[str]) -> None:
        """Overwrite the current crontab with the provided line sequence."""

        content = "\n".join(lines).rstrip()
        payload = (content + "\n") if content else ""
        subprocess.run(["crontab", "-"], input=payload, text=True, check=True)

    def remove_block(self, markers: list[tuple[str, str]]) -> list[str]:
        """Remove all blocks identified by begin/end markers and return remaining lines."""

        lines = self.read_lines()
        if not lines:
            return []
        filtered: list[str] = []
        skip = False
        active_markers = {begin: end for begin, end in markers}
        end_markers = {end for _, end in markers}
        current_end = ""
        for line in lines:
            if line in active_markers:
                skip = True
                current_end = active_markers[line]
                continue
            if skip and line == current_end:
                skip = False
                current_end = ""
                continue
            if not skip and line in end_markers:
                continue
            if not skip:
                filtered.append(line)
        self.write_lines(filtered)
        return filtered

    def upsert_block(self, block: CronBlock) -> list[str]:
        """Replace a named block if present, then append the new block contents."""

        filtered = self.remove_block([(block.begin_marker, block.end_marker)])
        filtered.extend([block.begin_marker, *block.entries, block.end_marker])
        self.write_lines(filtered)
        return filtered


class HarvestProcessManager:
    """Manage the guarded one-shot execution of the harvest wrapper."""

    def __init__(self, paths: RepoPaths) -> None:
        self._paths = paths

    def active_matches(self) -> list[str]:
        """Describe the active wrapper process when the PID lock is still valid."""

        pid = self._read_active_pid()
        if pid is None:
            return []
        return [f"pid={pid} script={self._paths.run_script_path}"]

    def is_running(self) -> bool:
        """Return whether the wrapper PID lock still points to a live process."""

        return self._read_active_pid() is not None

    def run_once(self) -> int:
        """Run one guarded harvest invocation and clear the PID lock afterward."""

        print(f"[{_timestamp()}] starting harvest wrapper in {self._paths.root_dir}")
        if self.is_running():
            print(
                f"[{_timestamp()}] harvest already running, wrapper exiting without starting a second process"
            )
            return 0
        self._paths.data_dir.mkdir(parents=True, exist_ok=True)
        self._paths.runner_pid_path.write_text(f"{os.getpid()}\n", encoding="utf-8")
        try:
            command = [
                _python_executable(),
                "main.py",
                "harvest-linkedin",
                "--compass-file",
                "profiles/professional_compass.json",
                "--db-path",
                "data/jobs.db",
            ]
            result = subprocess.run(command, cwd=self._paths.root_dir, check=False)
            return int(result.returncode)
        finally:
            self._clear_pid_file()

    def _read_active_pid(self) -> int | None:
        if not self._paths.runner_pid_path.exists():
            return None
        try:
            pid = int(self._paths.runner_pid_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            self._clear_pid_file()
            return None
        if _pid_is_running(pid):
            return pid
        self._clear_pid_file()
        return None

    def _clear_pid_file(self) -> None:
        try:
            self._paths.runner_pid_path.unlink()
        except FileNotFoundError:
            pass


class HarvestDatabaseViewer:
    """Render recent stored jobs from the local SQLite database."""

    def __init__(self, paths: RepoPaths) -> None:
        self._paths = paths

    def show_recent_jobs(self, limit: int) -> int:
        """Print the most recent stored jobs or fail clearly when the DB is missing."""

        if not self._paths.db_path.exists():
            print(f"Database not found: {self._paths.db_path}", file=sys.stderr)
            return 1
        with sqlite3.connect(self._paths.db_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT
                  id,
                  source,
                  external_job_id,
                  company,
                  title,
                  location_text,
                  workplace_type,
                  post_age_days,
                  collected_at
                FROM jobs
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        columns = [
            "id",
            "source",
            "external_job_id",
            "company",
            "title",
            "location_text",
            "workplace_type",
            "post_age_days",
            "collected_at",
        ]
        widths = {column: len(column) for column in columns}
        text_rows: list[dict[str, str]] = []
        for row in rows:
            values = {
                column: "" if row[column] is None else str(row[column])
                for column in columns
            }
            text_rows.append(values)
            for column, value in values.items():
                widths[column] = max(widths[column], len(value))
        header = "  ".join(column.ljust(widths[column]) for column in columns)
        print(header)
        for values in text_rows:
            print("  ".join(values[column].ljust(widths[column]) for column in columns))
        return 0


class LogTailer:
    """Tail one or more local log files until interrupted."""

    def tail(self, paths: list[Path]) -> int:
        """Follow appended content for the provided log paths."""

        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch(exist_ok=True)
        print("Tailing:")
        for path in paths:
            print(f"  {path}")
        positions = {path: path.stat().st_size for path in paths}
        try:
            while True:
                for path in paths:
                    with path.open("r", encoding="utf-8") as handle:
                        handle.seek(positions[path])
                        chunk = handle.read()
                        if chunk:
                            sys.stdout.write(chunk)
                            sys.stdout.flush()
                            positions[path] = handle.tell()
                time.sleep(1.0)
        except KeyboardInterrupt:
            return 0


class HarvestCronEntryBuilder:
    """Build canonical cron blocks for nightly, hourly, and temporary harvest runs."""

    def __init__(self, paths: RepoPaths, python_executable: str) -> None:
        self._paths = paths
        self._python_executable = python_executable

    def nightly_block(self) -> CronBlock:
        """Return the canonical nightly harvest cron block."""

        return CronBlock(
            begin_marker="# opensignal-job-intel nightly harvest BEGIN",
            end_marker="# opensignal-job-intel nightly harvest END",
            entries=(
                self._entry(schedule="0 0 * * *"),
            ),
        )

    def continuous_hourly_block(self) -> CronBlock:
        """Return the canonical top-of-hour continuous harvest cron block."""

        return CronBlock(
            begin_marker="# opensignal-job-intel continuous hourly harvest BEGIN",
            end_marker="# opensignal-job-intel continuous hourly harvest END",
            entries=(
                self._entry(schedule="0 * * * *"),
            ),
        )

    def temporary_hourly_block(
        self, *, minute: int, day: int, month: int, start_hour: int, end_hour: int
    ) -> CronBlock:
        """Return a one-day temporary block that fires hourly between the provided bounds."""

        entries = tuple(
            self._entry(schedule=f"{minute} {hour:02d} {day} {month} *")
            for hour in range(start_hour, end_hour)
        )
        return CronBlock(
            begin_marker="# opensignal-job-intel temporary harvest BEGIN",
            end_marker="# opensignal-job-intel temporary harvest END",
            entries=entries,
        )

    def _entry(self, *, schedule: str) -> str:
        return (
            f"{schedule} {self._python_executable} {self._paths.run_script_path} >> "
            f"{self._paths.cron_log_path} 2>&1"
        )


class HarvestCronScripts:
    """Dispatch source-local operational entrypoints for harvest installation and monitoring."""

    def __init__(self, script_path: str | Path) -> None:
        resolved = Path(script_path).resolve()
        self._script_path = resolved
        self._paths = RepoPaths(root_dir=resolved.parents[2])
        self._crontab = CrontabManager()
        self._processes = HarvestProcessManager(self._paths)
        self._db = HarvestDatabaseViewer(self._paths)
        self._tailer = LogTailer()
        self._cron_entries = HarvestCronEntryBuilder(self._paths, _python_executable())

    def run(self, argv: list[str]) -> int:
        """Route the current entrypoint filename to the matching operational command."""

        handlers = {
            "harvest_status.py": lambda: self.harvest_status(),
            "install_continuous_hourly_harvest_cron.py": lambda: self.install_continuous_hourly_harvest(),
            "install_harvest_cron.py": lambda: self.install_nightly_harvest(),
            "remove_harvest_cron.py": lambda: self.remove_nightly_harvest(),
            "remove_one_shot_harvest_cron.py": lambda: self.remove_one_shot_harvest(),
            "run_harvest_cron.py": lambda: self._processes.run_once(),
            "schedule_harvest_next_minute.py": lambda: self.schedule_harvest_next_minute(),
            "show_recent_jobs.py": lambda: self._db.show_recent_jobs(int(argv[1]) if len(argv) > 1 else 25),
            "tail_harvest_logs.py": lambda: self._tailer.tail(
                [self._paths.harvest_log_path, self._paths.cron_log_path]
            ),
        }
        try:
            return handlers[self._script_path.name]()
        except KeyError as exc:
            raise ValueError(
                f"Unsupported script entrypoint: {self._script_path.name}"
            ) from exc

    def harvest_status(self) -> int:
        """Print whether the harvest wrapper is currently running."""

        matches = self._processes.active_matches()
        if matches:
            print("Harvest is running.")
            for line in matches:
                print(line)
            return 0
        print("Harvest is not running.")
        return 0

    def install_nightly_harvest(self) -> int:
        """Install the canonical nightly harvest cron block."""

        self._install_cron_block(self._cron_entries.nightly_block())
        print("Installed nightly harvest cron entry.")
        print(f"Window is controlled by {self._paths.schedule_override_path}")
        print(f"Harvest runner: {self._paths.run_script_path}")
        print(f"Current log target: {self._paths.cron_log_path}")
        self._print_current_crontab()
        return 0

    def install_continuous_hourly_harvest(self) -> int:
        """Install the top-of-hour continuous harvest cron block."""

        self._install_cron_block(self._cron_entries.continuous_hourly_block())
        print("Installed continuous hourly harvest cron entry.")
        print(f"Runs at minute 0 of every hour using {self._paths.run_script_path}")
        print(f"Window is still controlled by {self._paths.schedule_override_path}")
        print(f"Current log target: {self._paths.cron_log_path}")
        self._print_current_crontab()
        return 0

    def remove_nightly_harvest(self) -> int:
        """Remove the nightly harvest cron block from the user crontab."""

        lines = self._crontab.remove_block(
            [
                (
                    "# opensignal-job-intel nightly harvest BEGIN",
                    "# opensignal-job-intel nightly harvest END",
                )
            ]
        )
        if lines:
            print("Removed nightly harvest cron entry.")
            self._print_current_crontab(lines)
            return 0
        print("Removed nightly harvest cron entry. Crontab is now empty.")
        return 0

    def remove_one_shot_harvest(self) -> int:
        """Remove temporary/one-shot harvest cron blocks from the user crontab."""

        self._crontab.remove_block(
            [
                (
                    "# opensignal-job-intel temporary harvest BEGIN",
                    "# opensignal-job-intel temporary harvest END",
                ),
                (
                    "# opensignal-job-intel one-shot harvest BEGIN",
                    "# opensignal-job-intel one-shot harvest END",
                ),
            ]
        )
        print(f"[{_timestamp()}] removed temporary harvest cron block")
        return 0

    def schedule_harvest_next_minute(self) -> int:
        """Install a temporary same-day hourly cron block and start one background run."""

        self._paths.data_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        self._install_cron_block(
            self._cron_entries.temporary_hourly_block(
                minute=now.minute,
                day=now.day,
                month=now.month,
                start_hour=now.hour + 1,
                end_hour=12,
            )
        )
        self._start_background_harvest()
        print(
            f"Installed hourly fallback harvest starts at minute {now.minute:02d} through 11:00 local time."
        )
        print(
            f"Use {self._paths.remove_one_shot_script_path} to remove the temporary cron block later if desired."
        )
        self._print_current_crontab()
        return 0

    def _start_background_harvest(self) -> None:
        """Launch one detached harvest wrapper run and append output to the cron log."""

        with self._paths.cron_log_path.open("a", encoding="utf-8") as handle:
            process = subprocess.Popen(
                [self._cron_entries._python_executable, str(self._paths.run_script_path)],
                cwd=self._paths.root_dir,
                stdout=handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        print(f"Started harvest immediately in background (pid {process.pid}).")

    def _install_cron_block(self, block: CronBlock) -> None:
        """Ensure the wrapper is executable, then upsert the provided cron block."""

        self._paths.data_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_executable(self._paths.run_script_path)
        self._crontab.upsert_block(block)

    def _ensure_executable(self, path: Path) -> None:
        current_mode = path.stat().st_mode
        path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def _print_current_crontab(self, lines: list[str] | None = None) -> None:
        print("\nCurrent crontab:")
        for line in (self._crontab.read_lines() if lines is None else lines):
            print(line)


def _python_executable() -> str:
    """Return an absolute Python executable path suitable for cron and subprocess use."""

    if sys.executable and Path(sys.executable).exists():
        return sys.executable
    for candidate in ("python3.11", "python3"):
        resolved = _which(candidate)
        if resolved:
            return resolved
    return sys.executable


def _which(program: str) -> str | None:
    """Resolve an executable from PATH without invoking a shell."""

    path = os.environ.get("PATH", "")
    for directory in path.split(os.pathsep):
        candidate = Path(directory) / program
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _timestamp() -> str:
    """Return a local timestamp for wrapper log messages."""

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _pid_is_running(pid: int) -> bool:
    """Return whether the given PID still appears to be alive."""

    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def run_script(script_path: str | Path, argv: list[str] | None = None) -> int:
    """Execute the operational command associated with the given source-local entrypoint."""

    tool = HarvestCronScripts(script_path)
    return tool.run(list(sys.argv if argv is None else argv))
