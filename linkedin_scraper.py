"""
LinkedIn job scraper — searches LinkedIn Jobs, scrapes listings + descriptions,
adds them to jobs_queue.csv, and optionally triggers Claude analysis.

Usage:
    python linkedin_scraper.py                        # use defaults in SEARCH_CONFIGS
    python linkedin_scraper.py --keywords "cloud engineer" --location "United Kingdom" --limit 20
    python linkedin_scraper.py --analyze              # also run Claude analysis after scraping
"""

import os
import re
import sys
import time
import random
import json
import argparse
import datetime

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
except ImportError:
    print("ERROR: playwright not installed — run: python3 -m pip install playwright && python3 -m playwright install chromium")
    sys.exit(1)

# Import queue management from main engine
sys.path.insert(0, os.path.dirname(__file__))
from auto_apply import add_job, load_jobs, analyze_new_jobs

PROFILE_DIR = os.getenv("LINKEDIN_PROFILE_DIR", "./linkedin_profile")

# Default job searches — edit these to match what you're looking for
SEARCH_CONFIGS = [
    {"keywords": "cloud engineer", "location": "United Kingdom", "easy_apply": True},
    {"keywords": "devops engineer", "location": "United Kingdom", "easy_apply": True},
    {"keywords": "platform engineer", "location": "United Kingdom", "easy_apply": True},
    {"keywords": "infrastructure engineer", "location": "United Kingdom", "easy_apply": True},
    {"keywords": "site reliability engineer", "location": "United Kingdom", "easy_apply": True},
]

def _delay(lo=0.5, hi=1.5):
    time.sleep(random.uniform(lo, hi))


def build_search_url(keywords: str, location: str, easy_apply: bool = True) -> str:
    import urllib.parse
    kw = urllib.parse.quote_plus(keywords)
    loc = urllib.parse.quote_plus(location)
    url = f"https://www.linkedin.com/jobs/search/?keywords={kw}&location={loc}&f_TPR=r86400"
    if easy_apply:
        url += "&f_LF=f_AL"  # Easy Apply filter
    return url


def _safe_text(page, selector: str, timeout: int = 5000) -> str:
    """Get inner text of first matching element, returning '' on any failure."""
    try:
        loc = page.locator(selector).first
        loc.wait_for(state="attached", timeout=timeout)
        return (loc.inner_text(timeout=timeout) or "").strip()
    except Exception:
        return ""


def scrape_job_description(page, job_url: str) -> str:
    """Navigate to a job page and extract the job description text."""
    try:
        page.goto(job_url, wait_until="domcontentloaded", timeout=25000)
        # Wait for the page to settle — LinkedIn does a lot of JS rendering
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        _delay(1, 2)

        # Try to expand "Show more" in description
        try:
            show_more = page.locator("button:has-text('Show more')").first
            if show_more.is_visible(timeout=2000):
                show_more.click()
                _delay(0.5, 1)
        except Exception:
            pass

        # Extract description text — try selectors in priority order
        selectors = [
            "#job-details",
            ".jobs-description__content",
            ".jobs-description-content__text",
            ".jobs-box__html-content",
            ".job-view-layout",
            "article",
        ]
        for sel in selectors:
            text = _safe_text(page, sel, timeout=4000)
            if text and len(text) > 100:
                return text[:6000]

        # Fallback: grab body text
        try:
            body = page.inner_text("body", timeout=5000)
            return body[:5000]
        except Exception:
            return ""
    except Exception as e:
        return f"[Failed to scrape: {e}]"


def extract_company_and_title(page) -> tuple[str, str]:
    """Extract company name and job title from a job page."""
    title = _safe_text(page, (
        ".job-details-jobs-unified-top-card__job-title h1, "
        "h1.t-24, "
        "h1[class*='title'], "
        ".jobs-unified-top-card__job-title h1"
    ), timeout=5000)

    company = _safe_text(page, (
        ".job-details-jobs-unified-top-card__company-name a, "
        ".job-details-jobs-unified-top-card__company-name, "
        ".jobs-unified-top-card__company-name a, "
        ".jobs-unified-top-card__company-name, "
        "a[data-tracking-control-name='public_jobs_topcard-org-name']"
    ), timeout=5000)

    return company, title


def detect_ats(job_url: str, description: str) -> str:
    """Detect ATS from URL or description text."""
    combined = (job_url + " " + description).lower()
    if "linkedin.com" in job_url and ("easy apply" in combined or "f_LF=f_AL" in job_url):
        return "linkedin_easy_apply"
    ats_markers = {
        "greenhouse": ["greenhouse.io", "boards.greenhouse"],
        "lever": ["lever.co", "jobs.lever"],
        "workday": ["myworkdayjobs", "workday.com"],
        "smartrecruiters": ["smartrecruiters.com"],
        "icims": ["icims.com"],
        "successfactors": ["successfactors.com", "successfactors.eu"],
        "taleo": ["taleo.net"],
    }
    for ats, markers in ats_markers.items():
        if any(m in combined for m in markers):
            return ats
    return "unknown"


def scrape_search_page(page, search_url: str, limit: int = 25) -> list[dict]:
    """
    Load a LinkedIn job search page and collect job cards.
    Returns list of dicts with: job_url, title_hint, company_hint
    """
    print(f"  Searching: {search_url}")
    try:
        page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        _delay(2, 4)
    except Exception as e:
        print(f"  Failed to load search page: {e}")
        return []

    if "authwall" in page.url or "login" in page.url:
        print("  Not logged in — run linkedin_test.py first to save session")
        return []

    jobs = []
    seen_urls = set()
    scroll_attempts = 0
    max_scrolls = max(3, limit // 5)

    while len(jobs) < limit and scroll_attempts < max_scrolls:
        # Collect ALL anchor tags and filter to job view URLs
        all_links = page.locator("a[href*='/jobs/view/']").all()
        for card in all_links:
            try:
                href = card.get_attribute("href") or ""
                if not href:
                    continue
                # Normalise — strip query params, keep just the numeric job ID path
                match = re.search(r"(https://www\.linkedin\.com/jobs/view/\d+)", href)
                if not match:
                    match = re.search(r"(/jobs/view/\d+)", href)
                    if match:
                        href = "https://www.linkedin.com" + match.group(1)
                    else:
                        continue
                else:
                    href = match.group(1)

                if href in seen_urls:
                    continue
                seen_urls.add(href)
                try:
                    title_hint = (card.inner_text(timeout=1000) or "").strip()
                except Exception:
                    title_hint = ""
                jobs.append({"job_url": href, "title_hint": title_hint, "company_hint": ""})
                if len(jobs) >= limit:
                    break
            except Exception:
                continue

        if len(jobs) >= limit:
            break

        # Scroll to load more
        page.evaluate("window.scrollBy(0, window.innerHeight * 3)")
        _delay(1.5, 3)

        # Click "See more jobs" button if present
        try:
            see_more = page.locator("button:has-text('See more jobs')").first
            if see_more.is_visible():
                see_more.click()
                _delay(1.5, 2.5)
        except Exception:
            pass

        scroll_attempts += 1

    print(f"  Found {len(jobs)} job links")
    return jobs[:limit]


def run_scraper(
    search_configs: list[dict],
    limit_per_search: int = 20,
    run_analysis: bool = False,
):
    existing_jobs = load_jobs()
    existing_urls = {j.get("job_url", "") for j in existing_jobs}

    with sync_playwright() as pw:
        browser = pw.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 900},
        )
        page = browser.new_page()

        new_job_texts = {}  # job_id -> description (for analysis)

        for cfg in search_configs:
            keywords = cfg.get("keywords", "")
            location = cfg.get("location", "United Kingdom")
            easy_apply = cfg.get("easy_apply", True)
            print(f"\n--- Searching: '{keywords}' in '{location}' (Easy Apply={easy_apply}) ---")

            search_url = build_search_url(keywords, location, easy_apply)
            cards = scrape_search_page(page, search_url, limit=limit_per_search)

            for i, card in enumerate(cards):
                job_url = card["job_url"]
                if job_url in existing_urls:
                    print(f"  [{i+1}/{len(cards)}] Already in queue, skipping: {job_url}")
                    continue

                print(f"  [{i+1}/{len(cards)}] Scraping: {job_url}")
                description = scrape_job_description(page, job_url)

                # Re-extract title/company from the job page (more reliable than card)
                company, title = extract_company_and_title(page)
                if not title:
                    title = card.get("title_hint", "Unknown Role")
                if not company:
                    company = "Unknown Company"

                ats = detect_ats(job_url, description)
                print(f"      → {company} | {title} | ATS: {ats}")

                # Skip if description is empty/failed
                if not description or "[Failed" in description or len(description) < 50:
                    print(f"      ✗ Could not get description, skipping")
                    continue

                # Add to queue
                add_job(company, title, ats, job_url)
                existing_urls.add(job_url)

                # Store description for analysis
                # We need the job_id — reload queue to get it
                updated_jobs = load_jobs()
                for j in updated_jobs:
                    if j.get("job_url") == job_url and j.get("status") == "NEW":
                        new_job_texts[j["id"]] = description
                        break

                _delay(2, 4)  # polite delay between job pages

        browser.close()

    print(f"\n✓ Scraped and queued {len(new_job_texts)} new jobs")

    if run_analysis and new_job_texts:
        print("\nRunning Claude analysis on new jobs...")
        analyze_new_jobs(new_job_texts)
        print("✓ Analysis complete — run 'python auto_apply.py queue' to review")
    elif new_job_texts and not run_analysis:
        print("\nNext steps:")
        print("  1. Run analysis:  python auto_apply.py analyze --jobs-json <(echo '{}')")
        print("     Or re-run with --analyze flag: python linkedin_scraper.py --analyze")
        print("  2. Review queue:  python auto_apply.py queue")
        print("  3. Approve jobs:  python auto_apply.py approve --id <id>")
        print("  4. Apply:         python auto_apply.py linkedin-apply")


def main():
    parser = argparse.ArgumentParser(description="LinkedIn Job Scraper")
    parser.add_argument("--keywords", help="Job keywords (overrides SEARCH_CONFIGS)")
    parser.add_argument("--location", default="United Kingdom", help="Location")
    parser.add_argument("--limit", type=int, default=20, help="Max jobs per search")
    parser.add_argument("--no-easy-apply", action="store_true", help="Don't filter to Easy Apply only")
    parser.add_argument("--analyze", action="store_true", help="Run Claude analysis after scraping")
    args = parser.parse_args()

    if args.keywords:
        configs = [{"keywords": args.keywords, "location": args.location, "easy_apply": not args.no_easy_apply}]
    else:
        configs = SEARCH_CONFIGS

    run_scraper(configs, limit_per_search=args.limit, run_analysis=args.analyze)


if __name__ == "__main__":
    main()
