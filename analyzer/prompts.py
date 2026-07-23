import re

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

Some URLs in the email are replaced with placeholder URLs like
http://placeholder/track/1. Use the exact placeholder URL as the "url"
field — do not add any extra text before or after it.
"""

RESUME_MATCH_PROMPT = """\
You are a strict technical recruiter evaluating skills and experience match. The evaluation is based in the context of the job description and the candidate's resume. 

IMPORTANT RULES — These override skill match:
- If the job requires permanent relocation to a different country (not occasional travel), score ≤ 2 (Low)
- If the seniority level required (e.g. Staff/Principal/Director) is 2+ levels above or below the candidate's proven level, score ≤ 5 (Medium)

Score 1-4 (Low): 
- less than 30% of skill overlap
- the seniority level is wrong
- missing critical experience or qualifications
Score 5-7 (Medium): 
- 50-70% skill match with some gaps
- plausible but not ideal
Score 8-10 (High): 
- 90%+ skill match (not 80%)
- the required seniority is aligned
- the candidate has relevant domain experience

Output JSON with exactly these fields:
- "score": integer 1-10
- "level": "Low" if score <= 4, "Medium" if 5-7, "High" if 8-10
- "matching_skills": list of specific matching skills or experiences
- "missing_skills": list of specific gaps or missing qualifications
- "summary": 2-3 sentence explanation
"""

EXPECTATIONS_MATCH_PROMPT = """\
You are evaluating whether a job matches the candidate's personal preferences
and career goals.

Key criteria (in order of importance):
1. Salary range — if mentioned, does it fit the candidate's expectations?
2. Location / remote policy — does it match the candidate's preference?
3. Industry and domain — aligned with the candidate's interest?
4. Company stage and culture — compatible with what the candidate wants?
5. Career growth — does the role offer what the candidate seeks?

HARD DEAL-BREAKERS (score must be ≤ 2, level = Low):
- Salary mentioned and below 70% of candidate's expected range
- Location is in a different country and not fully remote
- The job explicitly requires relocation to another continent

Score 1-4 (Low): 
- salary or location is a deal-breaker (see rules above)
- both salary and location are not mentioned (uncertainty rule)
Score 5-7 (Medium): 
- salary range partially matches (70-90% of expected)
- location compatible (remote or within same region)
- most other criteria are satisfactory
Score 8-10 (High): 
- salary range matches 90%+ of expectations
- location is ideal (remote-first or same city)
- industry, preferred technology domains, culture, and growth all align

COMMUTE DATA (when provided):
The candidate's home is at a fixed location. Pre-calculated commute information
to the job location is provided in the user prompt below. Evaluate this against
the candidate's commute threshold in their expectations file. If the commute
exceeds the stated maximum, this is a deal-breaker (score ≤ 4, level = Low).

Output JSON with exactly these fields:
- "score": integer 1-10
- "level": "Low" if score <= 4, "Medium" if 5-7, "High" if 8-10
- "matching_aspects": list of aligned preferences
- "conflicting_aspects": list of mismatches or deal-breakers
- "summary": 2-3 sentence explanation
"""


def shorten_urls(text: str) -> tuple[str, dict[str, str]]:
    url_map = {}
    counter = 0
    def _replacer(m: re.Match) -> str:
        nonlocal counter
        counter += 1
        key = f"http://placeholder/track/{counter}"
        url_map[key] = m.group(0)
        return key
    shortened = re.sub(r'https?://\S+', _replacer, text)
    return shortened, url_map


def restore_urls(jobs: list[dict], url_map: dict[str, str]) -> list[dict]:
    for job in jobs:
        url = job.get("url", "")
        if url in url_map:
            job["url"] = url_map[url].rstrip(")>]\"")
        else:
            match = re.match(r'(http://placeholder/track/\d+)', url)
            if match and match.group(1) in url_map:
                job["url"] = url_map[match.group(1)].rstrip(")>]\"")
    return jobs


def build_extraction_user_prompt(email_body: str) -> str:
    return f"Email content:\n\n{email_body}"


def build_match_user_prompt(job_description: str, doc_type: str, candidate_text: str, commute_info: str = "") -> str:
    doc_label = "Resume / Professional Experience" if doc_type == "resume" else "Job Expectations & Motivation"
    prompt = (
        f"Job Description:\n{job_description}\n\n"
        f"Candidate {doc_label}:\n{candidate_text}\n\n"
        f"Analyze the match between this job and the candidate's {doc_label.lower()}. "
        "Be honest and specific about what matches and what doesn't."
    )
    if commute_info:
        prompt += f"\n\nCommute information: {commute_info}"
    return prompt


JOB_SUMMARY_PROMPT = """\
You are extracting key details from a job description.

Extract the following information:
1. Title — the exact job title
2. Company — the company offering the job
3. Salary — salary information if mentioned, otherwise null
4. Location — job location, "Remote" if remote-first, or null

Then summarize concisely (2-3 sentences each):
5. Responsibilities — what the role involves day-to-day
6. Requirements — qualifications, skills, and experience needed

Then identify (comma-separated list):
7. Technology Domains — technology areas (e.g. "Python, React, PostgreSQL, AWS, Docker")
   and functional domains (e.g. "fintech, payments, data pipelines, real-time systems")
   covered by the role. List the most prominent ones, max 10-12 items.

Output JSON with exactly these fields:
- "title": the job title
- "company": the company name
- "salary": salary info or null
- "location": location or null
- "responsibilities": concise summary of key responsibilities
- "requirements": concise summary of key requirements
- "technology_domains": comma-separated list of technology areas and functional domains
"""


def build_summary_user_prompt(job_description: str) -> str:
    return f"Job Description:\n\n{job_description}"
