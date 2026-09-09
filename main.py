#!/usr/bin/env python3
"""CLI entry point: process .eml files through the analysis pipeline.

Reads job alert emails, extracts job proposals via the LLM, fetches job
descriptions, scores them, and writes results to SQLite. Outputs a
{"flagged": bool} JSON line per file for AppleScript to consume.
"""
import argparse
import json
import logging
from pathlib import Path

from config import load_config
from core.engine import process_eml
from core.llm.llm_client import LlmClient
from core.storage.repository import JobRepository

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


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
