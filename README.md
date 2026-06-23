# UK Job Agent — DIY Auto-Apply System

An autonomous job application bot that finds visa-sponsor positions on LinkedIn and auto-fills ATS forms. Built as a modular 3-script system inspired by AIApply.

---

## Architecture

```
┌─────────────────┐
│  profile.json   │  Personal data (name, email, phone, CV, credentials)
└────────┬────────┘
         │
┌────────▼──────────┐
│   find_jobs.py    │  Scrapes LinkedIn → jobs_queue.csv
└────────┬──────────┘
         │
┌────────▼──────────┐
│    apply.py       │  Reads queue, applies one job at a time
└─────────────────┘
```

---

## Setup

### 1. Prerequisites

```bash
pip install playwright pdfplumber requests
playwright install chromium
```

### 2. LinkedIn Login

Run once to log in and save session:

```bash
python3 linkedin_test.py
```

This creates `./linkedin_profile/` with your saved LinkedIn session.

### 3. Profile Configuration

Edit `profile.json` with your details:

```json
{
  "name": "Your Name",
  "email": "your@email.com",
  "phone": "+44...",
  "address": "City, Country",
  "cv_path": "Your_CV.pdf",
  "right_to_work": "Yes",
  "requires_sponsorship": "Yes",
  "linkedin_email": "your@linkedin.com",
  "linkedin_password": "your_password",
  "ats_password": "your_ats_form_password"
}
```

### 4. CV Setup

Place your CV as PDF in the project folder. Update `cv_path` in `profile.json` to match.

---

## Usage

### Find Jobs

Search LinkedIn for matching positions:

```bash
# Search all major sponsors
python3 find_jobs.py

# Search one company
python3 find_jobs.py --company Barclays --limit 10

# Dry run (don't add to queue)
python3 find_jobs.py --company "HSBC" --headless
```

Creates/appends to `jobs_queue.csv`:
```
url,title,company,status
https://linkedin.com/jobs/view/12345,Application Support Engineer,Barclays,pending
```

### Apply to Jobs

Read queue and apply one-by-one:

```bash
# Dry run (see what will happen)
python3 apply.py --dry-run --one

# Apply to 1 job (real)
python3 apply.py --one

# Apply to all pending jobs
python3 apply.py

# Headless mode (no visible browser window)
python3 apply.py --headless
```

Updates queue status: `pending` → `applied` or `failed`

---

## Supported Job Boards

### LinkedIn Easy Apply
- ✅ Auto-fills multi-step form
- ✅ Auto-uploads CV
- ✅ Auto-answers "Do you have right to work?" questions
- ⚠️ May timeout on slow pages

### External ATS Platforms
- **Workday** — Detects and fills form fields automatically
- **Greenhouse** — Supported
- **Lever** — Supported
- **SmartRecruiters** — Supported
- **iCIMS** — Supported
- **Generic** — Attempts to fill common patterns

---

## Configuration

### Sponsor Companies (with LinkedIn IDs)

Edit `find_jobs.py` to add more:

```python
LINKEDIN_COMPANY_IDS = {
    "HSBC": "1557",
    "Barclays": "3529",
    "Lloyds Banking Group": "7116",
    # Add more...
}
```

### Role Keywords

In `find_jobs.py`, customize search terms:

```python
role_kws = [
    "Application Support Engineer",
    "Application Support Analyst",
    "Technical Support Engineer",
    # Add your target roles
]
```

### Hard Filters

Edit regex patterns in `find_jobs.py` to skip jobs:

```python
_TITLE_BLOCKLIST = re.compile(r"\b(devops|sre|cloud engineer)\b", re.IGNORECASE)
_NO_SPONSORSHIP = re.compile(r"(no sponsorship|right to work required)", re.IGNORECASE)
_SECURITY_CLEARANCE = re.compile(r"(sc clear|dv clear)", re.IGNORECASE)
```

---

## Outputs

### Logs

- **`jobs_queue.csv`** — Job queue with status (pending/applied/failed)
- **`applications.csv`** — Full application log with timestamps and ATS type
- **`hunt_results/`** — Detailed results from scoring runs

### ATS Accounts

New accounts created during applications are saved to:
- **`ats_accounts.csv`** — Domain, email, password, timestamp

---

## Known Issues & Errors Handled

### 1. **Browser Profile Locked** ❌

**Error:** `Opening in existing browser session` or `SingletonLock` issues

**Cause:** Previous Chrome process wasn't cleanly killed

**Fix (automatic):** Scripts kill Chrome before launch:
```bash
pkill -9 -f "Google Chrome for Testing"
pkill -9 -f "chrome for testing"
sleep 2
rm -f ./linkedin_profile/SingletonLock
rm -f ./linkedin_profile/SingletonSocket
rm -f ./linkedin_profile/SingletonCookie
```

**Status:** ✅ **Handled** — All scripts auto-kill Chrome and remove locks on startup

---

### 2. **Not Logged Into LinkedIn** ❌

**Error:** `Page.goto` redirects to `linkedin.com/login`

**Cause:** Session expired or `linkedin_profile/` directory deleted

**Fix:**
```bash
python3 linkedin_test.py  # Re-login
```

**Status:** ✅ **Handled** — Scripts detect login redirect and exit gracefully

---

### 3. **Job Scraper Returns 0 Results** ❌

**Error:** Found 0 jobs even for known sponsors

**Cause:**
- LinkedIn algorithm limited results
- Company ID not found in `LINKEDIN_COMPANY_IDS`
- Search terms too narrow
- Rate-limited by LinkedIn

**Fix:**
```bash
# Try different role keywords
python3 find_jobs.py --company Barclays

# Try generic search (no company filter)
python3 find_jobs.py

# Add delay between searches (default: 0.5-1.5s)
```

**Status:** ✅ **Handled** — Returns gracefully if no jobs found; no crash

---

### 4. **ATS Form Filling Fails** ⚠️

**Error:** `✗ FAILED` on apply attempt

**Cause:**
- Form selectors changed (LinkedIn updates HTML frequently)
- ATS not recognized
- Required fields not found
- File upload timeout

**Status:** ⚠️ **Partially Handled** — Detects failures but form selectors need manual tuning

**Debug:**
```bash
# Run with visible browser to watch form filling
python3 apply.py --one  # (no --headless)
```

---

### 5. **LinkedIn Easy Apply Timeout** ❌

**Error:** Form step takes >30s to load

**Cause:**
- LinkedIn server slow
- Page has heavy JS
- Network latency

**Status:** ✅ **Handled** — Timeout set to 15s; increased to 60s on retry

---

### 6. **Rate Limiting / Bot Detection** ⚠️

**Symptoms:**
- Searches return 0 results on 2nd+ runs
- LinkedIn shows "unusual activity" warning
- CAPTCHA appears

**Cause:** Too many requests in short time

**Status:** ⚠️ **Partially Handled** — Random delays (0.5-1.5s) between searches; no proxy rotation yet

**Fix:**
```bash
# Increase delays manually
# Edit find_jobs.py:  _delay(0.5, 1.0) → _delay(3.0, 5.0)
# Run less frequently (daily, not continuous)
```

---

### 7. **CV Upload Not Triggering Autofill** ⚠️

**Symptom:** ATS accepts CV but doesn't auto-fill fields

**Cause:** Some ATS require form interaction before parsing CV

**Status:** ✅ **Handled** — Wait 2-3s after upload before filling fields

---

### 8. **Workday "Unauthorized" After Registration** ❌

**Error:** Login fails even with correct password after account creation

**Cause:** Workday doesn't accept auto-filled passwords on first login

**Status:** ⚠️ **Workaround Available** — Can pause for manual login with `input()` prompt

---

### 9. **Duplicate Applications** ⚠️

**Symptom:** Same job applied twice

**Cause:**
- Job URL formats differ (utm params, job ID vs full URL)
- Dedup cache corrupted

**Status:** ✅ **Handled** — Dedup by full URL + bare job ID (numeric)

---

### 10. **CSV Header Mismatch** ❌

**Error:** `KeyError: 'url'` when reading `jobs_queue.csv`

**Cause:** Manually edited CSV, removed headers, or file corrupted

**Status:** ✅ **Handled** — Scripts tolerate missing headers; recreate if needed:
```bash
rm jobs_queue.csv
python3 find_jobs.py --company Barclays --limit 5
```

---

### 11. **Playwright Timeout on Page Load** ❌

**Error:** `Page.goto: Target page, context or browser has been closed`

**Cause:** Browser crashed mid-navigation

**Status:** ✅ **Handled** — Try/except wraps all page navigation; logs error and skips job

---

### 12. **"Element Not Interactable" on Form Field** ❌

**Error:** Click/fill fails — element exists but not visible/enabled

**Cause:**
- Element hidden behind modal
- Page still loading
- Element visibility set to `display: none`

**Status:** ✅ **Handled** — Locators include wait states; retry on failure

---

### 13. **File Upload Selector Mismatch** ❌

**Error:** CV upload fails; `input[type=file]` not found

**Cause:** ATS uses custom upload widget (not standard HTML input)

**Status:** ⚠️ **Partially Handled** — Standard input selector works for Workday/Greenhouse; custom ATS need manual fixes

---

### 14. **Screening Questions Not Answered** ⚠️

**Symptom:** Form validation fails; "Sponsorship" field required

**Cause:** Question text doesn't match regex patterns

**Status:** ✅ **Handled** — Regex patterns cover common variations:
- "right to work", "eligible to work", "need sponsorship", "visa sponsorship"
- Answer: Always "Yes"

---

### 15. **LinkedIn Profile Corruption** ❌

**Error:** Scripts behave oddly; session acts logged-out despite valid creds

**Cause:** `./linkedin_profile/` directory partially deleted or corrupted

**Status:** ✅ **Handled** — Run `python3 linkedin_test.py` to refresh session

---

## Potential Future Errors

### 16. **LinkedIn Blocks Persistent Context** 🚀

**Risk Level:** Medium (LinkedIn periodically hardens bot detection)

**Mitigation:**
- [ ] Add proxy rotation
- [ ] Vary user agent per session
- [ ] Add random delays (already done)
- [ ] Monitor for CAPTCHA, pause if detected
- [ ] Switch to Chrome extension approach (manual for now)

---

### 17. **ATS Requires Email Verification** 🚀

**Risk Level:** Medium (many ATS send verification links)

**Mitigation:**
- [ ] Parse verification email from Gmail API
- [ ] Click link automatically
- [ ] Or pause for user to verify manually

---

### 18. **Security Clearance Bypass Attempts** 🚀

**Risk Level:** High (applying for SC/DV jobs violates UK law if you don't qualify)

**Mitigation:**
- [ ] Regex blocks SC/DV in descriptions (already done)
- [ ] BPSS allowed (you qualify with 3+ years UK residency)
- [ ] Never auto-answer clearance questions

---

## Troubleshooting Checklist

Before running, verify:

- [ ] LinkedIn logged in? `python3 linkedin_test.py`
- [ ] `profile.json` correct? Check all fields, especially CV path
- [ ] CV file exists? `ls Faizan_Fayyaz_KYNDRYL.pdf`
- [ ] Python packages installed? `pip list | grep -E "playwright|pdfplumber"`
- [ ] Chrome not running? `pkill -9 chromium`
- [ ] Browser profile not locked? `ls ./linkedin_profile/SingletonLock`
- [ ] Queue file valid? `head -2 jobs_queue.csv`
- [ ] Run without `--headless` to watch browser?

---

## License

MIT

---

## Author

Faizan Fayyaz — Senior IT Infrastructure Engineer, Portsmouth UK

---

## Support

For issues, check the **Known Issues & Errors Handled** section above first.

For LinkedIn authentication: `python3 linkedin_test.py`

For ATS form issues: Inspect with browser DevTools, update selectors in `apply.py`
