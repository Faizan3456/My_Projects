"""
LinkedIn Easy Apply automation using Playwright + persistent browser profile.
The profile at ./linkedin_profile must already have a valid LinkedIn session
(run linkedin_test.py once to log in and save it).
"""

import os
import re
import time
import random
import datetime
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
except ImportError:
    sync_playwright = None
    PlaywrightTimeoutError = Exception

PROFILE_DIR = os.getenv("LINKEDIN_PROFILE_DIR", "./linkedin_profile")
CV_PDF_PATH = os.getenv("CV_PATH", "/Users/faizansmac/UKJobAgent/Faizan_Fayyaz_KYNDRYL.pdf")

# Human-like delay helpers
def _delay(lo=0.4, hi=1.2):
    time.sleep(random.uniform(lo, hi))

def _slow_type(element, text: str):
    for ch in text:
        element.type(ch, delay=random.randint(40, 120))

# ---------------------------------------------------------------------------
# Form helpers
# ---------------------------------------------------------------------------

def _visible_text(loc) -> str:
    try:
        return (loc.inner_text() or "").strip().lower()
    except Exception:
        return ""


def _fill_text_question(page, label_text: str, answer: str):
    """Find a text/textarea input near a label that contains label_text and fill it."""
    try:
        inputs = page.locator("input[type='text'], input[type='number'], textarea").all()
        for inp in inputs:
            try:
                aria = (inp.get_attribute("aria-label") or "").lower()
                placeholder = (inp.get_attribute("placeholder") or "").lower()
                if label_text.lower() in aria or label_text.lower() in placeholder:
                    inp.scroll_into_view_if_needed()
                    inp.click()
                    inp.fill("")
                    _slow_type(inp, answer)
                    _delay(0.2, 0.5)
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def _select_option(page, label_text: str, option_text: str):
    """Find a select/combobox near a label and pick the best matching option."""
    try:
        selects = page.locator("select").all()
        for sel in selects:
            try:
                aria = (sel.get_attribute("aria-label") or "").lower()
                if label_text.lower() in aria:
                    options = sel.locator("option").all()
                    best = None
                    for opt in options:
                        t = (opt.inner_text() or "").strip().lower()
                        if option_text.lower() in t:
                            best = opt.inner_text().strip()
                            break
                    if best:
                        sel.select_option(label=best)
                        _delay(0.2, 0.5)
                        return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def _answer_yes_no_radio(page, label_text: str, answer_yes: bool):
    """Click Yes or No radio for a question containing label_text."""
    try:
        labels = page.locator("label").all()
        for lbl in labels:
            txt = _visible_text(lbl)
            if label_text.lower() in txt:
                # look for sibling/nearby radio buttons
                parent = lbl.locator("xpath=../..")
                radios = parent.locator("input[type='radio']").all()
                for radio in radios:
                    radio_label_id = radio.get_attribute("id") or ""
                    corresponding = page.locator(f"label[for='{radio_label_id}']")
                    radio_txt = _visible_text(corresponding).lower()
                    if answer_yes and radio_txt in ("yes", "true"):
                        radio.check()
                        _delay(0.2, 0.5)
                        return True
                    elif not answer_yes and radio_txt in ("no", "false"):
                        radio.check()
                        _delay(0.2, 0.5)
                        return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Core Easy Apply flow
# ---------------------------------------------------------------------------

class LinkedInEasyApply:
    def __init__(self, headless: bool = False):
        if sync_playwright is None:
            raise RuntimeError("playwright not installed — run: pip install playwright && playwright install chromium")
        self.headless = headless
        self._pw = None
        self._browser = None
        self._page = None

    def start(self):
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 900},
        )
        self._page = self._browser.new_page()

    def stop(self):
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass

    def apply(self, job: dict, package: dict | None = None) -> dict:
        """
        Attempt Easy Apply for a single job.
        job: dict with at least 'job_url', 'job_title', 'company'
        package: parsed JSON from application_packages/*.json (optional, used for answers)
        Returns dict with keys: success (bool), note (str)
        """
        url = job.get("job_url", "")
        if not url:
            return {"success": False, "note": "No job URL provided"}

        page = self._page
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            _delay(2, 4)
        except Exception as e:
            return {"success": False, "note": f"Page load failed: {e}"}

        # Check if still logged in
        if "authwall" in page.url or "login" in page.url:
            return {"success": False, "note": "Not logged in — run linkedin_test.py first"}

        # Click Easy Apply button
        easy_apply_btn = page.locator("button:has-text('Easy Apply'), .jobs-apply-button").first
        try:
            easy_apply_btn.wait_for(timeout=10000)
            easy_apply_btn.click()
            _delay(1.5, 3)
        except PlaywrightTimeoutError:
            return {"success": False, "note": "Easy Apply button not found — may not be an Easy Apply job"}
        except Exception as e:
            return {"success": False, "note": f"Could not click Easy Apply: {e}"}

        # Multi-step modal
        note = self._handle_modal(page, job, package)
        return {"success": "submitted" in note.lower(), "note": note}

    def _handle_modal(self, page, job: dict, package: dict | None) -> str:
        max_steps = 15
        for step in range(max_steps):
            _delay(1, 2)

            # Check if modal closed (submitted)
            if not page.locator("div[data-test-modal]").is_visible():
                # Look for success message
                try:
                    page.wait_for_selector("text=application was sent", timeout=3000)
                    return "Application submitted successfully"
                except Exception:
                    pass

            # Handle "Upload resume" step
            self._try_upload_resume(page)

            # Handle form questions
            self._try_fill_questions(page, job, package)

            # Try Next or Review or Submit button
            result = self._try_advance(page)
            if result == "submitted":
                return "Application submitted successfully"
            elif result == "error":
                return f"Stopped at step {step+1}: could not advance"
            # result == "next" → continue loop

        return f"Reached max steps ({max_steps}) without submitting"

    def _try_upload_resume(self, page):
        try:
            upload_input = page.locator("input[type='file']").first
            if upload_input.is_visible() and os.path.exists(CV_PDF_PATH):
                upload_input.set_input_files(CV_PDF_PATH)
                _delay(1, 2)
        except Exception:
            pass

    def _try_fill_questions(self, page, job: dict, package: dict | None):
        """Fill visible form fields using package data and sensible defaults."""
        pkg = package or {}

        # Phone number
        _fill_text_question(page, "phone", "07700000000")

        # Work authorization / right to work
        work_auth = pkg.get("work_authorization_answer", "Yes, I have the right to work in the UK")
        _answer_yes_no_radio(page, "authorised to work", True)
        _answer_yes_no_radio(page, "right to work", True)
        _fill_text_question(page, "work authoriz", work_auth)

        # Visa / sponsorship
        _answer_yes_no_radio(page, "require sponsorship", True)
        _answer_yes_no_radio(page, "visa sponsorship", True)
        _fill_text_question(page, "sponsorship", pkg.get("visa_sponsorship_answer", "Yes, I require a Skilled Worker visa sponsorship"))

        # Salary
        salary = pkg.get("salary_expectation_answer", "£55,000 - £70,000")
        _fill_text_question(page, "salary", salary)
        _fill_text_question(page, "expected salary", salary)
        _fill_text_question(page, "desired salary", salary)

        # Notice period
        notice = pkg.get("notice_period_answer", "1 month")
        _fill_text_question(page, "notice", notice)
        _fill_text_question(page, "availability", notice)

        # Location / relocation
        _fill_text_question(page, "location", pkg.get("location_answer", "London, UK — open to hybrid"))
        _fill_text_question(page, "city", "London")
        _fill_text_question(page, "postcode", "")

        # Years of experience (try to find number fields)
        _fill_text_question(page, "years of experience", "7")
        _fill_text_question(page, "how many years", "7")

        # LinkedIn / website
        _fill_text_question(page, "linkedin", "https://www.linkedin.com/in/faizanfayyaz")
        _fill_text_question(page, "website", "")
        _fill_text_question(page, "portfolio", "")

        # Cover letter / additional info
        cover = pkg.get("cover_letter", "")
        if cover:
            _fill_text_question(page, "cover letter", cover)
            _fill_text_question(page, "additional information", cover[:500])

        # Generic radio questions — try to pick "Yes" for most
        try:
            unanswered_radios = page.locator("fieldset:not(:has(input[type='radio']:checked))").all()
            for fieldset in unanswered_radios:
                # Pick the first option
                first_radio = fieldset.locator("input[type='radio']").first
                first_radio.check()
                _delay(0.1, 0.3)
        except Exception:
            pass

        # Unset required text inputs — fill with N/A
        try:
            empty_required = page.locator("input[required]:not([type='file']):not([type='radio']):not([type='checkbox'])").all()
            for inp in empty_required:
                try:
                    val = inp.input_value()
                    if not val.strip():
                        inp.fill("N/A")
                        _delay(0.1, 0.2)
                except Exception:
                    pass
        except Exception:
            pass

    def _try_advance(self, page) -> str:
        """Click Next / Review / Submit. Returns 'next', 'submitted', or 'error'."""
        _delay(0.5, 1)

        # Submit button
        submit_btn = page.locator("button:has-text('Submit application'), button[aria-label*='Submit application']").first
        if submit_btn.is_visible():
            submit_btn.click()
            _delay(2, 4)
            return "submitted"

        # Review button
        review_btn = page.locator("button:has-text('Review'), button[aria-label*='Review']").first
        if review_btn.is_visible():
            review_btn.click()
            _delay(1, 2)
            return "next"

        # Next button
        next_btn = page.locator("button:has-text('Next'), button[aria-label*='Continue to next step']").first
        if next_btn.is_visible():
            next_btn.click()
            _delay(1, 2)
            return "next"

        # Dismiss "not now" / follow company popups
        try:
            dismiss = page.locator("button:has-text('Not now'), button:has-text('Skip'), button:has-text('Dismiss')").first
            if dismiss.is_visible():
                dismiss.click()
                _delay(0.5, 1)
                return "next"
        except Exception:
            pass

        return "error"


# ---------------------------------------------------------------------------
# Batch apply entry point (called from auto_apply.py)
# ---------------------------------------------------------------------------

def apply_easy_apply_jobs(jobs: list, packages_dir: str = "application_packages") -> list:
    """
    Apply to all APPROVED Easy Apply jobs.
    Returns updated jobs list with statuses set.
    """
    if sync_playwright is None:
        print("ERROR: playwright not installed")
        return jobs

    bot = LinkedInEasyApply(headless=False)
    bot.start()

    try:
        for idx, job in enumerate(jobs):
            if job.get("status") != "APPROVED":
                continue
            ats = str(job.get("ats", "")).lower()
            if not ("easy_apply" in ats or "linkedin" in ats):
                continue

            print(f"\n[{idx+1}] Applying: {job['company']} — {job['job_title']}")

            # Load package JSON if available
            package = None
            pkg_txt = job.get("package_path", "")
            if pkg_txt:
                json_path = pkg_txt.replace(".txt", ".json")
                if os.path.exists(json_path):
                    import json
                    try:
                        with open(json_path, "r", encoding="utf-8") as f:
                            package = json.load(f)
                    except Exception:
                        pass

            result = bot.apply(job, package)
            now = datetime.datetime.utcnow().isoformat()

            if result["success"]:
                job["status"] = "SUBMITTED"
                job["updated_at"] = now
                print(f"  ✓ {result['note']}")
            else:
                job["status"] = "FAILED"
                job["updated_at"] = now
                print(f"  ✗ {result['note']}")

            # Polite delay between applications
            _delay(5, 10)
    finally:
        bot.stop()

    return jobs


# ---------------------------------------------------------------------------
# CLI for standalone use
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys, json

    if len(sys.argv) < 2:
        print("Usage: python linkedin_apply.py <jobs_queue.csv>")
        sys.exit(1)

    import csv
    csv_path = sys.argv[1]
    with open(csv_path, newline="", encoding="utf-8") as f:
        jobs = list(csv.DictReader(f))

    updated = apply_easy_apply_jobs(jobs)

    # Write back
    if updated:
        fieldnames = list(updated[0].keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            w.writerows(updated)
        print(f"\nUpdated {csv_path}")
