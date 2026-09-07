#!/usr/bin/env python3
"""Shared configuration loading and environment resolution.

Consolidates config logic previously duplicated across main.py, dashboard.py,
gmail_scanner.py, analyzer/llm_client.py and analyzer/commute.py.
"""
import json
import logging
import os
import sys
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent


def load_config() -> dict:
    config_path = ROOT / "config.yaml"
    if not config_path.exists():
        logger.error("config.yaml not found at %s", config_path)
        sys.exit(1)
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def resolve_env_var(val: str) -> str | None:
    if not (val.startswith("${") and val.endswith("}")):
        return val or None
    key = val[2:-1]
    result = os.environ.get(key)
    if result:
        return result
    dotenv = ROOT / "__private__" / ".env"
    if dotenv.exists():
        for line in dotenv.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                if k.strip() == key:
                    return v.strip()
    return None


def load_linkedin_cookies(config: dict | None = None) -> dict:
    if config is None:
        config = load_config()
    cookie_rel = config.get("paths", {}).get(
        "linkedin_cookies", "__private__/linkedin_cookies.json"
    )
    cookie_path = ROOT / cookie_rel
    if not cookie_path.exists():
        return {}
    try:
        with open(cookie_path, "r") as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if isinstance(v, str) and v.strip()}
    except Exception as e:
        logger.warning("Failed to load LinkedIn cookies: %s", e)
        return {}
