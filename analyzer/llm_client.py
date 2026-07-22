import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

import requests

from analyzer.prompts import (
    EXTRACTION_SYSTEM_PROMPT,
    RESUME_MATCH_PROMPT,
    EXPECTATIONS_MATCH_PROMPT,
    JOB_SUMMARY_PROMPT,
    build_extraction_user_prompt,
    build_match_user_prompt,
    build_summary_user_prompt,
    restore_urls,
    shorten_urls,
)

logger = logging.getLogger(__name__)


class LlmClient:
    def __init__(self, config: dict):
        llm_cfg = config["llm"]
        self.provider = llm_cfg.get("provider", "ollama")
        self.endpoint = llm_cfg["endpoint"].rstrip("/")
        self.model = llm_cfg["model"]
        self.options = llm_cfg.get("options", {})
        raw_key = llm_cfg.get("api_key", "")
        self.api_key = self._resolve_env_var(raw_key) if raw_key else None
        self._cv: Optional[str] = None
        self._expectations: Optional[str] = None
        self._load_documents(config["paths"])

    @staticmethod
    def _resolve_env_var(val: str) -> str | None:
        if val.startswith("${") and val.endswith("}"):
            key = val[2:-1]
            result = os.environ.get(key)
            if result:
                return result
            dotenv = Path(__file__).parent.parent / "data" / "private" / ".env"
            if dotenv.exists():
                for line in dotenv.read_text().splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        if k.strip() == key:
                            return v.strip()
            return None
        return val or None

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
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        if self.provider == "ollama":
            payload = {
                "model": self.model,
                "messages": messages,
                "format": "json",
                "options": self.options,
                "stream": False,
            }
            resp = requests.post(f"{self.endpoint}/api/chat", json=payload, timeout=120)
        else:
            if self.api_key:
                time.sleep(4)
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": self.options.get("temperature", 0.1),
                "max_tokens": self.options.get("num_predict", 4096),
                "stream": False,
            }
            if any(domain in self.endpoint for domain in ("groq.com", "openai.com","api.x.ai")):
                payload["response_format"] = {"type": "json_object"}

            for attempt in range(2):
                resp = requests.post(
                    f"{self.endpoint}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=120,
                )
                if resp.status_code == 429 and attempt == 0:
                    logger.warning("Rate limited, retrying after 5s...")
                    time.sleep(5)
                    continue
                resp.raise_for_status()
                break

        resp.raise_for_status()
        body = resp.json()

        if self.provider == "ollama":
            raw = body["message"]["content"]
        else:
            raw = body["choices"][0]["message"]["content"]

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Try extracting JSON from markdown code fences
            import re
            match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', raw, re.DOTALL)
            if match:
                return json.loads(match.group(1))
            raise
        
    def extract_job_proposals(self, email_body: str) -> list[dict]:
        shortened, url_map = shorten_urls(email_body)
        user = build_extraction_user_prompt(shortened)
        try:
            result = self._chat(EXTRACTION_SYSTEM_PROMPT, user)
            jobs = []
            if isinstance(result, dict):
                for key in ("jobs", "proposals", "results", "items"):
                    if key in result and isinstance(result[key], list):
                        jobs = result[key]
                        break
            elif isinstance(result, list):
                jobs = result
            else:
                jobs = [result] if isinstance(result, dict) else []
            if url_map:
                jobs = restore_urls(jobs, url_map)
            return jobs
        except Exception as e:
            logger.error("Failed to extract job proposals: %s", e)
            return []

    def match_resume(self, job_description: str) -> dict[str, Any]:
        user = build_match_user_prompt(job_description, "resume", self._cv or "")
        return self._chat(RESUME_MATCH_PROMPT, user)

    def match_expectations(self, job_description: str, commute_info: str = "") -> dict[str, Any]:
        user = build_match_user_prompt(job_description, "expectations", self._expectations or "", commute_info)
        return self._chat(EXPECTATIONS_MATCH_PROMPT, user)

    def summarize_job(self, job_description: str) -> dict[str, Any]:
        user = build_summary_user_prompt(job_description)
        return self._chat(JOB_SUMMARY_PROMPT, user)
