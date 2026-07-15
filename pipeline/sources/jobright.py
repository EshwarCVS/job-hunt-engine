"""Scrape job listings from jobright-ai GitHub repos.

Auto-detects repos from the jobright-ai org matching known naming patterns,
then parses the markdown tables from each repo's README.
"""

import re
from datetime import date, datetime

import requests

from pipeline.models import Job

JOBRIGHT_ORG = "jobright-ai"
GITHUB_API = "https://api.github.com"

REPO_PATTERNS = [
    r"\d{4}-Software-Engineer-New-Grad",
    r"\d{4}-Software-Engineer-Internship",
    r"\d{4}-Data-Analysis-New-Grad",
    r"\d{4}-Data-Analysis-Internship",
    r"Daily-H1B-Jobs-In-Tech",
]


def _discover_repos(year: int) -> list[dict]:
    """Discover relevant repos from the jobright-ai org."""
    repos = []
    page = 1
    while True:
        url = f"{GITHUB_API}/orgs/{JOBRIGHT_ORG}/repos?per_page=100&page={page}"
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            break
        data = resp.json()
        if not data:
            break
        for repo in data:
            name = repo["name"]
            for pattern in REPO_PATTERNS:
                if re.match(pattern, name):
                    if name.startswith("Daily-") or str(year) in name or str(year + 1) in name:
                        repos.append({
                            "name": name,
                            "branch": repo.get("default_branch", "master"),
                            "is_h1b": "H1B" in name,
                        })
                    break
        page += 1

    print(f"  [jobright] Discovered {len(repos)} repos: {[r['name'] for r in repos]}")
    return repos


def _parse_swe_table(readme: str, repo_name: str) -> list[Job]:
    """Parse SWE/Data repo tables: Company | Job Title | Location | Work Model | Date Posted"""
    jobs = []
    lines = readme.splitlines()
    in_table = False
    current_company = ""

    for line in lines:
        line = line.strip()
        if not line.startswith("|"):
            in_table = False
            continue

        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) < 5:
            continue

        if any(c.startswith("---") or c.startswith(":--") or c == "-----" for c in cells):
            in_table = True
            continue

        if not in_table:
            continue

        company_cell = cells[0].replace("↳", "").strip()
        if company_cell and company_cell != "":
            company_match = re.search(r"\*\*\[([^\]]+)\]", company_cell)
            if company_match:
                current_company = company_match.group(1)
            else:
                company_match = re.search(r"\*\*([^*]+)\*\*", company_cell)
                if company_match:
                    current_company = company_match.group(1)

        title_cell = cells[1]
        title_match = re.search(r"\*\*\[([^\]]+)\]\(([^)]+)\)", title_cell)
        if not title_match:
            continue
        title = title_match.group(1)
        url = title_match.group(2)

        location = cells[2] if len(cells) > 2 else "Not Listed"
        work_model = cells[3] if len(cells) > 3 else ""
        date_str = cells[4] if len(cells) > 4 else ""

        posted = _parse_date(date_str)
        category = _classify_from_repo(repo_name, title)

        is_intern = "Internship" in repo_name or "intern" in title.lower()

        jobs.append(Job(
            title=title,
            company=current_company or "Unknown",
            location=location,
            url=url,
            date_posted=posted,
            source="jobright-ai",
            category="Internship" if is_intern else category,
            work_model=work_model,
            info="",
        ))

    return jobs


def _parse_h1b_table(readme: str) -> list[Job]:
    """Parse H1B repo table: Company | Job Title | Level | Location | H1B status | Link | Date Posted"""
    jobs = []
    lines = readme.splitlines()
    in_table = False

    for line in lines:
        line = line.strip()
        if not line.startswith("|"):
            in_table = False
            continue

        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) < 7:
            continue

        if any(c.startswith("---") or c.startswith(":--") for c in cells):
            in_table = True
            continue

        if not in_table:
            continue

        company_match = re.search(r"\*\*\[([^\]]+)\]", cells[0])
        company = company_match.group(1) if company_match else cells[0].strip("* ")

        title = cells[1].strip()
        level = cells[2].strip()
        location = cells[3].strip()
        h1b_status = cells[4].strip()
        link_cell = cells[5]
        date_str = cells[6].strip()

        url_match = re.search(r"\[apply\]\(([^)]+)\)", link_cell)
        if not url_match:
            continue
        url = url_match.group(1)

        info_parts = []
        if "🏅" in h1b_status:
            info_parts.append("H1B Sponsor")
        elif "🥈" in h1b_status:
            info_parts.append("H1B (Historical)")
        if level:
            info_parts.append(level)

        posted = _parse_date(date_str)
        category = _classify_from_repo("H1B", title)

        jobs.append(Job(
            title=title,
            company=company,
            location=location if location != "REMOTE" else "Remote",
            url=url,
            date_posted=posted,
            source="jobright-ai",
            category=category,
            work_model="Remote" if location == "REMOTE" else "",
            info=" | ".join(info_parts) if info_parts else "",
        ))

    return jobs


def _parse_date(date_str: str) -> date:
    """Parse various date formats from jobright tables."""
    date_str = date_str.strip()
    today = date.today()

    for fmt in ["%Y-%m-%d", "%b %d", "%B %d"]:
        try:
            parsed = datetime.strptime(date_str, fmt).date()
            if parsed.year == 1900:
                parsed = parsed.replace(year=today.year)
            return parsed
        except ValueError:
            continue

    return today


def _classify_from_repo(repo_name: str, title: str) -> str:
    """Classify role category based on repo name and title."""
    title_lower = title.lower()
    if "Data-Analysis" in repo_name or "data" in title_lower:
        if any(kw in title_lower for kw in ["scientist", "machine learning", "ml", "ai"]):
            return "Data/ML"
        return "Data/ML"
    if any(kw in title_lower for kw in ["frontend", "front-end", "react", "angular", "ui engineer"]):
        return "Frontend"
    if any(kw in title_lower for kw in ["backend", "back-end", "api", "server"]):
        return "Backend"
    if any(kw in title_lower for kw in ["full stack", "fullstack"]):
        return "Full Stack"
    if any(kw in title_lower for kw in ["devops", "sre", "infrastructure", "platform", "cloud"]):
        return "DevOps/Infra"
    if any(kw in title_lower for kw in ["mobile", "ios", "android"]):
        return "Mobile"
    return "Software Engineering"


def scrape(year: int | None = None) -> list[Job]:
    """Scrape all jobright-ai repos and return unified job list."""
    if year is None:
        year = date.today().year

    repos = _discover_repos(year)
    all_jobs: list[Job] = []

    for repo_info in repos:
        name = repo_info["name"]
        branch = repo_info["branch"]
        url = f"https://raw.githubusercontent.com/{JOBRIGHT_ORG}/{name}/{branch}/README.md"

        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            print(f"  [jobright] Could not fetch README from {name}: {resp.status_code}")
            continue

        if repo_info["is_h1b"]:
            jobs = _parse_h1b_table(resp.text)
        else:
            jobs = _parse_swe_table(resp.text, name)

        print(f"  [jobright] Parsed {len(jobs)} jobs from {name}")
        all_jobs.extend(jobs)

    print(f"  [jobright] Total: {len(all_jobs)} jobs from jobright-ai")
    return all_jobs
