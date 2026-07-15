#!/usr/bin/env python3
"""Main scraper orchestrator.

Fetches jobs from all sources, deduplicates, merges with existing data,
handles monthly rollover, and generates the README and month archive files.
"""

import csv
import io
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

from pipeline.deduplicator import deduplicate
from pipeline.models import Job
from pipeline.sources import community, jobright, linkedin_rss, simplify

ROOT = Path(__file__).parent.parent
JOBS_DIR = ROOT / "jobs"
README_PATH = ROOT / "README.md"
EXISTING_JOBS_CSV = ROOT / "pipeline" / "jobs_data.csv"

MONTH_NAMES = [
    "", "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]

TABLE_HEADER = """| Date | Role | Company | Location | Category | Type | Source | Info |
|------|------|---------|----------|----------|------|--------|------|"""


def run():
    """Main entry point for the scraper."""
    today = date.today()
    print(f"=== Job Hunt Engine Scraper — {today.isoformat()} ===\n")

    _handle_monthly_rollover(today)

    print("Fetching from sources...")
    new_jobs: list[Job] = []

    try:
        new_jobs.extend(simplify.scrape(today.year))
    except Exception as e:
        print(f"  [ERROR] SimplifyJobs scraper failed: {e}")

    try:
        new_jobs.extend(jobright.scrape(today.year))
    except Exception as e:
        print(f"  [ERROR] jobright-ai scraper failed: {e}")

    try:
        new_jobs.extend(linkedin_rss.scrape())
    except Exception as e:
        print(f"  [ERROR] LinkedIn scraper failed: {e}")

    try:
        new_jobs.extend(community.scrape())
    except Exception as e:
        print(f"  [ERROR] Community jobs loader failed: {e}")

    print(f"\nTotal fetched: {len(new_jobs)} jobs")

    existing_jobs = _load_existing_jobs(today)
    all_jobs = existing_jobs + new_jobs
    all_jobs = deduplicate(all_jobs)

    current_month_jobs = [j for j in all_jobs if j.date_posted.year == today.year and j.date_posted.month == today.month]
    current_month_jobs.sort(key=lambda j: j.date_posted, reverse=True)

    print(f"After dedup: {len(current_month_jobs)} jobs for {MONTH_NAMES[today.month].title()} {today.year}")

    _save_jobs_csv(all_jobs)
    _update_readme(current_month_jobs, today)
    _update_month_file(current_month_jobs, today)

    print("\nDone!")


def _handle_monthly_rollover(today: date):
    """If we're in a new month, ensure last month's data is archived."""
    if today.month == 1:
        prev_month, prev_year = 12, today.year - 1
    else:
        prev_month, prev_year = today.month - 1, today.year

    prev_month_file = JOBS_DIR / str(prev_year) / f"{MONTH_NAMES[prev_month]}.md"
    year_dir = JOBS_DIR / str(prev_year)
    year_dir.mkdir(parents=True, exist_ok=True)

    if prev_month_file.exists():
        return

    prev_jobs = _load_jobs_for_month(prev_year, prev_month)
    if prev_jobs:
        print(f"Archiving {len(prev_jobs)} jobs to {prev_month_file}")
        _write_month_file(prev_jobs, prev_year, prev_month, prev_month_file)


def _load_existing_jobs(today: date) -> list[Job]:
    """Load existing jobs from the CSV data file."""
    if not EXISTING_JOBS_CSV.exists():
        return []

    jobs = []
    with open(EXISTING_JOBS_CSV, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                posted = datetime.strptime(row["date_posted"], "%Y-%m-%d").date()
            except (ValueError, KeyError):
                continue
            jobs.append(Job(
                title=row.get("title", ""),
                company=row.get("company", ""),
                location=row.get("location", ""),
                url=row.get("url", ""),
                date_posted=posted,
                source=row.get("source", ""),
                category=row.get("category", ""),
                work_model=row.get("work_model", ""),
                info=row.get("info", ""),
            ))
    return jobs


def _load_jobs_for_month(year: int, month: int) -> list[Job]:
    """Load jobs for a specific month from the CSV."""
    all_jobs = _load_existing_jobs(date.today())
    return [j for j in all_jobs if j.date_posted.year == year and j.date_posted.month == month]


def _save_jobs_csv(jobs: list[Job]):
    """Save all jobs to a CSV for persistence between runs."""
    fields = ["date_posted", "title", "company", "location", "url", "source", "category", "work_model", "info"]

    with open(EXISTING_JOBS_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for job in sorted(jobs, key=lambda j: j.date_posted, reverse=True):
            writer.writerow({
                "date_posted": job.date_posted.isoformat(),
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "url": job.url,
                "source": job.source,
                "category": job.category,
                "work_model": job.work_model,
                "info": job.info,
            })


def _generate_job_table(jobs: list[Job]) -> str:
    """Generate a markdown table from a list of jobs."""
    if not jobs:
        return f"{TABLE_HEADER}\n| - | No jobs found yet | - | - | - | - | - | - |"

    lines = [TABLE_HEADER]
    for job in jobs:
        lines.append(job.to_table_row())
    return "\n".join(lines)


def _update_readme(jobs: list[Job], today: date):
    """Update the root README.md with the current month's jobs."""
    month_name = MONTH_NAMES[today.month].title()
    year = today.year
    job_table = _generate_job_table(jobs)
    job_count = len(jobs)

    if today.month == 1:
        prev_month, prev_year = 12, today.year - 1
    else:
        prev_month, prev_year = today.month - 1, today.year

    prev_month_name = MONTH_NAMES[prev_month].title()
    prev_month_link = f"[{prev_month_name} {prev_year}](jobs/{prev_year}/{MONTH_NAMES[prev_month]}.md)"

    readme_content = f"""# Job Hunt Engine

Your one-stop, open-source job board for tech roles. Updated daily via automated scrapers.

![Jobs Updated](https://img.shields.io/badge/last_updated-{today.isoformat()}-blue)
![Job Count](https://img.shields.io/badge/jobs_this_month-{job_count}-green)

---

## {month_name} {year} Jobs

> **{job_count}** active listings | Sorted by date (newest first) | {prev_month_link}

{job_table}

---

## Job Archives

Browse previous months:

"""

    year_dirs = sorted(JOBS_DIR.iterdir()) if JOBS_DIR.exists() else []
    for year_dir in year_dirs:
        if not year_dir.is_dir() or year_dir.name.startswith("."):
            continue
        month_files = sorted(year_dir.glob("*.md"))
        if month_files:
            links = []
            for mf in month_files:
                mname = mf.stem.title()
                links.append(f"[{mname}](jobs/{year_dir.name}/{mf.name})")
            readme_content += f"- **{year_dir.name}**: " + " | ".join(links) + "\n"

    readme_content += """
---

## Tips & Tricks

### Resume Optimization
- **Tailor your resume** for each application — match keywords from the job description
- **Quantify impact** — "Reduced API latency by 40%" beats "Improved performance"
- **ATS-friendly format** — use standard section headers, avoid tables/columns, stick to PDF
- **One page** for < 5 years experience, two pages max for senior roles

### Application Strategy
- **Apply early** — most roles fill within 2 weeks of posting
- **Track everything** — use a spreadsheet or tool to avoid duplicate applications
- **Referrals matter** — a referral increases your callback rate by 5-10x
- **Don't self-reject** — apply if you meet 60%+ of the requirements

### Interview Preparation
- **System design** — practice with real-world scenarios, not just textbook patterns
- **Behavioral questions** — prepare 8-10 STAR stories covering leadership, conflict, failure, and impact
- **Coding practice** — LeetCode medium-level problems, focus on patterns not memorization
- **Research the company** — know their product, recent news, and tech stack

### Negotiation
- **Always negotiate** — the first offer is rarely the best offer
- **Get competing offers** — leverage is your best friend
- **Consider total comp** — base, bonus, equity, benefits, and growth potential
- **Get it in writing** — verbal offers aren't binding

### Resources
- [Resume Tips](skills/resume-tips.md) — detailed resume writing guide
- [Interview Checklist](skills/interview-checklist.md) — pre-interview preparation checklist
- [ATS Optimization](skills/ats-optimization.md) — beat the Applicant Tracking System
- [More Resources](resources.md) — tools, communities, and learning materials

---

## Data Sources

| Source | What it Provides | Update Frequency |
|--------|-----------------|------------------|
| [SimplifyJobs](https://github.com/SimplifyJobs) | Internship & new grad roles | Every 30 min |
| [jobright-ai](https://github.com/jobright-ai) | SWE, Data, H1B roles by level | Hourly |
| [LinkedIn Posts](sources/linkedin-feeds.json) | Curated posts from industry leaders | Daily |
| Community PRs | Jobs submitted by contributors | Ongoing |

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for how to:
- Submit job listings via Pull Request
- Add new data sources
- Report broken links
- Improve the scraper pipeline

---

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.

> **Disclaimer**: Job listings are aggregated from public sources. We don't guarantee accuracy or availability. Always verify details on the company's official careers page before applying.
"""

    with open(README_PATH, "w") as f:
        f.write(readme_content)

    print(f"Updated README.md with {job_count} jobs for {month_name} {year}")


def _update_month_file(jobs: list[Job], today: date):
    """Write/update the current month's archive file."""
    year_dir = JOBS_DIR / str(today.year)
    year_dir.mkdir(parents=True, exist_ok=True)
    month_file = year_dir / f"{MONTH_NAMES[today.month]}.md"
    _write_month_file(jobs, today.year, today.month, month_file)


def _write_month_file(jobs: list[Job], year: int, month: int, filepath: Path):
    """Write a month archive markdown file with navigation links."""
    month_name = MONTH_NAMES[month].title()
    job_table = _generate_job_table(jobs)

    nav_links = []
    if month == 1:
        prev_m, prev_y = 12, year - 1
    else:
        prev_m, prev_y = month - 1, year

    prev_file = filepath.parent.parent / str(prev_y) / f"{MONTH_NAMES[prev_m]}.md"
    if prev_file.exists() or prev_y == year:
        if prev_y != year:
            nav_links.append(f"[← {MONTH_NAMES[prev_m].title()} {prev_y}](../{prev_y}/{MONTH_NAMES[prev_m]}.md)")
        else:
            nav_links.append(f"[← {MONTH_NAMES[prev_m].title()}]({MONTH_NAMES[prev_m]}.md)")

    if month == 12:
        next_m, next_y = 1, year + 1
    else:
        next_m, next_y = month + 1, year

    if next_y != year:
        nav_links.append(f"[{MONTH_NAMES[next_m].title()} {next_y} →](../{next_y}/{MONTH_NAMES[next_m]}.md)")
    else:
        nav_links.append(f"[{MONTH_NAMES[next_m].title()} →]({MONTH_NAMES[next_m]}.md)")

    nav = " | ".join(nav_links) if nav_links else ""

    content = f"""# {month_name} {year} Jobs

[← Back to Current Listings](../../README.md)

{nav}

> **{len(jobs)}** listings for {month_name} {year}

{job_table}

---

{nav}
"""

    with open(filepath, "w") as f:
        f.write(content)

    print(f"Updated {filepath.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    run()
