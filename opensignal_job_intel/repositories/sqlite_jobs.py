from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from dataclasses import replace

from opensignal_job_intel.models import (
    HarvestQueryState,
    HarvestRunState,
    JobRecord,
    JobSource,
    utc_now,
)


class SQLiteJobRepository:
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

    def upsert_job(self, job: JobRecord) -> None:
        job = _with_inferred_post_datetime(job)
        stored_at = utc_now()
        with self._connect() as connection:
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


def _serialize_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _with_inferred_post_datetime(job: JobRecord) -> JobRecord:
    if job.post_datetime is not None or job.post_age_days is None:
        return job
    return replace(job, post_datetime=job.collected_at - timedelta(days=job.post_age_days))
