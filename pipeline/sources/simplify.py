"""Scrape job listings from SimplifyJobs GitHub repos.

Uses the structured listings.json available in both internship and
new-grad repos for clean, machine-readable data.
"""

import json
import re
from datetime import date, datetime

import requests

from pipeline.models import Job, normalize_info_tags
from pipeline.registry import archive_stale_repos, touch_repo

SIMPLIFY_ORG = "SimplifyJobs"
GITHUB_API = "https://api.github.com"

SPONSORSHIP_MAP = {
    "Does Not Sponsor": "No Sponsorship",
    "Other": "",
    "Will Sponsor": "Sponsors Visa",
    "U.S. Citizen Required": "US Citizen Only",
}


def _detect_json_repos(year: int, include_previous: bool = True) -> dict[str, str]:
    """Auto-detect internship repos for the given year (and prior year when backfilling)."""
    repos = {}
    patterns = [
        f"Summer{year}-Internships",
        f"Summer{year + 1}-Internships",
    ]
    if include_previous:
        patterns.append(f"Summer{year - 1}-Internships")

    for pattern in patterns:
        url = f"{GITHUB_API}/repos/{SIMPLIFY_ORG}/{pattern}"
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            default_branch = data.get("default_branch", "dev")
            repos[pattern] = default_branch
            pushed = (data.get("pushed_at") or "")[:10]
            try:
                from datetime import datetime as _dt
                activity = _dt.strptime(pushed, "%Y-%m-%d").date() if pushed else date.today()
            except ValueError:
                activity = date.today()
            touch_repo(
                SIMPLIFY_ORG,
                pattern,
                url=f"https://github.com/{SIMPLIFY_ORG}/{pattern}",
                branch=default_branch,
                last_activity=activity,
                meta={"kind": "internships"},
            )
    return repos


def _detect_newgrad_repos() -> dict[str, str]:
    """Auto-detect new-grad repos (also have listings.json)."""
    repos = {}
    url = f"{GITHUB_API}/repos/{SIMPLIFY_ORG}/New-Grad-Positions"
    resp = requests.get(url, timeout=15)
    if resp.status_code == 200:
        data = resp.json()
        default_branch = data.get("default_branch", "dev")
        repos["New-Grad-Positions"] = default_branch
        pushed = (data.get("pushed_at") or "")[:10]
        try:
            from datetime import datetime as _dt
            activity = _dt.strptime(pushed, "%Y-%m-%d").date() if pushed else date.today()
        except ValueError:
            activity = date.today()
        touch_repo(
            SIMPLIFY_ORG,
            "New-Grad-Positions",
            url=f"https://github.com/{SIMPLIFY_ORG}/New-Grad-Positions",
            branch=default_branch,
            last_activity=activity,
            meta={"kind": "new-grad"},
        )
    return repos


def _fetch_json_listings(repo: str, branch: str) -> list[Job]:
    """Fetch and parse the listings.json file from a SimplifyJobs repo."""
    url = f"https://raw.githubusercontent.com/{SIMPLIFY_ORG}/{repo}/{branch}/.github/scripts/listings.json"
    resp = requests.get(url, timeout=60)
    if resp.status_code != 200:
        print(f"  [simplify] Could not fetch listings.json from {repo}: {resp.status_code}")
        return []

    data = json.loads(resp.text)
    jobs = []

    for entry in data:
        if not entry.get("active", False) or not entry.get("is_visible", True):
            continue
        if not entry.get("url"):
            continue

        dt = datetime.fromtimestamp(entry["date_posted"])
        posted = dt.date()

        locations = entry.get("locations", [])
        location_str = ", ".join(locations[:3])
        if len(locations) > 3:
            location_str += f" +{len(locations) - 3} more"

        sponsorship_raw = entry.get("sponsorship", "Other")
        info_parts = []
        mapped = SPONSORSHIP_MAP.get(sponsorship_raw, sponsorship_raw)
        if mapped:
            info_parts.append(mapped)

        degrees = entry.get("degrees", [])
        if degrees:
            info_parts.append(", ".join(degrees))

        category = _classify_role(entry.get("title", ""), entry.get("category", ""))
        terms = entry.get("terms", [])
        work_model = ""
        terms_lower = [t.lower() for t in terms]
        if any("remote" in t for t in terms_lower):
            work_model = "Remote"
        elif any("hybrid" in t for t in terms_lower):
            work_model = "Hybrid"

        jobs.append(Job(
            title=entry["title"],
            company=entry.get("company_name", "Unknown"),
            location=location_str or "Not Listed",
            url=entry["url"],
            date_posted=posted,
            source="SimplifyJobs",
            category=category,
            work_model=work_model,
            info=normalize_info_tags(*info_parts),
        ))

    print(f"  [simplify] Fetched {len(jobs)} active jobs from {repo} (JSON)")
    return jobs


def _parse_markdown_table(repo: str, branch: str) -> list[Job]:
    """Parse job listings from a SimplifyJobs README markdown table."""
    url = f"https://raw.githubusercontent.com/{SIMPLIFY_ORG}/{repo}/{branch}/README.md"
    resp = requests.get(url, timeout=30)
    if resp.status_code != 200:
        print(f"  [simplify] Could not fetch README from {repo}: {resp.status_code}")
        return []

    jobs = []
    lines = resp.text.splitlines()
    in_table = False

    for line in lines:
        line = line.strip()
        if not line.startswith("|"):
            in_table = False
            continue

        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) < 4:
            continue

        if any(c.startswith("---") or c.startswith(":--") for c in cells):
            in_table = True
            continue

        if not in_table:
            if "company" in cells[0].lower():
                continue
            continue

        if "🔒" in line:
            continue

        company_cell = cells[0].replace("↳", "").strip()
        company_match = re.search(r"\*\*\[?([^\]*]+)\]?", company_cell)
        company = company_match.group(1) if company_match else company_cell.strip("*")

        role = cells[1].strip()

        location = cells[2] if len(cells) > 2 else "Not Listed"
        location = re.sub(r"<[^>]+>", " ", location).strip()
        location = re.sub(r"\s+", " ", location)
        if len(location) > 80:
            location = location[:77] + "..."

        app_url = ""
        for cell in cells:
            url_match = re.search(r'href="([^"]+)"', cell)
            if url_match and "simplify.jobs" not in url_match.group(1):
                app_url = url_match.group(1)
                break
            url_match = re.search(r'\[([^\]]*)\]\(([^)]+)\)', cell)
            if url_match and "simplify.jobs" not in url_match.group(2):
                app_url = url_match.group(2)
                break

        if not app_url:
            continue

        info_parts = []
        if "🛂" in line:
            info_parts.append("No Sponsorship")
        if "🇺🇸" in line:
            info_parts.append("US Citizen Only")
        if "🎓" in line:
            info_parts.append("Advanced Degree")

        category = _classify_role(role)

        jobs.append(Job(
            title=role,
            company=company,
            location=location,
            url=app_url,
            date_posted=date.today(),
            source="SimplifyJobs",
            category=category,
            work_model="",
            info=" | ".join(info_parts) if info_parts else "",
        ))

    print(f"  [simplify] Parsed {len(jobs)} jobs from {repo} (Markdown)")
    return jobs


def _classify_role(title: str, category: str = "") -> str:
    """Classify a role into a broad category."""
    title_lower = title.lower()
    cat_lower = category.lower() if category else ""

    if any(kw in title_lower for kw in ["intern", "co-op", "coop"]):
        return "Internship"
    if any(kw in cat_lower for kw in ["data", "machine learning", "ml", "ai"]):
        return "Data/ML"
    if any(kw in title_lower for kw in ["data scientist", "data engineer", "data analyst", "machine learning", "ml engineer", "ai engineer"]):
        return "Data/ML"
    if any(kw in title_lower for kw in ["frontend", "front-end", "front end", "ui engineer", "react", "angular"]):
        return "Frontend"
    if any(kw in title_lower for kw in ["backend", "back-end", "back end", "server", "api engineer"]):
        return "Backend"
    if any(kw in title_lower for kw in ["full stack", "fullstack", "full-stack"]):
        return "Full Stack"
    if any(kw in title_lower for kw in ["devops", "sre", "site reliability", "infrastructure", "platform engineer", "cloud engineer"]):
        return "DevOps/Infra"
    if any(kw in title_lower for kw in ["security", "cybersecurity", "appsec"]):
        return "Security"
    if any(kw in title_lower for kw in ["mobile", "ios", "android", "flutter", "react native"]):
        return "Mobile"
    if any(kw in title_lower for kw in ["embedded", "firmware", "hardware"]):
        return "Embedded/HW"
    return "Software Engineering"


def scrape(year: int | None = None, include_previous: bool = True) -> list[Job]:
    """Scrape all SimplifyJobs repos and return unified job list."""
    if year is None:
        year = date.today().year

    all_jobs: list[Job] = []

    json_repos = _detect_json_repos(year, include_previous=include_previous)
    for repo, branch in json_repos.items():
        all_jobs.extend(_fetch_json_listings(repo, branch))

    newgrad_repos = _detect_newgrad_repos()
    for repo, branch in newgrad_repos.items():
        all_jobs.extend(_fetch_json_listings(repo, branch))

    archive_stale_repos(SIMPLIFY_ORG)
    print(f"  [simplify] Total: {len(all_jobs)} jobs from SimplifyJobs")
    return all_jobs
