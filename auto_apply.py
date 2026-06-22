import os
import csv
import json
import uuid
import datetime
import time
import tempfile
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        return None

load_dotenv()

CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
CV_PATH = os.getenv("CV_PATH", "/Users/faizansmac/Downloads/attachments/Faizan_Fayyaz_KYNDRYL.pdf")
MASTER_PROMPT_PATH = os.getenv("MASTER_PROMPT_PATH", "MasterPrompt.txt")
JOBS_CSV = os.getenv("JOBS_CSV", "jobs_queue.csv")
LOG_CSV = os.getenv("LOG_CSV", "applications_log.csv")
PACKAGES_DIR = os.getenv("PACKAGES_DIR", "application_packages")
COMPANY_STATS_PATH = os.getenv("COMPANY_STATS_PATH", "company_stats.json")

STATUSES = [
    "NEW",
    "ANALYZED",
    "READY_FOR_REVIEW",
    "APPROVED",
    "SUBMITTED",
    "COMPLETED",
    "FAILED",
    "SKIPPED",
]

ATS_PRIORITY = {
    "greenhouse": 100,
    "lever": 95,
    "workday": 90,
    "smartrecruiters": 85,
    "icims": 80,
    "successfactors": 75,
    "oracle": 70,
    "taleo": 65,
    "easy_apply": 10,
    "unknown": 40,
}

KNOWN_SPONSORS = [
    "accenture",
    "capgemini",
    "cgi",
    "deloitte",
    "ey",
    "kpmg",
    "pwc",
    "ibm",
    "oracle",
    "microsoft",
    "amazon",
    "aws",
    "google",
    "meta",
    "apple",
    "atos",
    "sopra steria",
    "infosys",
    "tcs",
    "wipro",
    "hcl",
    "kyndryl",
    "bt",
    "vodafone",
    "sky",
    "nhs",
    "hsbc",
    "barclays",
    "lloyds",
    "natwest",
    "standard chartered",
    "jp morgan",
    "jpmorgan",
    "deutsche bank",
    "bnp paribas",
    "citi",
    "equifax",
    "experian",
    "worldpay",
    "fis",
    "fiserv",
]

SPONSOR_KEYWORDS = [
    "sponsorship",
    "skilled worker",
    "tier 2",
    "tier ii",
    "global mobility",
    "certificate of sponsorship",
    "cos",
]

Path(PACKAGES_DIR).mkdir(parents=True, exist_ok=True)
_CV_TEXT = None
_MASTER_PROMPT = None


def load_cv_text(path: str) -> str:
    if pdfplumber is None:
        raise RuntimeError("Missing dependency: install pdfplumber before running analyze")
    if not os.path.exists(path):
        raise RuntimeError(f"CV file not found: {path}")

    text = ""
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            text += page_text + "\n"
    if len(text) > 8000:
        text = text[:8000]
    return text


def load_master_prompt(path: str) -> str:
    if not os.path.exists(path):
        raise RuntimeError(f"Master prompt file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def get_cv_text() -> str:
    global _CV_TEXT
    if _CV_TEXT is None:
        _CV_TEXT = load_cv_text(CV_PATH)
    return _CV_TEXT


def get_master_prompt() -> str:
    global _MASTER_PROMPT
    if _MASTER_PROMPT is None:
        _MASTER_PROMPT = load_master_prompt(MASTER_PROMPT_PATH)
    return _MASTER_PROMPT


def clean_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```json"):
        text = text.replace("```json", "", 1)
    if text.startswith("```"):
        text = text.replace("```", "", 1)
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def extract_json(text: str) -> str:
    start = text.find("{")
    if start == -1:
        return text

    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]

    return text


def safe_int(value, default=0) -> int:
    try:
        return int(float(str(value).replace("%", "").strip()))
    except (TypeError, ValueError):
        return default


def clamp(value: int, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, value))


def atomic_write(path: str, write_func):
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{os.path.basename(path)}.",
        suffix=".tmp",
        dir=directory,
        text=True,
    )
    os.close(fd)
    try:
        write_func(tmp_path)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def ask_claude(prompt: str, max_tokens: int = 1600) -> str:
    if requests is None:
        return "ERROR"

    headers = {
        "Content-Type": "application/json",
        "x-api-key": CLAUDE_API_KEY,
        "anthropic-version": "2023-06-01",
    }
    data = {
        "model": "claude-3-5-sonnet-20241022",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            json=data,
            headers=headers,
            timeout=90,
        )
        resp.raise_for_status()
        j = resp.json()
    except (requests.exceptions.RequestException, ValueError):
        return "ERROR"

    if "error" in j:
        return "ERROR"
    try:
        return j["content"][0]["text"]
    except (KeyError, IndexError, TypeError):
        return "ERROR"


def job_fieldnames():
    return [
        "id",
        "company",
        "job_title",
        "ats",
        "job_url",
        "status",
        "decision",
        "score",
        "sponsorship_confidence",
        "sponsorship_probability",
        "reason",
        "final_score",
        "package_path",
        "created_at",
        "updated_at",
    ]


def log_fieldnames():
    return [
        "timestamp",
        "job_id",
        "company",
        "job_title",
        "ats",
        "score",
        "sponsorship_confidence",
        "sponsorship_probability",
        "final_score",
        "status",
        "job_url",
        "package_path",
        "note",
    ]


def ensure_csv_schema(path: str, fieldnames):
    if not os.path.exists(path):
        def write_new_csv(tmp_path):
            with open(tmp_path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(fieldnames)

        atomic_write(path, write_new_csv)
        return

    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        existing_fieldnames = reader.fieldnames or []
        rows = list(reader)

    if existing_fieldnames == fieldnames:
        return

    if all(field in existing_fieldnames for field in fieldnames):
        return

    def write_migrated_csv(tmp_path):
        with open(tmp_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                for field in fieldnames:
                    row.setdefault(field, "")
                writer.writerow(row)

    atomic_write(path, write_migrated_csv)


def ensure_jobs_csv():
    ensure_csv_schema(JOBS_CSV, job_fieldnames())


def ensure_log_csv():
    ensure_csv_schema(LOG_CSV, log_fieldnames())


def load_company_stats():
    if not os.path.exists(COMPANY_STATS_PATH):
        return {}
    try:
        with open(COMPANY_STATS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_company_stats(stats):
    def write_stats(tmp_path):
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)

    atomic_write(COMPANY_STATS_PATH, write_stats)


def update_company_stats_on_submit(company: str):
    stats = load_company_stats()
    c = company.strip()
    if c not in stats:
        stats[c] = {"applied": 0, "interviews": 0, "rejections": 0}
    stats[c]["applied"] += 1
    save_company_stats(stats)


def update_company_stats_interview(company: str):
    stats = load_company_stats()
    c = company.strip()
    if c not in stats:
        stats[c] = {"applied": 0, "interviews": 0, "rejections": 0}
    stats[c]["interviews"] += 1
    save_company_stats(stats)


def update_company_stats_rejection(company: str):
    stats = load_company_stats()
    c = company.strip()
    if c not in stats:
        stats[c] = {"applied": 0, "interviews": 0, "rejections": 0}
    stats[c]["rejections"] += 1
    save_company_stats(stats)


def history_bonus(company: str) -> float:
    stats = load_company_stats()
    c = company.strip()
    data = stats.get(c)
    if not data:
        return 0.0
    applied = data.get("applied", 0)
    interviews = data.get("interviews", 0)
    rejections = data.get("rejections", 0)
    if applied == 0:
        return 0.0
    interview_rate = interviews / applied
    rejection_rate = rejections / applied
    bonus = (interview_rate * 20.0) - (rejection_rate * 5.0)
    return max(-10.0, min(10.0, bonus))


def load_jobs():
    ensure_jobs_csv()
    jobs = []
    with open(JOBS_CSV, "r", newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            row.setdefault("sponsorship_confidence", "")
            row.setdefault("sponsorship_probability", "")
            jobs.append(row)
    return jobs


def save_jobs(jobs):
    ensure_jobs_csv()
    fieldnames = job_fieldnames()

    def write_jobs(tmp_path):
        with open(tmp_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            for job in jobs:
                w.writerow(job)

    atomic_write(JOBS_CSV, write_jobs)


def log_event(job, status: str, note: str = ""):
    ensure_log_csv()
    fieldnames = log_fieldnames()
    with open(LOG_CSV, "r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    rows.append(
        {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "job_id": job.get("id", ""),
            "company": job.get("company", ""),
            "job_title": job.get("job_title", ""),
            "ats": job.get("ats", ""),
            "score": job.get("score", ""),
            "sponsorship_confidence": job.get("sponsorship_confidence", ""),
            "sponsorship_probability": job.get("sponsorship_probability", ""),
            "final_score": job.get("final_score", ""),
            "status": status,
            "job_url": job.get("job_url", ""),
            "package_path": job.get("package_path", ""),
            "note": note,
        }
    )

    def write_log(tmp_path):
        with open(tmp_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

    atomic_write(LOG_CSV, write_log)


def sponsor_bonus(company: str) -> int:
    company = company.lower()
    for sponsor in KNOWN_SPONSORS:
        if sponsor in company:
            return 15
    return 0


def jd_sponsor_bonus(job_text: str) -> int:
    text = job_text.lower()
    if any(k.lower() in text for k in SPONSOR_KEYWORDS):
        return 20
    return 0


def sponsorship_level(score: int) -> str:
    if score >= 70:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"


def ats_priority(ats: str) -> int:
    ats_normalized = (ats or "unknown").lower()
    if "linkedin_easy_apply" in ats_normalized or "easy apply" in ats_normalized:
        return ATS_PRIORITY["easy_apply"]
    return ATS_PRIORITY.get(ats_normalized, 40)


def is_easy_apply(job) -> bool:
    ats = str(job.get("ats", "")).lower()
    return "easy_apply" in ats or "linkedin_easy_apply" in ats or ats == "linkedin"


def add_job(company: str, job_title: str, ats: str, job_url: str):
    jobs = load_jobs()
    for existing in jobs:
        if job_url and existing.get("job_url") == job_url:
            return
    job_id = str(uuid.uuid4())
    now = datetime.datetime.utcnow().isoformat()
    job = {
        "id": job_id,
        "company": company,
        "job_title": job_title,
        "ats": ats or "unknown",
        "job_url": job_url,
        "status": "NEW",
        "decision": "",
        "score": "",
        "sponsorship_confidence": "",
        "sponsorship_probability": "",
        "reason": "",
        "final_score": "",
        "package_path": "",
        "created_at": now,
        "updated_at": now,
    }
    jobs.append(job)
    save_jobs(jobs)
    log_event(job, "NEW", "Job added to queue")


def sponsorship_safeguards(job_text: str) -> bool:
    text = job_text.lower()
    hard_no = [
        "no sponsorship",
        "cannot sponsor",
        "unable to sponsor",
        "visa sponsorship unavailable",
        "visa sponsorship not available",
        "we do not provide sponsorship",
        "without sponsorship",
        "not eligible for sponsorship",
    ]
    return not any(x in text for x in hard_no)


def build_analysis_prompt(job_title: str, company: str, job_text: str) -> str:
    master_prompt = get_master_prompt()
    cv_text = get_cv_text()

    return f"""
{master_prompt}

OBJECTIVE:
You are helping Faizan decide whether to apply for this role, and preparing a tailored application package.
You must follow the sponsorship, honesty, and UK Skilled Worker logic defined in the master prompt.

JOB:
TITLE:
{job_title}

COMPANY:
{company}

JOB DESCRIPTION:
{job_text}

CV:
{cv_text}

OUTPUT SCHEMA:
Return valid JSON only, with exactly this structure:

{{
  "decision": "APPLY" | "SKIP",
  "score": 0-100,
  "sponsorship_confidence": 0-100,
  "sponsorship_probability": "Low" | "Medium" | "High",
  "reason": "one sentence reason for APPLY or SKIP",
  "cv_summary": "short tailored professional summary based only on the real CV",
  "top_keywords": [
    "important ATS keyword from the job description that is supported by the real CV"
  ],
  "cv_changes": [
    "specific truthful CV change or emphasis to make locally"
  ],
  "cover_letter": "tailored cover letter for this company and role",
  "keyword_match_analysis": "short analysis of how well the CV matches the JD, including key technologies and responsibilities",
  "missing_skills": [
    "list of important skills or requirements from the JD that are weak or missing in the CV"
  ],
  "sponsor_assessment": "short explanation of why sponsorship is likely or unlikely for this company and role",
  "application_answers": [
    {{
      "question": "likely ATS or application form question",
      "answer": "truthful answer based only on the real CV and profile"
    }}
  ],
  "work_authorization_answer": "truthful answer about current work authorization",
  "visa_sponsorship_answer": "truthful answer about needing or having visa sponsorship",
  "salary_expectation_answer": "truthful salary expectation or range",
  "notice_period_answer": "truthful notice period",
  "location_answer": "truthful preferred location / relocation stance"
}}
"""


def build_local_tailored_cv(cv_summary: str, top_keywords, cv_changes) -> str:
    keyword_lines = "\n".join(f"- {str(k).strip()}" for k in top_keywords if str(k).strip())
    change_lines = "\n".join(f"- {str(c).strip()}" for c in cv_changes if str(c).strip())
    return "\n".join(
        [
            "TAILORED CV DRAFT",
            "",
            "Professional Summary",
            cv_summary.strip(),
            "",
            "ATS Keywords To Emphasize",
            keyword_lines or "- No specific keyword changes returned.",
            "",
            "Truthful CV Changes To Apply",
            change_lines or "- No specific CV changes returned.",
            "",
            "Source CV Text",
            get_cv_text().strip(),
        ]
    )


def analyze_job(job, job_text: str):
    if not sponsorship_safeguards(job_text):
        job["status"] = "SKIPPED"
        job["decision"] = "SKIP"
        job["reason"] = "Hard sponsorship exclusion in job text"
        job["updated_at"] = datetime.datetime.utcnow().isoformat()
        log_event(job, "SKIPPED", "Sponsorship safeguards triggered")
        return job

    if requests is None:
        job["status"] = "FAILED"
        job["updated_at"] = datetime.datetime.utcnow().isoformat()
        log_event(job, "FAILED", "Missing dependency: install requests before running analyze")
        return job

    if not CLAUDE_API_KEY:
        job["status"] = "FAILED"
        job["updated_at"] = datetime.datetime.utcnow().isoformat()
        log_event(job, "FAILED", "Missing CLAUDE_API_KEY environment variable")
        return job

    try:
        prompt = build_analysis_prompt(job["job_title"], job["company"], job_text)
    except RuntimeError as exc:
        job["status"] = "FAILED"
        job["updated_at"] = datetime.datetime.utcnow().isoformat()
        log_event(job, "FAILED", str(exc))
        return job

    raw = "ERROR"
    for attempt in range(3):
        raw = ask_claude(prompt, max_tokens=2000)
        if raw != "ERROR":
            break
        time.sleep(2 ** attempt)
    if raw == "ERROR":
        job["status"] = "FAILED"
        job["updated_at"] = datetime.datetime.utcnow().isoformat()
        log_event(job, "FAILED", "Claude API error after retries")
        return job

    raw = extract_json(clean_json(raw))
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        job["status"] = "FAILED"
        job["updated_at"] = datetime.datetime.utcnow().isoformat()
        log_event(job, "FAILED", "Failed to parse Claude JSON")
        return job

    decision = str(data.get("decision", "")).upper()
    if decision not in {"APPLY", "SKIP"}:
        decision = "SKIP"
    ai_score = clamp(safe_int(data.get("score"), 0))
    sponsorship_confidence = safe_int(data.get("sponsorship_confidence"), 50)
    sponsorship_confidence = clamp(sponsorship_confidence)
    sponsorship_probability = sponsorship_level(sponsorship_confidence)
    reason = str(data.get("reason", "")).strip()
    cv_summary = data.get("cv_summary", "") or ""
    top_keywords = data.get("top_keywords", []) or []
    cv_changes = data.get("cv_changes", []) or []
    cover_letter = data.get("cover_letter", "") or ""
    keyword_match_analysis = data.get("keyword_match_analysis", "") or ""
    missing_skills = data.get("missing_skills", []) or []
    sponsor_assessment = data.get("sponsor_assessment", "") or ""
    answers = data.get("application_answers", []) or []
    work_auth_answer = data.get("work_authorization_answer", "") or ""
    visa_sponsorship_answer = data.get("visa_sponsorship_answer", "") or ""
    salary_expectation_answer = data.get("salary_expectation_answer", "") or ""
    notice_period_answer = data.get("notice_period_answer", "") or ""
    location_answer = data.get("location_answer", "") or ""
    tailored_cv = build_local_tailored_cv(cv_summary, top_keywords, cv_changes)

    if ai_score < 60:
        decision = "SKIP"

    ats = job.get("ats", "unknown")
    base_bonus = sponsor_bonus(job["company"])
    jd_bonus = jd_sponsor_bonus(job_text)
    hist_bonus = history_bonus(job["company"])
    ats_score = ats_priority(ats)

    final_score = (
        ai_score * 0.85
        + base_bonus
        + jd_bonus
        + hist_bonus
        + ats_score * 0.03
    )

    job["decision"] = decision
    job["score"] = str(ai_score)
    job["sponsorship_confidence"] = str(sponsorship_confidence)
    job["sponsorship_probability"] = sponsorship_probability
    job["reason"] = reason
    job["final_score"] = f"{final_score:.1f}"

    if decision != "APPLY":
        job["status"] = "SKIPPED"
        job["updated_at"] = datetime.datetime.utcnow().isoformat()
        log_event(job, "SKIPPED", f"AI decision SKIP (score={ai_score}): {reason}")
        return job

    package_path, json_path = write_application_package(
        job,
        ai_score,
        sponsorship_confidence,
        sponsorship_probability,
        reason,
        final_score,
        base_bonus,
        jd_bonus,
        hist_bonus,
        ats_score,
        tailored_cv,
        cover_letter,
        keyword_match_analysis,
        missing_skills,
        sponsor_assessment,
        answers,
        work_auth_answer,
        visa_sponsorship_answer,
        salary_expectation_answer,
        notice_period_answer,
        location_answer,
        job_text,
    )

    job["package_path"] = package_path
    job["status"] = "READY_FOR_REVIEW"
    job["updated_at"] = datetime.datetime.utcnow().isoformat()
    log_event(job, "READY_FOR_REVIEW", f"Application package generated ({package_path}, {json_path})")
    return job


def write_application_package(
    job,
    ai_score: int,
    sponsorship_confidence: int,
    sponsorship_probability: str,
    reason: str,
    final_score: float,
    sponsor_boost: int,
    jd_boost: int,
    hist_boost: float,
    ats_score: int,
    tailored_cv: str,
    cover_letter: str,
    keyword_match_analysis: str,
    missing_skills,
    sponsor_assessment: str,
    answers,
    work_auth_answer: str,
    visa_sponsorship_answer: str,
    salary_expectation_answer: str,
    notice_period_answer: str,
    location_answer: str,
    job_text: str,
):
    safe_company = job["company"].replace("/", "_").replace("\\", "_")
    safe_title = job["job_title"].replace("/", "_").replace("\\", "_")
    base_name = f"{safe_company}_{safe_title}_{job['id']}"
    txt_filename = f"{base_name}.txt"
    json_filename = f"{base_name}.json"
    txt_path = os.path.join(PACKAGES_DIR, txt_filename)
    json_path = os.path.join(PACKAGES_DIR, json_filename)

    def write_package_txt(tmp_path):
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(f"Company: {job['company']}\n")
            f.write(f"Role: {job['job_title']}\n")
            f.write(f"ATS: {job['ats']}\n")
            f.write(f"Job URL: {job['job_url']}\n")
            f.write(f"AI Score: {ai_score}\n")
            f.write(f"Sponsorship Confidence: {sponsorship_confidence}\n")
            f.write(f"Sponsorship Probability: {sponsorship_probability}\n")
            f.write(f"Sponsor Bonus (company): {sponsor_boost}\n")
            f.write(f"Sponsor Bonus (JD keywords): {jd_boost}\n")
            f.write(f"History Bonus: {hist_boost:.1f}\n")
            f.write(f"ATS Priority: {ats_score}\n")
            f.write(f"Final Ranking Score: {final_score:.1f}\n")
            f.write(f"Decision: {job.get('decision', '')}\n")
            f.write(f"Reason: {reason}\n")
            f.write("Status: READY FOR SUBMISSION\n")

            f.write("\n--- JOB DESCRIPTION ---\n")
            f.write(job_text.strip() + "\n")

            f.write("\n--- KEYWORD MATCH ANALYSIS ---\n")
            f.write(keyword_match_analysis.strip() + "\n")

            f.write("\n--- MISSING SKILLS ---\n")
            for ms in missing_skills:
                f.write(f"- {str(ms).strip()}\n")

            f.write("\n--- SPONSOR ASSESSMENT ---\n")
            f.write(sponsor_assessment.strip() + "\n")

            f.write("\n--- TAILORED CV ---\n")
            f.write(tailored_cv.strip() + "\n")

            f.write("\n--- COVER LETTER ---\n")
            f.write(cover_letter.strip() + "\n")

            f.write("\n--- APPLICATION ANSWERS ---\n")
            for i, qa in enumerate(answers, start=1):
                q = str(qa.get("question", "")).strip()
                a = str(qa.get("answer", "")).strip()
                if not q and not a:
                    continue
                f.write(f"\nQ{i}: {q}\n")
                f.write(f"A{i}: {a}\n")

            f.write("\n--- STANDARD ATS ANSWERS ---\n")
            f.write(f"Work Authorization: {work_auth_answer}\n")
            f.write(f"Visa Sponsorship: {visa_sponsorship_answer}\n")
            f.write(f"Salary Expectation: {salary_expectation_answer}\n")
            f.write(f"Notice Period: {notice_period_answer}\n")
            f.write(f"Location / Relocation: {location_answer}\n")

    atomic_write(txt_path, write_package_txt)

    meta = {
        "company": job["company"],
        "job_title": job["job_title"],
        "ats": job["ats"],
        "job_url": job["job_url"],
        "decision": job.get("decision", ""),
        "ai_score": ai_score,
        "sponsorship_confidence": sponsorship_confidence,
        "sponsorship_probability": sponsorship_probability,
        "reason": reason,
        "sponsor_bonus_company": sponsor_boost,
        "sponsor_bonus_jd": jd_boost,
        "history_bonus": hist_boost,
        "ats_priority": ats_score,
        "final_score": final_score,
        "package_txt": txt_path,
        "created_at": datetime.datetime.utcnow().isoformat(),
    }
    def write_package_json(tmp_path):
        with open(tmp_path, "w", encoding="utf-8") as jf:
            json.dump(meta, jf, indent=2, ensure_ascii=False)

    atomic_write(json_path, write_package_json)

    return txt_path, json_path


def analyze_new_jobs(job_texts_by_id: dict):
    jobs = load_jobs()
    changed = False
    for idx, job in enumerate(jobs):
        if job["status"] != "NEW":
            continue
        job_id = job["id"]
        job_text = job_texts_by_id.get(job_id, "")
        if not job_text.strip():
            job["status"] = "FAILED"
            job["updated_at"] = datetime.datetime.utcnow().isoformat()
            log_event(job, "FAILED", "No job description provided")
            jobs[idx] = job
            changed = True
            continue
        job["status"] = "ANALYZED"
        job["updated_at"] = datetime.datetime.utcnow().isoformat()
        log_event(job, "ANALYZED", "Starting analysis")
        jobs[idx] = analyze_job(job, job_text)
        changed = True
    if changed:
        save_jobs(jobs)


def mark_job_approved(job_id: str):
    jobs = load_jobs()
    changed = False
    for idx, job in enumerate(jobs):
        if job["id"] == job_id:
            if job["status"] != "READY_FOR_REVIEW":
                log_event(job, job["status"], "Cannot approve: not READY_FOR_REVIEW")
                break
            job["status"] = "APPROVED"
            job["updated_at"] = datetime.datetime.utcnow().isoformat()
            log_event(job, "APPROVED", "Job approved for submission")
            jobs[idx] = job
            changed = True
            break
    if changed:
        save_jobs(jobs)


def submit_application(job):
    update_company_stats_on_submit(job.get("company", ""))
    if is_easy_apply(job):
        try:
            from linkedin_apply import LinkedInEasyApply
            import json as _json
            package = None
            pkg_txt = job.get("package_path", "")
            if pkg_txt:
                json_path = pkg_txt.replace(".txt", ".json")
                if os.path.exists(json_path):
                    with open(json_path, "r", encoding="utf-8") as _f:
                        package = _json.load(_f)
            bot = LinkedInEasyApply(headless=False)
            bot.start()
            try:
                result = bot.apply(job, package)
            finally:
                bot.stop()
            note = result.get("note", "")
            if result.get("success"):
                job["status"] = "SUBMITTED"
                job["updated_at"] = datetime.datetime.utcnow().isoformat()
                log_event(job, "SUBMITTED", note)
            else:
                job["status"] = "FAILED"
                job["updated_at"] = datetime.datetime.utcnow().isoformat()
                log_event(job, "FAILED", note)
        except Exception as exc:
            job["status"] = "FAILED"
            job["updated_at"] = datetime.datetime.utcnow().isoformat()
            log_event(job, "FAILED", f"LinkedIn automation error: {exc}")
    else:
        log_event(job, "SUBMITTED", "Non-Easy-Apply job: manual submission required")
        job["status"] = "SUBMITTED"
        job["updated_at"] = datetime.datetime.utcnow().isoformat()
    return job


def submit_approved_jobs():
    jobs = load_jobs()
    changed = False
    for idx, job in enumerate(jobs):
        if job["status"] != "APPROVED":
            continue
        jobs[idx] = submit_application(job)
        changed = True
        save_jobs(jobs)  # save after each job so progress isn't lost on crash


def print_queue():
    jobs = load_jobs()

    def score_for_sort(j):
        try:
            return float(j.get("final_score", "0"))
        except ValueError:
            return 0.0

    jobs = sorted(jobs, key=score_for_sort, reverse=True)
    print("JOB QUEUE (sorted by final_score)")
    print("--------------------------------")
    for job in jobs:
        print(
            f"{job['id']} | {job['company']} | {job['job_title']} | {job['status']} | "
            f"decision={job.get('decision', '')} | ai_score={job.get('score', '')} | "
            f"sponsorship={job.get('sponsorship_probability', '')} "
            f"({job.get('sponsorship_confidence', '')}) | "
            f"final={job.get('final_score', '')} | ats={job.get('ats', '')}"
        )


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Job Application Engine (Review -> Approve -> Submit)")
    sub = parser.add_subparsers(dest="cmd")

    add_cmd = sub.add_parser("add", help="Add a job to the queue")
    add_cmd.add_argument("--company", required=True)
    add_cmd.add_argument("--title", required=True)
    add_cmd.add_argument("--ats", default="unknown")
    add_cmd.add_argument("--url", default="")

    analyze_cmd = sub.add_parser("analyze", help="Analyze NEW jobs and generate packages")
    analyze_cmd.add_argument(
        "--jobs-json",
        required=True,
        help="Path to JSON file mapping job_id -> job_description",
    )

    approve_cmd = sub.add_parser("approve", help="Mark a job as APPROVED")
    approve_cmd.add_argument("--id", required=True)

    sub.add_parser("submit", help="Submit all APPROVED jobs (simulated)")
    sub.add_parser("queue", help="Print job queue")

    mark_int_cmd = sub.add_parser("mark-interview", help="Record an interview for a company")
    mark_int_cmd.add_argument("--company", required=True)

    mark_rej_cmd = sub.add_parser("mark-rejection", help="Record a rejection for a company")
    mark_rej_cmd.add_argument("--company", required=True)

    sub.add_parser("linkedin-apply", help="Run LinkedIn Easy Apply automation for all APPROVED jobs")

    args = parser.parse_args()

    if args.cmd is None:
        print_queue()
        return

    if args.cmd == "add":
        add_job(args.company, args.title, args.ats, args.url)
    elif args.cmd == "analyze":
        with open(args.jobs_json, "r", encoding="utf-8") as f:
            job_texts_by_id = json.load(f)
        analyze_new_jobs(job_texts_by_id)
    elif args.cmd == "approve":
        mark_job_approved(args.id)
    elif args.cmd == "submit":
        submit_approved_jobs()
    elif args.cmd == "queue":
        print_queue()
    elif args.cmd == "mark-interview":
        update_company_stats_interview(args.company)
        print(f"Recorded interview for {args.company}")
    elif args.cmd == "mark-rejection":
        update_company_stats_rejection(args.company)
        print(f"Recorded rejection for {args.company}")
    elif args.cmd == "linkedin-apply":
        submit_approved_jobs()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
