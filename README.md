# UK Job Agent 🤖

An autonomous LinkedIn job application bot for UK Skilled Worker visa sponsorship roles. It searches LinkedIn, scores every job against your CV and preferences using Claude AI, tailors your CV per application, and submits — fully automatically for Easy Apply, semi-automatically for external ATS (Workday, Greenhouse, Lever, etc.).

---

## How It Works

```
Phase 0  →  Claude reads your CV + MasterPrompt → generates targeted search queries
Phase 1  →  Searches LinkedIn with those queries, collects job URLs
Phase 2  →  Scrapes each job page (title, company, description)
Phase 3  →  Scores all jobs in parallel with Claude Haiku (fast + cheap)
Phase 4  →  Ranks jobs, shows table — applies to top N automatically
Phase 5  →  Easy Apply: fully automatic
             External ATS: auto-fills, pauses for your login + final review
```

---

## Project Structure

```
UKJobAgent/
├── hunt.py                  # Main script — full autonomous hunt + apply
├── apply_job.py             # Apply to a single job URL
├── auto_apply.py            # Job queue engine (CSV-based pipeline)
├── linkedin_apply.py        # LinkedIn Easy Apply automation module
├── linkedin_scraper.py      # LinkedIn job scraper (standalone)
├── linkedin_test.py         # One-time login to save browser session
├── MasterPrompt.txt         # Your job preferences, scoring rules, sponsorship logic
├── Faizan_Fayyaz_KYNDRYL.pdf  # Your CV (source of truth)
├── .env                     # API keys and config (not committed)
├── jobs_queue.csv           # Job queue (used by auto_apply.py)
├── applications.csv         # Log of all submitted applications
├── tailored_cvs/            # Generated tailored CVs per application
└── hunt_results/            # Ranked job CSVs from each hunt run
```

---

## Setup

### 1. Install dependencies

```bash
python -m pip install playwright pdfplumber python-docx docx2pdf requests python-dotenv
python -m playwright install chromium
```

### 2. Create `.env` file

```env
CLAUDE_API_KEY=your_anthropic_api_key_here
CV_PATH=Faizan_Fayyaz_KYNDRYL.pdf
LINKEDIN_PROFILE_DIR=./linkedin_profile
```

### 3. Log in to LinkedIn once

```bash
python linkedin_test.py
```

Log in manually in the browser that opens, then press Enter. Your session is saved to `linkedin_profile/` — you won't need to log in again.

---

## Usage

### Full autonomous hunt (recommended)

```bash
python hunt.py
```

Searches LinkedIn, scores all jobs, applies to top 20 automatically.

```bash
python hunt.py --score-only          # Score and rank, don't apply yet
python hunt.py --top 10              # Apply to top 10 instead of 20
python hunt.py --min-score 65        # Only apply if score >= 65 (default: 60)
python hunt.py --limit 25            # Collect more jobs per search term
python hunt.py --searches 30         # Generate 30 search queries instead of 20
```

### Apply to a single job

```bash
python apply_job.py "https://www.linkedin.com/jobs/view/1234567890"
python apply_job.py "https://www.linkedin.com/jobs/view/1234567890" --dry-run   # analyse only
python apply_job.py "https://www.linkedin.com/jobs/view/1234567890" --skip-cv   # use original CV
```

---

## Scoring Formula

Defined in `MasterPrompt.txt` — Claude scores each job on five dimensions:

| Dimension | Weight |
|---|---|
| Role Alignment | 30% |
| Technology Match | 25% |
| Sponsorship Probability | 25% |
| Salary Probability | 10% |
| Company Quality | 10% |

**APPLY** if final score ≥ 60. **SKIP** otherwise.

Hard skips regardless of score:
- "No sponsorship", "cannot sponsor", "right to work required"
- Salary clearly below £45,000
- Outside United Kingdom
- Excluded companies (Citi, Morgan Stanley)

---

## What Happens Per Application

### LinkedIn Easy Apply
Fully automatic — no input needed:
1. Clicks Easy Apply
2. Uploads tailored CV (generated per job)
3. Fills all form fields (phone, salary, notice period, work auth, sponsorship)
4. Clicks Next → Review → Submit

### External ATS (Workday, Greenhouse, Lever, iCIMS, etc.)
Semi-automatic — two pauses:
1. **Login pause** — if the ATS shows a login page, it pauses and waits for you to log in
2. **Review pause** — before final Submit, pauses so you can check the filled form
3. Type `skip` at either pause to move to the next job

---

## CV Tailoring

For every job that passes scoring, Claude Sonnet:
- Rewrites the professional summary for that specific role
- Rewrites key achievement bullets to match the job description keywords
- Generates a tailored cover letter
- Highlights the most relevant skills

The tailored CV is saved as a DOCX (and PDF if Microsoft Word is available) in `tailored_cvs/`.

---

## Logs

- **`applications.csv`** — every application with timestamp, company, title, score, status, CV path
- **`hunt_results/ranked_YYYYMMDD_HHMM.csv`** — full ranked list from each run including all scores and reasons

---

## MasterPrompt

`MasterPrompt.txt` controls everything:
- Which roles to target (Application Support, Production Support, SWIFT, etc.)
- Which companies to prioritise (HSBC, Barclays, Kyndryl, Accenture, etc.)
- Which to exclude (Citi, Morgan Stanley)
- Sponsorship rules
- Salary minimum (£45,000)
- Scoring weights

Edit this file to change your job search strategy — no code changes needed.

---

## Requirements

- Python 3.9+
- Anthropic API key (Claude)
- LinkedIn account
- macOS / Linux (Windows untested)
