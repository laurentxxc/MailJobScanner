#!/usr/bin/env python3
"""
Gmail IMAP scanner — polls a Gmail label for job alert emails,
processes them via the existing LLM pipeline, and marks them done.

Usage:
    python gmail_scanner.py              # single run
    python gmail_scanner.py --daemon     # poll every N seconds (from config)
"""
import argparse
import imaplib
import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

import yaml
from tqdm import tqdm

from analyzer.llm_client import LlmClient
from db.repository import JobRepository
from main import load_config, process_eml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _resolve_env_var(val: str) -> str | None:
    if val.startswith("${") and val.endswith("}"):
        key = val[2:-1]
        result = os.environ.get(key)
        if result:
            return result
        dotenv = Path(__file__).parent / "data" / "private" / ".env"
        if dotenv.exists():
            for line in dotenv.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    if k.strip() == key:
                        return v.strip()
        return None
    return val or None


def connect_gmail(gmail_cfg: dict) -> imaplib.IMAP4_SSL:
    host = gmail_cfg["imap_host"]
    port = gmail_cfg.get("imap_port", 993)
    addr = gmail_cfg["email"]
    raw_pw = gmail_cfg.get("app_password", "")
    password = _resolve_env_var(raw_pw) if raw_pw else None
    if not password:
        raise ValueError("Gmail app_password is empty. Set it in config.yaml or via ${GMAIL_APP_PASSWORD}.")
    logger.info("Connecting to %s:%d as %s", host, port, addr)
    mail = imaplib.IMAP4_SSL(host, port)
    mail.login(addr, password)
    return mail


def _apply_label(mail: imaplib.IMAP4_SSL, uid: str, done_label: str, scan_label: str) -> bool:
    try:
        typ, data = mail.uid("COPY", uid, done_label)
        if typ != "OK":
            logger.warning("COPY uid %s to '%s' failed: %s", uid, done_label, data)
            return False

        mail.select(scan_label)
        mail.uid("STORE", uid, "+FLAGS", "(\\Deleted)")
        mail.expunge()
        return True
    except Exception as e:
        logger.warning("Failed to move uid %s to '%s': %s", uid, done_label, e)
        return False


def scan_once(config: dict, gmail_cfg: dict, repo: JobRepository, llm: LlmClient, progress: bool = False) -> int:
    Path("/tmp/mailjobscan").mkdir(parents=True, exist_ok=True)

    mail = connect_gmail(gmail_cfg)
    try:
        scan_label = gmail_cfg["scan_label"]
        done_label = gmail_cfg.get("done_label", "JobScan/Done")

        status, _ = mail.select(scan_label, readonly=True)
        if status != "OK":
            logger.error("Could not select label '%s': %s", scan_label, _)
            return 0

        status, data = mail.uid("search", None, "ALL")
        if status != "OK" or not data[0]:
            logger.info("No messages found in '%s'", scan_label)
            return 0

        uids = data[0].split()
        total = len(uids)
        logger.info("Found %d messages in '%s'", total, scan_label)

        processed = 0
        skipped = 0
        start_time = time.time()

        uid_iter = tqdm(uids, unit="mail", position=0, disable=not progress, dynamic_ncols=True)
        for uid in uid_iter:
            uid_str = uid.decode()

            _, msg_data = mail.uid("fetch", uid_str, "(RFC822)")
            if not msg_data or not msg_data[0]:
                if progress:
                    tqdm.write(f"Failed to fetch uid {uid_str}")
                else:
                    logger.warning("Failed to fetch uid %s", uid_str)
                continue

            raw_email = msg_data[0][1]
            with tempfile.NamedTemporaryFile(
                suffix=".eml", delete=False, dir="/tmp/mailjobscan"
            ) as tmp:
                tmp.write(raw_email)
                tmp_path = tmp.name

            try:
                result = process_eml(tmp_path, config, llm, repo, progress=progress, bar_position=1 if progress else 0)
                if result.get("skipped"):
                    skipped += 1
                else:
                    processed += 1

                if done_label:
                    _apply_label(mail, uid_str, done_label, scan_label)

            except Exception as e:
                if progress:
                    tqdm.write(f"Failed to process uid {uid_str}: {e}")
                else:
                    logger.error("Failed to process uid %s: %s", uid_str, e)
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

            if progress:
                done = processed + skipped
                remaining = total - done
                elapsed = time.time() - start_time
                uid_iter.set_description(
                    f"Emails: {processed} done / {skipped} skip / {remaining} left | {elapsed:.0f}s"
                )

        if progress:
            uid_iter.close()

        logger.info("Scan complete: %d processed, %d skipped", processed, skipped)
        return processed

    finally:
        try:
            mail.logout()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="Gmail job alert scanner")
    parser.add_argument("--daemon", action="store_true", help="Poll continuously at configured interval")
    args = parser.parse_args()

    config = load_config()
    gmail_cfg = config.get("gmail", {})

    if not gmail_cfg.get("enabled"):
        logger.error("Gmail scanning is not enabled. Set gmail.enabled=true in config.yaml.")
        sys.exit(1)

    llm = LlmClient(config)
    repo = JobRepository(config["paths"]["db"])
    repo.connect()

    try:
        if args.daemon:
            interval = gmail_cfg.get("poll_interval_seconds", 300)
            logger.info("Starting daemon mode — polling every %d seconds", interval)
            while True:
                try:
                    scan_once(config, gmail_cfg, repo, llm)
                except Exception as e:
                    logger.error("Scan cycle failed: %s", e)
                time.sleep(interval)
        else:
            logging.getLogger().setLevel(logging.WARNING)
            scan_once(config, gmail_cfg, repo, llm, progress=True)
    finally:
        repo.close()


if __name__ == "__main__":
    main()
