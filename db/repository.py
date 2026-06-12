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
                error TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        self._conn.commit()

    def insert(self, record: JobProposalRecord) -> int:
        conn = self.connect()
        conn.execute(
            """
            INSERT INTO job_proposals (
                email_subject, email_from, email_received_date,
                job_title, job_url, company, salary, location,
                resume_match_level, resume_match_summary,
                expectations_match_level, expectations_match_summary,
                error, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                record.error,
                record.created_at,
            ),
        )
        conn.commit()
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None
