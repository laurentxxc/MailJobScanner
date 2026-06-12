from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class JobProposalRecord:
    email_subject: str
    email_from: str
    email_received_date: str
    job_title: str
    job_url: str
    company: str
    salary: Optional[str] = None
    location: Optional[str] = None
    resume_match_level: Optional[str] = None
    resume_match_summary: Optional[str] = None
    expectations_match_level: Optional[str] = None
    expectations_match_summary: Optional[str] = None
    error: Optional[str] = None
    id: Optional[int] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
