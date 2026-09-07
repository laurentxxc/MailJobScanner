# AGENTS.md

## What this is

Python macOS tool: reads job alert emails from Apple Mail, extracts job proposals via LLM, fetches job descriptions, scores them against your resume and preferences, stores results in SQLite, and flags high-matching emails.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Requires Python 3.11+ and an LLM backend (Ollama or LM Studio running locally). macOS is needed for Apple Mail integration; Gmail scanning works on any platform.

## Running

- **Scan emails (AppleScript):** `python main.py /path/to/email.eml` (takes .eml files, outputs JSON to stdout)
- **Scan emails (Gmail IMAP):** `python gmail_scanner.py` (single run) or `python gmail_scanner.py --daemon` (polls every N seconds)
- **Dashboard:** `source .venv/bin/activate && streamlit run dashboard.py` (opens at localhost:8501)
- **Dashboard shortcut:** double-click `MacOS/MailJobScan.command` (uses `MacOS/launcher.py` internally)
- **Install AppleScript:** `bash MacOS/Scripts/install.sh` (compiles + copies to `~/Library/Scripts/Applications/Mail/`)

## No test/lint/typecheck

This project has no tests, linter, or type checker configured. There is no CI. If you add code, verify it manually via the LLM and dashboard.

## Critical gotchas

- **`data/cv.md` and `data/expectations.md` are symlinks** pointing into `data/private/` (gitignored). After cloning, create your own files in `data/private/` or the symlinks will be broken and the LLM will get empty context. Templates exist in `data/templates/`.
- **`jobscan.db` is gitignored** and auto-created on first run.
- **`config.yaml` is the source of truth** for which LLM provider is active. Copy `config.example.yaml` to `config.yaml` and adjust, or point `config.yaml` (a symlink) at your own private config. Current config points to `lmstudio` (not ollama as README sometimes implies).
- **LinkedIn jobs require cookies** in `data/private/linkedin_cookies.json` (`li_at` + `JSESSIONID` from Safari). Without them, LinkedIn job pages return login walls.
- **AppleScript has a hardcoded `projectDir`** at the top of `MacOS/Scripts/mailjobscan.applescript`. If you move the project, edit that path and re-run `MacOS/Scripts/install.sh`.
- **Gmail scanning requires an App Password** in `config.yaml` `gmail.app_password` (or env var `${GMAIL_APP_PASSWORD}`). Enable 2FA on your Google account first, then generate the App Password at https://myaccount.google.com/apppasswords.
- **Gmail dedup uses two mechanisms**: `Message-ID` stored in the `message_id` column of `job_proposals`, AND a `JobScan/Done` Gmail label applied after processing. The DB check is the primary guard; the label is a secondary marker visible in Gmail UI.
- **Gmail IMAP labels must not contain spaces** — Python's `imaplib` doesn't quote arguments, so labels with spaces cause `BAD` errors on COPY/STORE. Use CamelCase (e.g. `RechercheEmploi/JobAlerts`).

## Architecture (non-obvious)

- `main.py` is the CLI orchestrator. It parses .eml, calls LLM for extraction, fetches job URLs, calls LLM for matching, writes to SQLite, returns `{"flagged": bool}` JSON to stdout for AppleScript to consume.
- `analyzer/llm_client.py` handles all LLM calls. It auto-detects Ollama vs OpenAI-compatible APIs based on `config.yaml` `llm.provider`. Rate-limited providers (Groq, OpenAI, xAI) get `response_format: json_object`. There's a 4-second sleep before non-Ollama API calls.
- `analyzer/prompts.py` contains URL shortening logic: long URLs in emails are replaced with `http://placeholder/track/N` before sending to the LLM to reduce token usage, then restored after extraction.
- `db/repository.py` handles schema migrations inline via `ALTER TABLE ADD COLUMN` with silent error swallowing — this is intentional for incremental schema evolution.
- `dashboard.py` imports `refetch_single_job` from `main.py` — changing `main.py`'s function signatures will break the dashboard.
- The Streamlit dashboard uses `@st.cache_data(ttl=60)` — data refreshes every 60 seconds at most.
- The LLM client supports env var resolution in `api_key`: values like `${SOME_KEY}` are resolved from the environment or from `data/private/.env`.
- `gmail_scanner.py` is a cross-platform alternative to the AppleScript trigger. It connects to Gmail via IMAP, searches a configurable label (default "RechercheEmploi/JobAlerts"), checks the DB for already-processed `Message-ID`s, reuses `process_eml()` from `main.py` for the actual LLM work, and applies a `RechercheEmploi/ScannedJobs` label as a secondary dedup marker.
