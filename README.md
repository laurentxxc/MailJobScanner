# MailJobScan

Scan job alert emails from Apple Mail, extract job proposals, analyze them against your resume and expectations using a local LLM (Ollama), and flag high-matching opportunities.

## Features

- **One-click from Mail** — select emails and run from the Scripts menu
- **AI extraction** — parses job alert emails into structured proposals (title, URL, company, salary, location)
- **Automated analysis** — fetches each job description, compares it against your resume and expectations
- **Match scoring** — rates each job Low/Medium/High for both skill fit and preference fit
- **Local & private** — runs entirely on your machine via Ollama; no data leaves your Mac
- **Swappable AI** — designed so you can switch to OpenAI/Claude by changing one config line

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Apple Mail                         │
│  User selects emails → Scripts menu → mailjobscan   │
└──────────────────┬──────────────────────────────────┘
                   │ writes .eml files to /tmp/mailjobscan/
                   ▼
┌─────────────────────────────────────────────────────┐
│                   main.py                            │
│                                                      │
│  1. Parse .eml → subject, from, body + URLs         │
│  2. Send body to Ollama → list of job proposals     │
│  3. For each proposal:                              │
│     a. Fetch job URL → extract description text     │
│     b. Send description + cv.md → resume match      │
│     c. Send description + expectations.md → pref.   │
│     d. Store result in SQLite                       │
│  4. Return flag decision to AppleScript             │
└──┬───────────────────────┬──────────────────────────┘
   │                       │
   ▼                       ▼
┌──────────┐      ┌──────────────────┐
│  Ollama  │      │    SQLite DB     │
│ llama3.2 │      │  jobscan.db      │
└──────────┘      └──────────────────┘
                   │ query later via sqlite3
```

## Project Structure

```
MailJobScan/
├── config.yaml                 # LLM endpoint, model, file paths
├── main.py                     # Entry point / orchestrator
├── scanner/
│   └── email_parser.py         # .eml → plain text with URLs preserved
├── analyzer/
│   ├── llm_client.py           # Ollama API client (swap for remote)
│   └── prompts.py              # System prompts for extraction & matching
├── db/
│   ├── models.py               # JobProposalRecord dataclass
│   └── repository.py           # SQLite CRUD operations
├── data/
│   ├── cv.md                   # ← Your resume / experience (fill in)
│   └── expectations.md         # ← Your job preferences (fill in)
├── scripts/
│   ├── mailjobscan.applescript # Source for the Mail Script
│   └── install.sh              # Compiles & installs the script
└── jobscan.db                  # Auto-created on first run
```

> **Note on profile files:** `data/cv.md` and `data/expectations.md` are
> symlinks pointing into `data/private/`. The `data/private/` directory is
> gitignored — you must create your own files there after cloning.
> See `data/templates/` for demo examples to copy and adapt.

## Prerequisites

- macOS (Apple Mail + Scripts menu)
- [Ollama](https://ollama.com) installed (`brew install ollama`) with a model pulled (`ollama pull llama3.2`)
- Python 3.11+

## Setup

```bash
# 1. Navigate to the project
cd MailJobScan

# 2. Create virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Provide your personal profiles
#    data/cv.md and data/expectations.md are symlinks pointing to
#    files inside data/private/. Create your own files there:
#
#      data/private/your_resume.txt       # Your CV / experience
#      data/private/your_expectations.md  # Your job preferences
#
#    The symlinks resolve automatically when the target files exist.
#    See data/templates/ for demo examples to copy.

# 4. Verify Ollama is running with the configured model
ollama serve          # start Ollama if not already running
ollama list           # should show llama3.2 (or the model in config.yaml)

# 5. Install the Mail Script
bash scripts/install.sh

#    This compiles the AppleScript and copies it to
#    ~/Library/Scripts/Applications/Mail/mailjobscan.scpt
#    If you moved the project, update projectDir in scripts/mailjobscan.applescript first.
```

## Usage

### Via Mail Script (recommended)

1. Open **Mail.app**
2. Select one or more job alert emails
3. Click the **Scripts menu** (wrench icon in the menu bar) → **mailjobscan**
4. Wait for the "Done" dialog — each email takes ~30-60 seconds depending on the number of proposals
5. Emails with **High** match level are flagged with a yellow flag in Mail
6. All results are logged to `jobscan.db`

### Via Automator Quick Action (alternative)

If the Scripts menu isn't available, create a Quick Action:

1. Open **Automator.app** → **New Document** → **Quick Action**
2. Set **Workflow receives**: `messages` in `Mail`
3. Add a **Run AppleScript** action with the content below
4. Save as "MailJobScan"
5. Right-click selected emails → **Quick Actions** → **MailJobScan**

```applescript
on run {input, parameters}
    tell application "Mail"
        set projectDir to "/Users/lvt/Documents/Dev/MailJobScan"
        set venvPython to projectDir & "/.venv/bin/python3"
        do shell script "mkdir -p /tmp/mailjobscan"

        repeat with msg in input
            set tempFile to "/tmp/mailjobscan/" & (id of msg) & ".eml"
            do shell script "rm -f " & quoted form of tempFile
            set f to open for access tempFile with write permission
            set eof of f to 0
            write (source of msg) to f
            close access f

            set cmd to "cd " & quoted form of projectDir & " && " & venvPython & " main.py " & quoted form of tempFile
            set output to do shell script cmd
            set isFlagged to do shell script "echo " & quoted form of output & " | python3 -c \"import sys,json; d=json.load(sys.stdin); print('true' if d.get('flagged') else 'false')\""
            if isFlagged is "true" then
                set flag index of msg to 1
            end if
        end repeat

        do shell script "rm -f /tmp/mailjobscan/*.eml"
    end tell
end run
```

### Query results directly

```bash
sqlite3 jobscan.db -header -column "SELECT job_title, company, resume_match_level, expectations_match_level FROM job_proposals;"
```

### Dashboard (Streamlit)

Browse, filter, and analyze results in an interactive web dashboard:

```bash
source .venv/bin/activate
streamlit run dashboard.py
```

Opens at `http://localhost:8501` in your browser.

Features:
- **Date range filter** — last 7/30/90 days or custom period
- **Match filter** — show only high matches, medium+, or low matches
- **Color-coded table** — green (High), yellow (Medium), red (Low)
- **Detail panel** — click any proposal to see full match summaries, URL, salary, and location
- **CSV export** — download filtered results

## Workflow Diagram

```
Select email(s) in Mail
       │
       ▼
Run Scripts → mailjobscan
       │
       ▼
AppleScript writes each message to .eml file
       │
       ▼
Python parses .eml → extracts body text
       │
       ▼
Ollama extracts job proposals from email: title, URL, company, salary, location
       │
       ▼
For each proposal ──► Fetch job URL → extract description
       │                      │
       │                      ▼
       │              Ollama compares description
       │              against cv.md → resume match level + summary
       │              against expectations.md → expectations match level + summary
       │                      │
       │                      ▼
       │              Store all data in jobscan.db
       │                      │
       └──────────────────────┘
       │
       ▼
If any proposal has High match → AppleScript sets yellow flag on the email
```

## Configuration

Edit `config.yaml` to customize:

```yaml
llm:
  provider: ollama              # "openai" or "anthropic" supported
  endpoint: http://localhost:11434
  model: llama3.2               # or any model you have in Ollama
  options:
    temperature: 0.1            # low temp for consistent JSON output
    num_predict: 4096

paths:
  cv: data/cv.md
  expectations: data/expectations.md
  db: jobscan.db
  linkedin_cookies: data/private/linkedin_cookies.json         # required for fetching job on LinkedIn (see Extract LinkedIn cookies)
```

## Next Steps

### Switch to a remote LLM

The `LlmClient` class in `analyzer/llm_client.py` is designed to be subclassed. To use OpenAI:

```yaml
llm:
  provider: openai
  api_key: sk-...
  model: gpt-4o-mini
```

Then add an `OpenAIClient` subclass that implements the same `extract_job_proposals()`, `match_resume()`, and `match_expectations()` interface.

### Improve matching accuracy

- Make `data/cv.md` and `data/expectations.md` as detailed as possible — the quality of matching depends directly on these files
- Try a larger Ollama model like `mistral:7b` or `qwen2.5:7b` for better extraction and reasoning

### Scheduled scanning

Convert the manual AppleScript trigger to run periodically via `launchd` or `cron` by polling a Mail mailbox folder via IMAP directly (bypassing Mail.app).

### Extract LinkedIn Cookies

LinkedIn requires a logged-in session to view job pages. Configure your browser session cookies so the fetcher can access job descriptions behind LinkedIn's sign-in wall.

1. **Open Safari** and log into [linkedin.com](https://www.linkedin.com)
2. **Enable Developer Tools**: Safari → Settings → Advanced → check *"Show Develop menu in menu bar"*
3. **Open Web Inspector**: Develop → Show Web Inspector (or `⌥⌘I`)
4. **Go to the Storage tab** → expand *Cookies* → select `www.linkedin.com`
5. Find these two cookies and copy their values:

   | Cookie | What to look for |
   |--------|------------------|
   | `li_at` | Long base64 string (300+ chars) — the OAuth2 session token |
   | `JSESSIONID` | Short string like `ajax:123456789` — the CSRF token |

6. **Edit `data/private/linkedin_cookies.json`** (already gitignored):

   ```json
   {
       "li_at": "AQEFAHIBAAAA...",
       "JSESSIONID": "ajax:123456789"
   }
   ```

7. **Verify** by running the dashboard and clicking *Re-fetch & re-analyze* on any LinkedIn proposal — the error should clear and match results should appear.

> **Note:** If `JSESSIONID` doesn't appear in Safari's Storage tab, try first with only `li_at` — it may be sufficient for GET requests. Cookies expire approximately once per year (or when you log out); update the file when they do.

## Troubleshooting

### "Scripts menu doesn't appear in Mail"

Restart Mail.app. The Scripts menu (wrench icon) appears between the Window and Help menus if at least one script is in `~/Library/Scripts/Applications/Mail/`. If it still doesn't appear, try:

1. Open **Script Editor** → Preferences → **General** → check **"Show Script menu in menu bar"**
2. The icon now appears in the menu bar — select **Mail** from the dropdown

### "Ollama connection refused"

Ensure Ollama is running:
```bash
ollama serve
```

### "AppleScript cannot find the project"

If you moved the project directory, update `projectDir` at the top of `scripts/mailjobscan.applescript`, then recompile and reinstall:
```bash
bash scripts/install.sh
```

### "Python virtual environment not found"

Run from the project root:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### "No job proposals extracted"

- Check that `ollama serve` is running
- Verify the model in `config.yaml` matches `ollama list`
- Try a larger model — `llama3.2` (3B) can miss items in complex emails; `qwen2.5:7b` or `mistral:7b` performs better

### "Database file not found"

The `jobscan.db` file is created automatically in the project root on first run. If you see errors, verify the project root has write permissions.

### "URL fetching fails"

Some job portals block automated requests. The tool falls back from `trafilatura` to `requests` with a browser User-Agent, but very aggressive anti-scraping sites may still block it. Check the error field in the database:
```bash
sqlite3 jobscan.db "SELECT job_title, error FROM job_proposals WHERE error IS NOT NULL;"
```
