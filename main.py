#!/usr/bin/env python3
import argparse
import json
import logging
import re
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import trafilatura
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

from analyzer.llm_client import LlmClient
from analyzer.commute import get_commute_info
from config import load_config, load_linkedin_cookies
from db.models import JobProposalRecord
from db.repository import JobRepository
from scanner.email_parser import parse_eml

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


def fetch_job_description(url: str) -> str | None:
    # Normalize LinkedIn tracking URLs to clean job view URLs.
    # /comm/jobs/view/ tracking links redirect to a hard sign-in wall,
    # while /jobs/view/ renders content behind the sign-in.
    normalized = url
    parsed = urllib.parse.urlparse(url)
    if "linkedin.com" in parsed.netloc and "/comm/jobs/view/" in parsed.path:
        clean_path = parsed.path.replace("/comm/jobs/view/", "/jobs/view/")
        normalized = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, clean_path, "", "", ""))
        if normalized != url:
            logger.info("Normalized LinkedIn tracking URL for fetch: %s", normalized)

    # Load LinkedIn session cookies (li_at + JSESSIONID) for authenticated access
    # Export from Safari Developer Tools → Storage → Cookies → www.linkedin.com
    cookies = None
    if "linkedin.com" in parsed.netloc:
        cookies = load_linkedin_cookies()
        if cookies:
            logger.info("Using LinkedIn session cookies for authenticated fetch")

    # Skip trafilatura for cookie-authenticated requests (it doesn't support cookies)
    text = None
    try:
        if not cookies:
            downloaded = trafilatura.fetch_url(normalized)
            if downloaded:
                text = trafilatura.extract(downloaded)
        if not text:
            resp = requests.get(
                normalized,
                timeout=15,
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
                cookies=cookies or None,
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
    except Exception as e:
        logger.warning("Failed to fetch URL %s: %s", url, e)

    if text and not is_login_page(text, url):
        return text

    return text

_LOGIN_SIGNALS = ["sign in", "log in", "create account", "forgot password", "password"]

def is_login_page(text: str, url: str = "") -> bool:
    if len(text) < 300:
        return True
    lower = text.lower()
    count = sum(1 for s in _LOGIN_SIGNALS if s in lower)
    if "linkedin.com" in url.lower() and "sign in" in lower:
        return True
    return count >= 3

def _match_resume_and_expectations(llm: LlmClient, jd_text: str, commute_info: str = "") -> tuple[dict, dict]:
    """Run match_resume and match_expectations in parallel."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        resume_fut = pool.submit(llm.match_resume, jd_text)
        expectations_fut = pool.submit(llm.match_expectations, jd_text, commute_info)
        resume_match = resume_fut.result()
        expectations_match = expectations_fut.result()
    return resume_match, expectations_match


def refetch_single_job(url: str, llm: LlmClient, config: dict | None = None) -> dict:
    jd_text = fetch_job_description(url) if url else None
    if not jd_text:
        return {"error": f"Could not fetch job description from {url}" if url else "No URL",
                "resume_match_level": None, "resume_match_summary": "",
                "expectations_match_level": None, "expectations_match_summary": ""}
    if is_login_page(jd_text, url):
        return {"error": f"Login page detected at {url}",
                "resume_match_level": None, "resume_match_summary": "",
                "expectations_match_level": None, "expectations_match_summary": ""}

    job_summary = None
    try:
        job_summary = llm.summarize_job(jd_text)
    except Exception as e:
        job_summary = None

    commute_info = ""
    if config and config.get("commute", {}).get("enabled"):
        commute_cfg = config["commute"]
        job_location = job_summary.get("location", "") if job_summary else ""
        commute_info = get_commute_info(
            commute_cfg["home_address"],
            job_location,
            commute_cfg.get("api_key", ""),
            commute_cfg.get("profile", "driving-car"),
        )

    resume_match = expectations_match = None
    try:
        resume_match, expectations_match = _match_resume_and_expectations(llm, jd_text, commute_info)
    except Exception as e:
        resume_match = {"level": "Error", "summary": str(e)}
        expectations_match = {"level": "Error", "summary": str(e)}

    return {
        "error": None,
        "resume_match_level": resume_match.get("level") if resume_match else None,
        "resume_match_summary": resume_match.get("summary", "") if resume_match else "",
        "expectations_match_level": expectations_match.get("level") if expectations_match else None,
        "expectations_match_summary": expectations_match.get("summary", "") if expectations_match else "",
        "job_responsibilities_summary": job_summary.get("responsibilities", "") if job_summary else "",
        "job_requirements_summary": job_summary.get("requirements", "") if job_summary else "",
        "job_technology_domains": job_summary.get("technology_domains", "") if job_summary else "",
        "commute_info": commute_info,
        "title": job_summary.get("title", "") if job_summary else "",
        "company": job_summary.get("company", "") if job_summary else "",
        "salary": job_summary.get("salary", "") if job_summary else "",
        "location": job_summary.get("location", "") if job_summary else "",
    }

def process_eml(filepath: str, config: dict, llm: LlmClient, repo: JobRepository, dry_run: bool = False, progress: bool = False, bar_position: int = 0) -> dict:
    email_data = parse_eml(filepath)

    message_id = email_data.get("message_id", "")
    if not dry_run and message_id and repo.has_message_id(message_id):
        logger.info("Skipping %s — already processed (message_id=%s)", filepath, message_id)
        return {"file": filepath, "flagged": False, "total": 0, "skipped": True}

    logger.info("Processing: %s", email_data["subject"])

    proposals = llm.extract_job_proposals(email_data["body"])
    if not proposals:
        logger.info("No job proposals found in email")
        return {"file": filepath, "flagged": False, "total": 0}

    logger.info("Found %d proposals", len(proposals))
    has_high_match = False
    errors = 0
    loop_start = time.time()

    prop_iter = tqdm(proposals, unit="job", position=bar_position, leave=False,
                     disable=not progress, dynamic_ncols=True)
    for prop in prop_iter:
        title = prop.get("title", "Unknown")
        url = prop.get("url", "")
        company = prop.get("company", "Unknown")
        salary = prop.get("salary", "Unknown")
        location = prop.get("location", "Unknown")

        jd_text = None
        job_summary = None
        resume_match = None
        expectations_match = None
        error = None
        commute_info = ""

        if url:
            jd_text = fetch_job_description(url)
            if jd_text and is_login_page(jd_text, url):
                logger.info("Login page detected for '%s' at %s", title, url)
                error = f"Login page detected at {url}"
                jd_text = None
            if jd_text:
                try:
                    job_summary = llm.summarize_job(jd_text)
                    logger.info("Job summary for '%s': responsibilities extracted", title)
                except Exception as e:
                    logger.warning("Job summary failed for '%s': %s", title, e)

                if job_summary:
                    if job_summary.get("title") and job_summary["title"] != title:
                        logger.info("Title corrected: '%s' → '%s'", title, job_summary["title"])
                        title = job_summary["title"]
                    if job_summary.get("company"):
                        company = job_summary["company"]
                    if job_summary.get("salary"):
                        salary = job_summary["salary"]
                    if job_summary.get("location"):
                        location = job_summary["location"]

                if config.get("commute", {}).get("enabled"):
                    commute_cfg = config["commute"]
                    commute_info = get_commute_info(
                        commute_cfg["home_address"],
                        location,
                        commute_cfg.get("api_key", ""),
                        commute_cfg.get("profile", "driving-car"),
                    )

                try:
                    resume_match, expectations_match = _match_resume_and_expectations(
                        llm, jd_text, commute_info
                    )
                    logger.info("Resume match for '%s': %s", title, resume_match.get("level", "?"))
                    logger.info(
                        "Expectations match for '%s': %s",
                        title,
                        expectations_match.get("level", "?"),
                    )
                except Exception as e:
                    logger.warning("Match failed for '%s': %s", title, e)
                    resume_match = {"level": "Error", "summary": str(e)}
                    expectations_match = {"level": "Error", "summary": str(e)}
            else:
                error = f"Could not fetch job description from {url}"
        else:
            error = "No URL provided for this proposal"

        notes = ""
        dup_status = None

        if not dry_run:
            dup = repo.find_last_duplicate(company, title)
            if dup:
                dup_id, dup_status, dup_created_at = dup
                notes = f"duplicate of {dup_id} (created at {dup_created_at})"
                logger.info("Duplicate of record %d for '%s' at %s", dup_id, title, company)

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
                job_responsibilities_summary=job_summary.get("responsibilities", "") if job_summary else "",
                job_requirements_summary=job_summary.get("requirements", "") if job_summary else "",
                job_technology_domains=job_summary.get("technology_domains", "") if job_summary else "",
                commute_info=commute_info,
                error=error,
                notes=notes,
                status=dup_status or "new",
                message_id=email_data.get("message_id", ""),
            )
            repo.insert(record)
        else:
            logger.info("Dry run — skipping DB insert for '%s'", title)

        rl = (resume_match or {}).get("level", "")
        el = (expectations_match or {}).get("level", "")
        if rl == "High" and el == "High":
            has_high_match = True

        if error:
            errors += 1

        if progress:
            done = prop_iter.n + 1
            elapsed = time.time() - loop_start
            prop_iter.set_description(
                f"Jobs: {done} done / {errors} err / {len(proposals) - done} left | {elapsed:.0f}s"
            )

    if progress:
        prop_iter.close()

    return {
        "file": filepath,
        "flagged": has_high_match,
        "total": len(proposals),
    }


def main():
    parser = argparse.ArgumentParser(description="Process .eml files for job proposals")
    parser.add_argument("eml_files", nargs="+", help="Path(s) to .eml files")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run full LLM analysis but skip DB insert")
    args = parser.parse_args()

    config = load_config()
    llm = LlmClient(config)
    repo = JobRepository(config["paths"]["db"])
    repo.connect()

    for eml_path in args.eml_files:
        if not Path(eml_path).exists():
            logger.warning("File not found: %s", eml_path)
            continue
        try:
            result = process_eml(eml_path, config, llm, repo, dry_run=args.dry_run, progress=True)
            print(json.dumps(result))
        except Exception as e:
            logger.error("Failed to process %s: %s", eml_path, e)
            print(json.dumps({"file": eml_path, "flagged": False, "error": str(e)}))

    repo.close()


if __name__ == "__main__":
    main()
