"""Extract one or more jobs from LinkedIn-style posts and comment dumps.

Handles:
- "Company is hiring Role…" posts with Application link / lnkd.in
- "Company | Role | Location" + Apply Here lines (including comment replies)
- Multiple opportunities in one paste from the same curator
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse

from pipeline.models import normalize_info_tags

JOB_HOST_HINTS = (
    "greenhouse.io", "lever.co", "ashbyhq.com", "myworkdayjobs.com",
    "smartrecruiters.com", "icims.com", "workable.com", "wellfound.com",
    "jobvite.com", "breezy.hr", "recruitee.com", "oraclecloud.com",
    "successfactors", "taleo.net", "careers.", "jobs.", "apply.",
    "lnkd.in", "aurora.tech", "akunacapital.com", "nvidia.com",
    "simplific", "myworkday.com", "workdayjobs",
)

PIPE_LINE = re.compile(
    r"^\s*([A-Za-z0-9][^|\n]{0,60}?)\s*\|\s*([^|\n]{2,100}?)\s*(?:\|\s*([^\n]*))?\s*$",
    re.M,
)

HIRING_LINE = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9&.\- ]{1,40})\s+is hiring\s+(.+?)\s*$",
    re.I | re.M,
)

CHECK_ROLE = re.compile(
    r"(?:✅|☑️|\*)\s*([A-Za-z0-9][A-Za-z0-9/+\- ()]{4,90})",
)

URL_RE = re.compile(r"https?://[^\s<>\")\]]+")


def _clean_url(raw: str) -> str:
    return raw.rstrip(".,);\"'")


def _url_key(url: str) -> str:
    return url.split("?")[0].rstrip("/").lower()


def is_job_url(url: str) -> bool:
    lower = url.lower()
    if any(x in lower for x in (
        "linkedin.com/in/", "linkedin.com/feed", "linkedin.com/posts",
        "linkedin.com/pulse", "linkedin.com/company/",
    )):
        return False
    if any(h in lower for h in JOB_HOST_HINTS) or "linkedin.com/jobs" in lower:
        return True
    path = urlparse(url).path.lower()
    return any(tok in path for tok in ("/job", "/jobs", "/careers", "/apply", "gh_jid"))


def extract_job_urls(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in URL_RE.findall(text or ""):
        url = _clean_url(raw)
        if not is_job_url(url):
            continue
        key = _url_key(url)
        if key in seen:
            continue
        seen.add(key)
        out.append(url)
    return out


def _snippet_around(text: str, url: str, pad: int = 500) -> str:
    idx = text.find(url)
    if idx < 0:
        # try without query
        idx = text.find(url.split("?")[0])
    if idx < 0:
        return text
    start = max(0, idx - pad)
    end = min(len(text), idx + len(url) + 80)
    return text[start:end]


def guess_title(text: str) -> str:
    m = HIRING_LINE.search(text)
    if m:
        title = re.sub(r"\s+", " ", m.group(2)).strip(" .-|,")
        title = re.sub(r"\.$", "", title)
        if 3 <= len(title) <= 120:
            return title

    for m in CHECK_ROLE.finditer(text):
        cand = re.sub(r"\s+", " ", m.group(1)).strip()
        lower = cand.lower()
        if any(skip in lower for skip in ("full-time role", "work on", "build high", "join one")):
            continue
        if any(k in lower for k in ("engineer", "developer", "intern", "fde", "analyst", "scientist")):
            return cand[:100]

    patterns = [
        r"(?:hiring|looking for|role|position|opening)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9/+\- &()]{4,90})",
        r"\b((?:Software Engineer(?:\s*[,\-]?\s*Entry Level)?|Backend Compiler Engineers?(?:\s*\([^)]+\))?|FDE|Forward Deployed Engineer)[A-Za-z0-9/+\- ()]{0,40})",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            title = re.sub(r"\s+", " ", m.group(1)).strip(" .-|,")
            if 3 <= len(title) <= 120:
                return title
    return "Open Role (from post)"


def guess_company(text: str, url: str = "") -> str:
    m = HIRING_LINE.search(text)
    if m:
        return m.group(1).strip()

    # Prefer pipe company from a line that looks like Company | Role
    for line in text.splitlines()[:8]:
        pm = PIPE_LINE.match(line.strip())
        if pm:
            return pm.group(1).strip()

    patterns = [
        r"(?:at|@|joining|join)\s+([A-Z][A-Za-z0-9&.\- ]{1,40})",
        r"Company\s*[:\-]\s*([^\n]{2,50})",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            company = m.group(1).strip(" .-|,")
            if len(company) >= 2 and company.lower() not in {"the", "our", "this", "a", "an"}:
                return company

    if url:
        host = urlparse(url).netloc.lower().replace("www.", "")
        for noise in (
            "boards.greenhouse.io", "job-boards.greenhouse.io",
            "jobs.lever.co", "jobs.ashbyhq.com", "lnkd.in",
        ):
            if noise in host:
                parts = [p for p in urlparse(url).path.strip("/").split("/") if p]
                if parts and noise != "lnkd.in":
                    return parts[0].replace("-", " ").title()
                break
        if host and host not in {"lnkd.in"}:
            base = host.split(".")[0]
            if base not in {"jobs", "careers", "www", "app"}:
                return base.replace("-", " ").title()
    return "See post"


def guess_location(text: str) -> str:
    patterns = [
        r"(?:full[- ]?time role in|based in|location|office(?:s)? in)\s*[:\-]?\s*([A-Za-z0-9,.\-/ ]{3,80})",
        r"\b(Remote(?:\s*(?:[·|,-]\s*)?(?:US|USA|in [A-Z]{2,3}))?)\b",
        r"\|\s*([A-Za-z][A-Za-z .]+,\s*[A-Z]{2})\s*$",
        r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*,\s*[A-Z]{2})\b",
        r"\b(NY|NYC|SF|Bay Area|Mountain View|Santa Clara|Seattle|Austin)\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I | re.M)
        if m:
            loc = m.group(1).strip()[:80]
            if loc.lower() not in {"ca", "us"}:
                return loc
    return ""


def guess_work_model(text: str) -> str:
    lower = text.lower()
    if "hybrid" in lower:
        return "Hybrid"
    if re.search(r"\bremote\b", lower):
        return "Remote"
    if "on-site" in lower or "onsite" in lower or "in-office" in lower:
        return "On Site"
    return ""


def guess_info(text: str) -> str:
    lower = text.lower()
    tags: list[str] = []
    if "h1b" in lower or "h-1b" in lower or "visa sponsor" in lower:
        if "no sponsor" in lower or "cannot sponsor" in lower:
            tags.append("No Sponsorship")
        else:
            tags.append("H1B Sponsor")
    if "new college grad" in lower or "new grad" in lower or "college grad" in lower or "entry level" in lower:
        tags.append("New Grad")
    if "intern" in lower and "internal" not in lower:
        tags.append("Internship")
    if "fde" in lower or "forward deployed" in lower:
        tags.append("FDE")
    return normalize_info_tags(*tags)


def guess_category(text: str, title: str = "") -> str:
    blob = f"{title} {text}".lower()
    if "intern" in blob and "internal" not in blob:
        return "Internship"
    if "fde" in blob or "forward deployed" in blob:
        return "Software Engineering"
    if any(k in blob for k in ("compiler", "gpu", "cuda", "systems programming")):
        return "Software Engineering"
    if any(k in blob for k in ("data scientist", "machine learning", " ml ", "ai engineer")):
        return "Data/ML"
    if any(k in blob for k in ("backend", "back-end")):
        return "Backend"
    if any(k in blob for k in ("frontend", "front-end")):
        return "Frontend"
    return "Software Engineering"


def _parse_pipe_context(snippet: str) -> tuple[str, str, str]:
    """Return (company, title, location) from Company | Role | Location lines."""
    for line in snippet.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("apply"):
            continue
        m = PIPE_LINE.match(line)
        if m:
            company = m.group(1).strip()
            title = m.group(2).strip()
            location = (m.group(3) or "").strip()
            return company, title, location
    return "", "", ""


def _blocks_by_url(text: str) -> list[tuple[str, str]]:
    """Pair each job URL with the text block preceding it (until previous URL)."""
    matches = list(URL_RE.finditer(text))
    job_matches = [m for m in matches if is_job_url(_clean_url(m.group(0)))]
    if not job_matches:
        return []

    blocks: list[tuple[str, str]] = []
    for i, m in enumerate(job_matches):
        url = _clean_url(m.group(0))
        # Text after the previous apply URL → this URL (includes Company | Role lines)
        start = job_matches[i - 1].end() if i > 0 else 0
        blocks.append((url, text[start:m.end()]))
    return blocks


def content_fingerprint(text: str) -> str:
    normalized = re.sub(r"\s+", " ", (text or "").strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def extract_jobs_from_post(raw_post: str, *, defaults: dict | None = None) -> list[dict]:
    """Turn pasted post (+ comments) into structured jobs — one per apply URL."""
    defaults = defaults or {}
    text = (raw_post or "").strip()
    if not text and defaults.get("url"):
        text = defaults["url"]

    blocks = _blocks_by_url(text)
    if not blocks and defaults.get("url"):
        blocks = [(defaults["url"], text)]
    if not blocks:
        return []

    jobs: list[dict] = []
    seen_urls: set[str] = set()

    for url, snippet in blocks:
        key = _url_key(url)
        if key in seen_urls:
            continue
        seen_urls.add(key)

        pipe_company, pipe_title, pipe_location = _parse_pipe_context(snippet)
        single = len(blocks) == 1
        title = (
            (defaults.get("title") or "").strip()
            or pipe_title
            or guess_title(snippet)
            or (guess_title(text) if single else "")
            or "Open Role (from post)"
        )
        company = (
            (defaults.get("company") or "").strip()
            or pipe_company
            or guess_company(snippet, url)
        )
        location = (
            (defaults.get("location") or "").strip()
            or pipe_location
            or guess_location(snippet)
            or (guess_location(text) if single else "")
        )
        work_model = (defaults.get("work_model") or "").strip()
        if work_model in {"", "Not sure", "Not Sure"}:
            work_model = guess_work_model(snippet) or (guess_work_model(text) if single else "")
        category = (
            (defaults.get("category") or "").strip()
            or guess_category(snippet, title)
        )
        # Per-URL snippet only — don't bleed New Grad / FDE tags across multi-job pastes
        info_sources = [defaults.get("info") or "", guess_info(snippet)]
        if single:
            info_sources.append(guess_info(text))
        info = normalize_info_tags(*info_sources)

        # Prefer short snippet as raw_post for multi-job pastes; keep enough context
        raw_for_job = snippet.strip()
        if len(raw_for_job) < 40:
            raw_for_job = _snippet_around(text, url)

        jobs.append({
            "title": title,
            "company": company,
            "location": location,
            "work_model": work_model,
            "category": category,
            "type": category,
            "url": url,
            "info": info,
            "raw_post": raw_for_job,
        })

    return jobs
