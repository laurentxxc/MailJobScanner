EXTRACTION_SYSTEM_PROMPT = """\
You are an expert at parsing job alert emails.
Extract ALL job proposals from the email content below.

Return a JSON object with a single key "jobs" containing an array of objects.
Each object must have exactly these fields:
- "title": the job title
- "url": the direct URL to view or apply for the job posting
- "company": the company name offering the job
- "salary": the salary information if mentioned, or null if not specified
- "location": the job location or "Remote" if remote, or null if not specified

Example: {"jobs": [{"title": "Software Engineer", "url": "https://...", "company": "Acme", "salary": null, "location": "Remote"}]}

Do not omit any job listing. If no job proposals are found, return {"jobs": []}.
"""

MATCH_SYSTEM_PROMPT = """\
You are a precise career advisor analyzing how well a job description matches a candidate's profile.

Consider:
- Required skills vs candidate's demonstrated skills
- Required experience level vs candidate's experience
- Industry and domain alignment
- Qualifications and certifications

Respond with a JSON object containing exactly these fields:
- "level": one of "Low", "Medium", or "High"
- "summary": a concise 2-3 sentence explanation justifying the match level
"""


def build_extraction_user_prompt(email_body: str) -> str:
    return f"Email content:\n\n{email_body}"


def build_match_user_prompt(job_description: str, doc_type: str, candidate_text: str) -> str:
    doc_label = "Resume / Professional Experience" if doc_type == "resume" else "Job Expectations & Motivation"
    return (
        f"Job Description:\n{job_description}\n\n"
        f"Candidate {doc_label}:\n{candidate_text}\n\n"
        f"Analyze the match between this job and the candidate's {doc_label.lower()}. "
        "Be honest and specific about what matches and what doesn't."
    )
