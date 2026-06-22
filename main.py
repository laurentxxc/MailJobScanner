#!/usr/bin/env python3
import json
import logging
import re
import sys
from pathlib import Path

import yaml
import trafilatura
import requests
from bs4 import BeautifulSoup

from analyzer.llm_client import LlmClient
from db.models import JobProposalRecord
from db.repository import JobRepository
from scanner.email_parser import parse_eml

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


def load_config() -> dict:
    config_path = Path(__file__).parent / "config.yaml"
    if not config_path.exists():
        logger.error("config.yaml not found at %s", config_path)
        sys.exit(1)
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def fetch_job_description(url: str) -> str | None:
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(downloaded)
            if text:
                return text
        resp = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)
    except Exception as e:
        logger.warning("Failed to fetch URL %s: %s", url, e)
        return None

_LOGIN_SIGNALS = ["sign in", "log in", "create account", "forgot password", "password"]

def is_login_page(text: str, url: str = "") -> bool:
    if len(text) < 300:
        return True
    lower = text.lower()
    count = sum(1 for s in _LOGIN_SIGNALS if s in lower)
    if "linkedin.com" in url.lower() and "sign in" in lower:
        return True
    return count >= 3

def process_eml(filepath: str, config: dict, llm: LlmClient, repo: JobRepository) -> dict:
    email_data = parse_eml(filepath)
    logger.info("Processing: %s", email_data["subject"])

    proposals = llm.extract_job_proposals(email_data["body"])
    if not proposals:
        logger.info("No job proposals found in email")
        return {"file": filepath, "flagged": False, "total": 0}

    logger.info("Found %d proposals", len(proposals))
    has_high_match = False

    for prop in proposals:
        title = prop.get("title", "Unknown")
        url = prop.get("url", "")
        company = prop.get("company", "Unknown")
        salary = prop.get("salary", "Unknown")
        location = prop.get("location", "Unknown")

        jd_text = None
        resume_match = None
        expectations_match = None
        error = None

        if url:
            jd_text = fetch_job_description(url)
            if jd_text and is_login_page(jd_text, url):
                logger.info("Login page detected for '%s' at %s", title, url)
                error = f"Login page detected at {url}"
                jd_text = None
            if jd_text:
                try:
                    resume_match = llm.match_resume(jd_text)
                    logger.info("Resume match for '%s': %s", title, resume_match.get("level", "?"))
                except Exception as e:
                    logger.warning("Resume match failed for '%s': %s", title, e)
                    resume_match = {"level": "Error", "summary": str(e)}

                try:
                    expectations_match = llm.match_expectations(jd_text)
                    logger.info(
                        "Expectations match for '%s': %s",
                        title,
                        expectations_match.get("level", "?"),
                    )
                except Exception as e:
                    logger.warning("Expectations match failed for '%s': %s", title, e)
                    expectations_match = {"level": "Error", "summary": str(e)}
            else:
                error = f"Could not fetch job description from {url}"
        else:
            error = "No URL provided for this proposal"

        record = JobProposalRecord(
            email_subject=email_data["subject"],
            email_from=email_data["from"],
            email_received_date=email_data["date"],
            job_title=title,
            job_url=url,
            company=company,
            salary=salary,
            location=location,
            resume_match_level=resume_match.get("level") if resume_match else None,
            resume_match_summary=resume_match.get("summary") if resume_match else "",
            expectations_match_level=expectations_match.get("level") if expectations_match else None,
            expectations_match_summary=expectations_match.get("summary") if expectations_match else "",
            error=error,
        )
        repo.insert(record)

        rl = (resume_match or {}).get("level", "")
        el = (expectations_match or {}).get("level", "")
        if rl == "High" or el == "High":
            has_high_match = True

    return {
        "file": filepath,
        "flagged": has_high_match,
        "total": len(proposals),
    }


def main():
    if len(sys.argv) < 2:
        logger.error("Usage: main.py <path-to-eml-file> [path-to-another-eml-file...]")
        sys.exit(1)

    config = load_config()
    llm = LlmClient(config)
    repo = JobRepository(config["paths"]["db"])
    repo.connect()

    for eml_path in sys.argv[1:]:
        if not Path(eml_path).exists():
            logger.warning("File not found: %s", eml_path)
            continue
        try:
            result = process_eml(eml_path, config, llm, repo)
            print(json.dumps(result))
        except Exception as e:
            logger.error("Failed to process %s: %s", eml_path, e)
            print(json.dumps({"file": eml_path, "flagged": False, "error": str(e)}))

    repo.close()


if __name__ == "__main__":
    main()
