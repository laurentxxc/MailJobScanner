import sqlite3
from pathlib import Path
from typing import Optional

from db.models import JobProposalRecord


class JobRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self):
        if self._conn is None:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._init_schema()
        return self._conn

    def _init_schema(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS job_proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email_subject TEXT NOT NULL,
                email_from TEXT NOT NULL,
                email_received_date TEXT NOT NULL,
                job_title TEXT NOT NULL,
                job_url TEXT NOT NULL,
                company TEXT NOT NULL,
                salary TEXT,
                location TEXT,
                resume_match_level TEXT,
                resume_match_summary TEXT,
                expectations_match_level TEXT,
                expectations_match_summary TEXT,
                job_responsibilities_summary TEXT,
                job_requirements_summary TEXT,
                error TEXT,
                status TEXT NOT NULL DEFAULT 'new',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        self.migrate()
        self._conn.commit()

    def migrate(self):
        conn = self.connect()
        for col in [
            "status TEXT NOT NULL DEFAULT 'new'",
            "notes TEXT NOT NULL DEFAULT ''",
            "job_responsibilities_summary TEXT DEFAULT ''",
            "job_requirements_summary TEXT DEFAULT ''",
            "job_technology_domains TEXT DEFAULT ''",
            "message_id TEXT DEFAULT ''",
        ]:
            try:
                conn.execute(f"ALTER TABLE job_proposals ADD COLUMN {col}")
                conn.commit()
            except sqlite3.OperationalError:
                pass

    def insert(self, record: JobProposalRecord) -> int:
        conn = self.connect()
        conn.execute(
            """
            INSERT INTO job_proposals (
                email_subject, email_from, email_received_date,
                job_title, job_url, company, salary, location,
                resume_match_level, resume_match_summary,
                expectations_match_level, expectations_match_summary,
                job_responsibilities_summary, job_requirements_summary,
                job_technology_domains,
                error, status, notes, message_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.email_subject,
                record.email_from,
                record.email_received_date,
                record.job_title,
                record.job_url,
                record.company,
                record.salary,
                record.location,
                record.resume_match_level,
                record.resume_match_summary,
                record.expectations_match_level,
                record.expectations_match_summary,
                record.job_responsibilities_summary,
                record.job_requirements_summary,
                record.job_technology_domains,
                record.error,
                record.status,
                record.notes,
                record.message_id,
                record.created_at,
            ),
        )
        conn.commit()
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def find_last_duplicate(self, company: str, job_title: str) -> tuple[int, str, str] | None:
        self.connect()
        row = self._conn.execute(
            "SELECT id, status, created_at FROM job_proposals WHERE company = ? AND job_title = ? ORDER BY created_at DESC LIMIT 1",
            (company, job_title),
        ).fetchone()
        return (row["id"], row["status"], row["created_at"]) if row else None

    def has_message_id(self, message_id: str) -> bool:
        if not message_id:
            return False
        self.connect()
        row = self._conn.execute(
            "SELECT 1 FROM job_proposals WHERE message_id = ? LIMIT 1",
            (message_id,),
        ).fetchone()
        return row is not None

    def update_status(self, record_id: int, status: str) -> None:
        conn = self.connect()
        conn.execute("UPDATE job_proposals SET status = ? WHERE id = ?", (status, record_id))
        conn.commit()

    def update_notes(self, record_id: int, notes: str) -> None:
        conn = self.connect()
        conn.execute("UPDATE job_proposals SET notes = ? WHERE id = ?", (notes, record_id))
        conn.commit()

    def update_match_results(self, record_id: int, results: dict) -> None:
        self.connect()
        title = results.get("title") if "title" in results else None
        company = results.get("company") if "company" in results else None
        salary = results.get("salary") if "salary" in results else None
        location = results.get("location") if "location" in results else None
        self._conn.execute("""
            UPDATE job_proposals SET
                resume_match_level = ?,
                resume_match_summary = ?,
                expectations_match_level = ?,
                expectations_match_summary = ?,
                job_responsibilities_summary = ?,
                job_requirements_summary = ?,
                job_technology_domains = ?,
                job_title = COALESCE(?, job_title),
                company = COALESCE(?, company),
                salary = COALESCE(?, salary),
                location = COALESCE(?, location),
                error = ?
            WHERE id = ?
        """, (
            results.get("resume_match_level"),
            results.get("resume_match_summary"),
            results.get("expectations_match_level"),
            results.get("expectations_match_summary"),
            results.get("job_responsibilities_summary", ""),
            results.get("job_requirements_summary", ""),
            results.get("job_technology_domains", ""),
            title,
            company,
            salary,
            location,
            results.get("error"),
            record_id,
        ))
        self._conn.commit()

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None
