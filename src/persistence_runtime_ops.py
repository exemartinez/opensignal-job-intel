"""Persistence and runtime operations for the refactored system.

Author: Ezequiel H. Martinez
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

from src.core_domain_inputs import (
    HarvestQueryState,
    HarvestRunState,
    JobRecord,
    JobSource,
    utc_now,
)


class SQLiteJobRepository:
    """Persist canonical jobs and harvest state in the local SQLite database."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)

    def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dedupe_key TEXT NOT NULL UNIQUE,
                    source TEXT NOT NULL,
                    external_job_id TEXT,
                    company TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    post_datetime TEXT,
                    link TEXT NOT NULL,
                    salary_text TEXT,
                    location_text TEXT,
                    workplace_type TEXT,
                    post_age_text TEXT,
                    post_age_days INTEGER,
                    collected_at TEXT NOT NULL,
                    stored_at TEXT NOT NULL,
                    seen INTEGER NOT NULL DEFAULT 0,
                    applied INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_source_external_job_id "
                "ON jobs(source, external_job_id)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS harvest_run_state (
                    source TEXT PRIMARY KEY,
                    throttle_events INTEGER NOT NULL DEFAULT 0,
                    current_backoff_seconds REAL NOT NULL DEFAULT 0,
                    sticky_caution_enabled INTEGER NOT NULL DEFAULT 0,
                    last_throttle_at TEXT,
                    last_success_at TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS harvest_query_state (
                    source TEXT NOT NULL,
                    query TEXT NOT NULL,
                    next_start INTEGER NOT NULL DEFAULT 0,
                    consecutive_empty_pages INTEGER NOT NULL DEFAULT 0,
                    yielded_new_ids INTEGER NOT NULL DEFAULT 0,
                    saw_stale_results INTEGER NOT NULL DEFAULT 0,
                    last_success_at TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(source, query)
                )
                """
            )
            existing_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(jobs)").fetchall()
            }
            if "salary_text" not in existing_columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN salary_text TEXT")
            if "location_text" not in existing_columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN location_text TEXT")
            if "workplace_type" not in existing_columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN workplace_type TEXT")
            if "post_age_text" not in existing_columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN post_age_text TEXT")
            if "post_age_days" not in existing_columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN post_age_days INTEGER")

    def upsert_job(self, job: JobRecord) -> bool:
        job = _with_inferred_post_datetime(job)
        stored_at = utc_now()
        with self._connect() as connection:
            existing_row = connection.execute(
                "SELECT 1 FROM jobs WHERE dedupe_key = ?",
                (job.dedupe_key,),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO jobs (
                    dedupe_key,
                    source,
                    external_job_id,
                    company,
                    title,
                    description,
                    post_datetime,
                    link,
                    salary_text,
                    location_text,
                    workplace_type,
                    post_age_text,
                    post_age_days,
                    collected_at,
                    stored_at,
                    seen,
                    applied
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dedupe_key) DO UPDATE SET
                    external_job_id = excluded.external_job_id,
                    company = excluded.company,
                    title = excluded.title,
                    description = excluded.description,
                    post_datetime = excluded.post_datetime,
                    link = excluded.link,
                    salary_text = excluded.salary_text,
                    location_text = excluded.location_text,
                    workplace_type = excluded.workplace_type,
                    post_age_text = excluded.post_age_text,
                    post_age_days = excluded.post_age_days,
                    collected_at = excluded.collected_at,
                    stored_at = excluded.stored_at
                """,
                (
                    job.dedupe_key,
                    job.source.value,
                    job.external_job_id,
                    job.company,
                    job.title,
                    job.description,
                    _serialize_datetime(job.post_datetime),
                    job.link,
                    job.salary_text,
                    job.location_text,
                    job.workplace_type,
                    job.post_age_text,
                    job.post_age_days,
                    _serialize_datetime(job.collected_at),
                    _serialize_datetime(stored_at),
                    int(job.seen),
                    int(job.applied),
                ),
            )
        return existing_row is None

    def list_jobs(self, limit: int = 20) -> list[JobRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    source,
                    company,
                    title,
                    description,
                    link,
                    salary_text,
                    location_text,
                    workplace_type,
                    post_age_text,
                    post_age_days,
                    collected_at,
                    external_job_id,
                    post_datetime,
                    stored_at,
                    seen,
                    applied
                FROM jobs
                ORDER BY collected_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_job(row) for row in rows]

    def count_jobs(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()
        return int(row[0])

    def existing_external_job_ids(
        self, source: JobSource, external_job_ids: list[str]
    ) -> set[str]:
        ids = [value.strip() for value in external_job_ids if value.strip()]
        if not ids:
            return set()
        placeholders = ", ".join("?" for _ in ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT external_job_id
                FROM jobs
                WHERE source = ?
                  AND external_job_id IN ({placeholders})
                """,
                (source.value, *ids),
            ).fetchall()
        return {str(row[0]) for row in rows if row[0]}

    def get_harvest_run_state(self, source: str) -> HarvestRunState:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM harvest_run_state WHERE source = ?", (source,)
            ).fetchone()
        if row is None:
            return HarvestRunState(source=source)
        return HarvestRunState(
            source=row["source"],
            throttle_events=int(row["throttle_events"]),
            current_backoff_seconds=float(row["current_backoff_seconds"]),
            sticky_caution_enabled=bool(row["sticky_caution_enabled"]),
            last_throttle_at=_parse_datetime(row["last_throttle_at"]),
            last_success_at=_parse_datetime(row["last_success_at"]),
        )

    def save_harvest_run_state(self, state: HarvestRunState) -> None:
        updated_at = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO harvest_run_state (
                    source,
                    throttle_events,
                    current_backoff_seconds,
                    sticky_caution_enabled,
                    last_throttle_at,
                    last_success_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    throttle_events = excluded.throttle_events,
                    current_backoff_seconds = excluded.current_backoff_seconds,
                    sticky_caution_enabled = excluded.sticky_caution_enabled,
                    last_throttle_at = excluded.last_throttle_at,
                    last_success_at = excluded.last_success_at,
                    updated_at = excluded.updated_at
                """,
                (
                    state.source,
                    state.throttle_events,
                    state.current_backoff_seconds,
                    int(state.sticky_caution_enabled),
                    _serialize_datetime(state.last_throttle_at),
                    _serialize_datetime(state.last_success_at),
                    _serialize_datetime(updated_at),
                ),
            )

    def get_harvest_query_state(self, source: str, query: str) -> HarvestQueryState:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM harvest_query_state WHERE source = ? AND query = ?",
                (source, query),
            ).fetchone()
        if row is None:
            return HarvestQueryState(source=source, query=query)
        return HarvestQueryState(
            source=row["source"],
            query=row["query"],
            next_start=int(row["next_start"]),
            consecutive_empty_pages=int(row["consecutive_empty_pages"]),
            yielded_new_ids=int(row["yielded_new_ids"]),
            saw_stale_results=bool(row["saw_stale_results"]),
            last_success_at=_parse_datetime(row["last_success_at"]),
        )

    def save_harvest_query_state(self, state: HarvestQueryState) -> None:
        updated_at = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO harvest_query_state (
                    source,
                    query,
                    next_start,
                    consecutive_empty_pages,
                    yielded_new_ids,
                    saw_stale_results,
                    last_success_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, query) DO UPDATE SET
                    next_start = excluded.next_start,
                    consecutive_empty_pages = excluded.consecutive_empty_pages,
                    yielded_new_ids = excluded.yielded_new_ids,
                    saw_stale_results = excluded.saw_stale_results,
                    last_success_at = excluded.last_success_at,
                    updated_at = excluded.updated_at
                """,
                (
                    state.source,
                    state.query,
                    state.next_start,
                    state.consecutive_empty_pages,
                    state.yielded_new_ids,
                    int(state.saw_stale_results),
                    _serialize_datetime(state.last_success_at),
                    _serialize_datetime(updated_at),
                ),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _row_to_job(self, row: sqlite3.Row) -> JobRecord:
        return JobRecord(
            source=JobSource(row["source"]),
            company=row["company"],
            title=row["title"],
            description=row["description"],
            link=row["link"],
            salary_text=row["salary_text"],
            location_text=row["location_text"],
            workplace_type=row["workplace_type"],
            post_age_text=row["post_age_text"],
            post_age_days=row["post_age_days"],
            collected_at=_parse_datetime(row["collected_at"]),
            external_job_id=row["external_job_id"],
            post_datetime=_parse_datetime(row["post_datetime"]),
            stored_at=_parse_datetime(row["stored_at"]),
            seen=bool(row["seen"]),
            applied=bool(row["applied"]),
        )


@dataclass(frozen=True, slots=True)
class RepoPaths:
    """Resolve repository-local paths used by runtime commands."""

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
        return self.root_dir / "src" / "runtime_entrypoints.py"

    @property
    def remove_one_shot_script_path(self) -> Path:
        return self.run_script_path


@dataclass(frozen=True, slots=True)
class CronBlock:
    """Represent a named crontab block that can be replaced atomically."""

    begin_marker: str
    end_marker: str
    entries: tuple[str, ...]


class CrontabManager:
    """Read, replace, and remove logical cron blocks from the user crontab."""

    def read_lines(self) -> list[str]:
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
        content = "\n".join(lines).rstrip()
        payload = (content + "\n") if content else ""
        subprocess.run(["crontab", "-"], input=payload, text=True, check=True)

    def remove_block(self, markers: list[tuple[str, str]]) -> list[str]:
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
        filtered = self.remove_block([(block.begin_marker, block.end_marker)])
        filtered.extend([block.begin_marker, *block.entries, block.end_marker])
        self.write_lines(filtered)
        return filtered


class HarvestProcessManager:
    """Manage the guarded one-shot execution of the harvest wrapper."""

    def __init__(self, paths: RepoPaths) -> None:
        self._paths = paths

    def active_matches(self) -> list[str]:
        pid = self._read_active_pid()
        if pid is None:
            return []
        return [f"pid={pid} command={self._paths.run_script_path} run-harvest-cron"]

    def is_running(self) -> bool:
        return self._read_active_pid() is not None

    def run_once(self) -> int:
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
        print("  ".join(column.ljust(widths[column]) for column in columns))
        for values in text_rows:
            print("  ".join(values[column].ljust(widths[column]) for column in columns))
        return 0


class LogTailer:
    """Tail one or more local log files until interrupted."""

    def tail(self, paths: list[Path]) -> int:
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
        return CronBlock(
            begin_marker="# opensignal-job-intel nightly harvest BEGIN",
            end_marker="# opensignal-job-intel nightly harvest END",
            entries=(self._entry(schedule="0 0 * * *"),),
        )

    def continuous_hourly_block(self) -> CronBlock:
        return CronBlock(
            begin_marker="# opensignal-job-intel continuous hourly harvest BEGIN",
            end_marker="# opensignal-job-intel continuous hourly harvest END",
            entries=(self._entry(schedule="0 * * * *"),),
        )

    def temporary_hourly_block(
        self, *, minute: int, day: int, month: int, start_hour: int, end_hour: int
    ) -> CronBlock:
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
            f"{schedule} {self._python_executable} {self._paths.run_script_path} run-harvest-cron >> "
            f"{self._paths.cron_log_path} 2>&1"
        )


class HarvestCronScripts:
    """Dispatch runtime operations through the single refactored entrypoint surface."""

    def __init__(self, script_path: str | Path) -> None:
        resolved = Path(script_path).resolve()
        self._script_path = resolved
        self._paths = RepoPaths(root_dir=_resolve_repo_root(resolved))
        self._crontab = CrontabManager()
        self._processes = HarvestProcessManager(self._paths)
        self._db = HarvestDatabaseViewer(self._paths)
        self._tailer = LogTailer()
        self._cron_entries = HarvestCronEntryBuilder(self._paths, _python_executable())

    def run(self, argv: list[str]) -> int:
        command = argv[1] if len(argv) > 1 else ""
        handlers = {
            "harvest-status": self.harvest_status,
            "install-continuous-hourly-harvest-cron": self.install_continuous_hourly_harvest,
            "install-harvest-cron": self.install_nightly_harvest,
            "remove-harvest-cron": self.remove_nightly_harvest,
            "remove-one-shot-harvest-cron": self.remove_one_shot_harvest,
            "run-harvest-cron": self._processes.run_once,
            "schedule-harvest-next-minute": self.schedule_harvest_next_minute,
            "show-recent-jobs": lambda: self._db.show_recent_jobs(int(argv[2]) if len(argv) > 2 else 25),
            "tail-harvest-logs": lambda: self._tailer.tail(
                [self._paths.harvest_log_path, self._paths.cron_log_path]
            ),
        }
        try:
            return handlers[command]()
        except KeyError as exc:
            raise ValueError(f"Unsupported runtime command: {command}") from exc

    def harvest_status(self) -> int:
        matches = self._processes.active_matches()
        if matches:
            print("Harvest is running.")
            for line in matches:
                print(line)
            return 0
        print("Harvest is not running.")
        return 0

    def install_nightly_harvest(self) -> int:
        self._install_cron_block(self._cron_entries.nightly_block())
        print("Installed nightly harvest cron entry.")
        print(f"Window is controlled by {self._paths.schedule_override_path}")
        print(f"Harvest runner: {self._paths.run_script_path} run-harvest-cron")
        print(f"Current log target: {self._paths.cron_log_path}")
        self._print_current_crontab()
        return 0

    def install_continuous_hourly_harvest(self) -> int:
        self._install_cron_block(self._cron_entries.continuous_hourly_block())
        print("Installed continuous hourly harvest cron entry.")
        print(f"Runs at minute 0 of every hour using {self._paths.run_script_path} run-harvest-cron")
        print(f"Window is still controlled by {self._paths.schedule_override_path}")
        print(f"Current log target: {self._paths.cron_log_path}")
        self._print_current_crontab()
        return 0

    def remove_nightly_harvest(self) -> int:
        lines = self._crontab.remove_block(
            [
                (
                    "# opensignal-job-intel nightly harvest BEGIN",
                    "# opensignal-job-intel nightly harvest END",
                ),
                (
                    "# opensignal-job-intel continuous hourly harvest BEGIN",
                    "# opensignal-job-intel continuous hourly harvest END",
                ),
            ]
        )
        if lines:
            print("Removed harvest cron entry.")
            self._print_current_crontab(lines)
            return 0
        print("Removed harvest cron entry. Crontab is now empty.")
        return 0

    def remove_one_shot_harvest(self) -> int:
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
            "Use "
            f"{self._paths.run_script_path} remove-one-shot-harvest-cron "
            "to remove the temporary cron block later if desired."
        )
        self._print_current_crontab()
        return 0

    def _start_background_harvest(self) -> None:
        with self._paths.cron_log_path.open("a", encoding="utf-8") as handle:
            process = subprocess.Popen(
                [
                    self._cron_entries._python_executable,
                    str(self._paths.run_script_path),
                    "run-harvest-cron",
                ],
                cwd=self._paths.root_dir,
                stdout=handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        print(f"Started harvest immediately in background (pid {process.pid}).")

    def _install_cron_block(self, block: CronBlock) -> None:
        self._paths.data_dir.mkdir(parents=True, exist_ok=True)
        self._crontab.upsert_block(block)

    def _print_current_crontab(self, lines: list[str] | None = None) -> None:
        print("\nCurrent crontab:")
        for line in (self._crontab.read_lines() if lines is None else lines):
            print(line)


class RepositoryStateStore:
    """Own repository-backed job and harvest state access."""

    def __init__(self, repository: SQLiteJobRepository) -> None:
        self._repository = repository

    def initialize(self) -> None:
        self._repository.initialize()

    def upsert_job(self, job: JobRecord) -> bool:
        return self._repository.upsert_job(job)

    def count_jobs(self) -> int:
        return self._repository.count_jobs()

    def list_jobs(self, limit: int) -> list[JobRecord]:
        return self._repository.list_jobs(limit)

    def get_harvest_run_state(self, source: str) -> HarvestRunState:
        return self._repository.get_harvest_run_state(source)

    def save_harvest_run_state(self, state: HarvestRunState) -> None:
        self._repository.save_harvest_run_state(state)

    def get_harvest_query_state(self, source: str, query: str) -> HarvestQueryState:
        return self._repository.get_harvest_query_state(source, query)

    def save_harvest_query_state(self, state: HarvestQueryState) -> None:
        self._repository.save_harvest_query_state(state)

    def existing_external_job_ids(self, source: JobSource, external_job_ids: list[str]) -> set[str]:
        return self._repository.existing_external_job_ids(source, external_job_ids)


class RuntimePathResolver:
    """Resolve repository-local paths used by runtime helpers."""

    def __init__(self, root_dir: Path) -> None:
        self._paths = RepoPaths(root_dir=root_dir)

    @property
    def paths(self) -> RepoPaths:
        return self._paths


class RuntimeScriptDispatcher:
    """Dispatch runtime helper commands through the unified runtime module."""

    def __init__(self, script_path: str | Path) -> None:
        self._scripts = HarvestCronScripts(script_path)

    def run(self, argv: list[str]) -> int:
        return self._scripts.run(argv)


def run_script(script_path: str | Path, argv: list[str] | None = None) -> int:
    tool = HarvestCronScripts(script_path)
    return tool.run(list(sys.argv if argv is None else argv))


def _serialize_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _with_inferred_post_datetime(job: JobRecord) -> JobRecord:
    if job.post_datetime is not None or job.post_age_days is None:
        return job
    return replace(job, post_datetime=job.collected_at - timedelta(days=job.post_age_days))


def _python_executable() -> str:
    if sys.executable and Path(sys.executable).exists():
        return sys.executable
    for candidate in ("python3.11", "python3"):
        resolved = _which(candidate)
        if resolved:
            return resolved
    return sys.executable


def _which(program: str) -> str | None:
    path = os.environ.get("PATH", "")
    for directory in path.split(os.pathsep):
        candidate = Path(directory) / program
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _resolve_repo_root(path: Path) -> Path:
    for parent in [path.parent, *path.parents]:
        if (parent / "main.py").exists() and (parent / "README.md").exists():
            return parent
    return path.parent


__all__ = [
    "CronBlock",
    "CrontabManager",
    "HarvestCronEntryBuilder",
    "HarvestCronScripts",
    "HarvestDatabaseViewer",
    "HarvestProcessManager",
    "LogTailer",
    "RepoPaths",
    "RepositoryStateStore",
    "RuntimePathResolver",
    "RuntimeScriptDispatcher",
    "SQLiteJobRepository",
    "run_script",
]
