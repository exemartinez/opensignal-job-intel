from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from opensignal_job_intel.models import JobRecord, JobSource, utc_now


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
