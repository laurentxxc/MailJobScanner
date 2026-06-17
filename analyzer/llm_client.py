import json
import logging
from pathlib import Path
from typing import Any, Optional

import requests

from analyzer.prompts import (
    EXTRACTION_SYSTEM_PROMPT,
    RESUME_MATCH_PROMPT,
    EXPECTATIONS_MATCH_PROMPT,
    build_extraction_user_prompt,
    build_match_user_prompt,
)

logger = logging.getLogger(__name__)


class LlmClient:
    def __init__(self, config: dict):
        llm_cfg = config["llm"]
        self.endpoint = llm_cfg["endpoint"].rstrip("/")
        self.model = llm_cfg["model"]
        self.options = llm_cfg.get("options", {})
        self._cv: Optional[str] = None
        self._expectations: Optional[str] = None
        self._load_documents(config["paths"])

    def _load_documents(self, paths: dict):
        cv_path = Path(paths["cv"])
        exp_path = Path(paths["expectations"])
        if cv_path.exists():
            self._cv = cv_path.read_text(encoding="utf-8")
        else:
            self._cv = ""
            logger.warning("CV file not found at %s", cv_path)
        if exp_path.exists():
            self._expectations = exp_path.read_text(encoding="utf-8")
        else:
            self._expectations = ""
            logger.warning("Expectations file not found at %s", exp_path)

    def _chat(self, system: str, user: str) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "format": "json",
            "options": self.options,
            "stream": False,
        }
        resp = requests.post(f"{self.endpoint}/api/chat", json=payload, timeout=120)
        resp.raise_for_status()
        body = resp.json()
        raw = body["message"]["content"]
        return json.loads(raw)

    def extract_job_proposals(self, email_body: str) -> list[dict]:
        user = build_extraction_user_prompt(email_body)
        try:
            result = self._chat(EXTRACTION_SYSTEM_PROMPT, user)
            if isinstance(result, dict):
                for key in ("jobs", "proposals", "results", "items"):
                    if key in result and isinstance(result[key], list):
                        return result[key]
            if isinstance(result, list):
                return result
            return [result] if isinstance(result, dict) else []
        except Exception as e:
            logger.error("Failed to extract job proposals: %s", e)
            return []

    def match_resume(self, job_description: str) -> dict[str, Any]:
        user = build_match_user_prompt(job_description, "resume", self._cv or "")
        return self._chat(RESUME_MATCH_PROMPT, user)

    def match_expectations(self, job_description: str) -> dict[str, Any]:
        user = build_match_user_prompt(job_description, "expectations", self._expectations or "")
        return self._chat(EXPECTATIONS_MATCH_PROMPT, user)
