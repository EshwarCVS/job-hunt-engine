#!/usr/bin/env python3
"""Main scraper orchestrator.

Fetches jobs from all sources, deduplicates, merges with existing data,
handles monthly rollover / backfill, and generates README + archives + board.
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote, urlparse

from pipeline.deduplicator import deduplicate
from pipeline.models import Job
from pipeline.registry import load_config, load_registry
from pipeline.sources import community, curators, jobright, linkedin_rss, simplify

ROOT = Path(__file__).parent.parent
JOBS_DIR = ROOT / "jobs"
README_PATH = ROOT / "README.md"
BOARD_PATH = ROOT / "docs" / "board.html"
BOARD_INDEX_PATH = ROOT / "docs" / "index.html"
PAGES_URL = "https://eshwarcvs.github.io/job-hunt-engine"
REPO_URL = "https://github.com/EshwarCVS/job-hunt-engine"
EXISTING_JOBS_CSV = ROOT / "pipeline" / "jobs_data.csv"
CONTRIBUTORS_FILE = ROOT / "sources" / "contributors.json"

MONTH_NAMES = [
    "", "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]

TABLE_HEADER = """| Date | Role | Company | Location / Type | Category | Source | Info |
|------|------|---------|-----------------|----------|--------|------|"""


def run():
    """Main entry point for the scraper."""
    today = date.today()
    config = load_config()
    print(f"=== Job Hunt Engine Scraper — {today.isoformat()} ===\n")

    # Do not backfill prior-year seasonal repos unless explicitly enabled.
    backfill = bool(config.get("backfill_previous_month", False))
    max_age_days = int(config.get("active_listing_max_age_days", 60))

    print("Fetching from sources...")
    new_jobs: list[Job] = []

    try:
        new_jobs.extend(simplify.scrape(today.year, include_previous=backfill))
    except Exception as e:
        print(f"  [ERROR] SimplifyJobs scraper failed: {e}")

    try:
        new_jobs.extend(jobright.scrape(today.year, include_previous=backfill))
    except Exception as e:
        print(f"  [ERROR] jobright-ai scraper failed: {e}")

    try:
        lookback = int(config.get("linkedin_lookback_days", 7))
        new_jobs.extend(linkedin_rss.scrape(lookback_days=lookback))
    except Exception as e:
        print(f"  [ERROR] LinkedIn scraper failed: {e}")

    try:
        new_jobs.extend(community.scrape())
    except Exception as e:
        print(f"  [ERROR] Community jobs loader failed: {e}")

    try:
        new_jobs.extend(curators.scrape())
    except Exception as e:
        print(f"  [ERROR] Curator submissions loader failed: {e}")

    print(f"\nTotal fetched: {len(new_jobs)} jobs")

    # Fresh runs win for the board: drop stale CSV history that created fake month archives.
    scraped = [_normalize_job(j) for j in new_jobs]
    scraped = [j for j in scraped if _is_real_listing(j)]
    scraped = _filter_recent_active(scraped, today, max_age_days)
    all_jobs = deduplicate(scraped)
    _save_jobs_csv(all_jobs)

    # Only maintain the current calendar month archive (real scrape result for this run).
    _handle_monthly_rollover(all_jobs, today)
    current_month_jobs = sorted(all_jobs, key=lambda j: j.date_posted, reverse=True)
    _update_month_file(current_month_jobs, today)

    print(
        f"After dedup / quality filter: {len(current_month_jobs)} active jobs "
        f"({MONTH_NAMES[today.month].title()} {today.year} board)"
    )

    month_contributors = _collect_month_contributors(current_month_jobs, today)
    _update_readme(current_month_jobs, today, month_contributors)
    _write_board_html(current_month_jobs, today)

    print("\nDone!")


def _normalize_job(job: Job) -> Job:
    job.url = (job.url or "").strip()
    job.title = (job.title or "").strip()
    job.company = (job.company or "").strip()
    return job


def _is_real_listing(job: Job) -> bool:
    """Reject missing/placeholder links so we never publish made-up rows."""
    url = (job.url or "").strip()
    if not url:
        return False
    lower = url.lower()
    banned = (
        "example.com", "example.org", "localhost", "127.0.0.1",
        "boards.greenhouse.io/example", "boards.greenhouse.io/demo",
        "javascript:", "about:blank",
    )
    if any(b in lower for b in banned):
        return False
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    if not job.title or job.title in {"See Link", "-", "TODO", "TBD"}:
        return False
    if not job.company or job.company in {"See Link", "-", "TODO", "TBD", "ExampleCorp", "DemoCo"}:
        return False
    return True


def _filter_recent_active(jobs: list[Job], today: date, max_age_days: int) -> list[Job]:
    """Keep currently relevant listings only (no multi-year historical dump)."""
    cutoff = today - timedelta(days=max_age_days)
    kept = [j for j in jobs if j.date_posted >= cutoff]
    dropped = len(jobs) - len(kept)
    if dropped:
        print(f"  [filter] Dropped {dropped} listings older than {max_age_days} days")
    return kept


def _handle_monthly_rollover(current_jobs: list[Job], today: date) -> None:
    """If last month's archive is missing but CSV from a prior run exists, skip inventing it.

    Past months are only kept if already written by a previous real scrape day in that month.
    We never synthesize 2025 / early-2026 archives from upstream timestamps.
    """
    # Intentionally no-op for synthesis. Cleanup of unknown months is explicit below.
    _remove_untracked_month_files(today)


def _remove_untracked_month_files(today: date) -> None:
    """Delete archive markdown files that are not the current month (stale backfills)."""
    if not JOBS_DIR.exists():
        return
    keep_name = f"{MONTH_NAMES[today.month]}.md"
    for year_dir in JOBS_DIR.iterdir():
        if not year_dir.is_dir() or year_dir.name.startswith("."):
            continue
        try:
            year = int(year_dir.name)
        except ValueError:
            continue
        for path in list(year_dir.glob("*.md")):
            if year == today.year and path.name == keep_name:
                continue
            print(f"  [archive] Removing stale archive {path.relative_to(ROOT)}")
            path.unlink(missing_ok=True)
        # Remove empty year dirs except current year
        if year != today.year and not any(year_dir.iterdir()):
            year_dir.rmdir()
        elif year != today.year and not list(year_dir.glob("*.md")):
            for leftover in year_dir.iterdir():
                if leftover.is_file():
                    leftover.unlink()
            if not any(year_dir.iterdir()):
                year_dir.rmdir()


def _load_existing_jobs() -> list[Job]:
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
            job = Job(
                title=row.get("title", ""),
                company=row.get("company", ""),
                location=row.get("location", ""),
                url=row.get("url", ""),
                date_posted=posted,
                source=row.get("source", ""),
                category=row.get("category", ""),
                work_model=row.get("work_model", ""),
                info=row.get("info", ""),
                contributor=row.get("contributor", ""),
            )
            if _is_real_listing(job):
                jobs.append(job)
    return jobs


def _save_jobs_csv(jobs: list[Job]):
    fields = [
        "date_posted", "title", "company", "location", "url",
        "source", "category", "work_model", "info", "contributor",
    ]
    EXISTING_JOBS_CSV.parent.mkdir(parents=True, exist_ok=True)
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
                "contributor": job.contributor,
            })


def _collect_month_contributors(jobs: list[Job], today: date) -> list[str]:
    names: set[str] = set()
    for job in jobs:
        if job.contributor:
            names.add(job.contributor)
        if job.source == "Community" and job.contributor:
            names.add(job.contributor)

    if CONTRIBUTORS_FILE.exists():
        try:
            with open(CONTRIBUTORS_FILE) as f:
                data = json.load(f)
            for entry in data:
                if isinstance(entry, str):
                    names.add(entry)
                elif isinstance(entry, dict):
                    month = entry.get("month")
                    if month and month != today.strftime("%Y-%m"):
                        continue
                    if entry.get("name"):
                        names.add(entry["name"])
        except (json.JSONDecodeError, OSError):
            pass

    return sorted(names, key=str.lower)


def _generate_job_table(jobs: list[Job], *, limit: int | None = None) -> str:
    if not jobs:
        return (
            "_No verified listings for this period yet. "
            "Jobs appear after the next successful scrape from public sources "
            "or a community/curator submission with a real application URL._"
        )

    subset = jobs if limit is None else jobs[:limit]
    lines = [TABLE_HEADER]
    for job in subset:
        lines.append(job.to_table_row())
    if limit is not None and len(jobs) > limit:
        lines.append(
            f"| … | *+{len(jobs) - limit} more — use "
            f"[Interactive Board]({PAGES_URL}/) to browse all* | | | | | |"
        )
    return "\n".join(lines)


def _badge(label: str, message: str, color: str) -> str:
    """Build a shields.io badge URL that won't 404 on hyphens in the message."""
    return (
        f"https://img.shields.io/static/v1?"
        f"label={quote(label)}&message={quote(message)}&color={quote(color)}"
    )


def _prev_month_link(today: date) -> str:
    if today.month == 1:
        prev_month, prev_year = 12, today.year - 1
    else:
        prev_month, prev_year = today.month - 1, today.year

    prev_path = JOBS_DIR / str(prev_year) / f"{MONTH_NAMES[prev_month]}.md"
    label = f"{MONTH_NAMES[prev_month].title()} {prev_year}"
    if prev_path.exists() and prev_path.stat().st_size > 0:
        return f"[{label}](jobs/{prev_year}/{MONTH_NAMES[prev_month]}.md)"
    return "_no prior archive yet_"


def _update_month_file(jobs: list[Job], today: date) -> None:
    year_dir = JOBS_DIR / str(today.year)
    year_dir.mkdir(parents=True, exist_ok=True)
    path = year_dir / f"{MONTH_NAMES[today.month]}.md"
    _write_month_file(jobs, today.year, today.month, path)


def _registry_summary_md() -> str:
    registry = load_registry()
    lines = [
        "Tracked source repositories (auto-updated each scrape). "
        "Inactive repos are archived after the threshold in "
        "[`sources/config.json`](sources/config.json).",
        "",
    ]
    orgs = registry.get("orgs", {})
    if not orgs:
        lines.append("_No repositories registered yet — they appear after the first successful scrape._")
        return "\n".join(lines)

    for org, data in sorted(orgs.items()):
        active = data.get("active", [])
        archived = data.get("archived", [])
        lines.append(f"### {org}")
        lines.append("")
        if active:
            lines.append("**Active**")
            lines.append("")
            for repo in active:
                url = repo.get("url") or f"https://github.com/{org}/{repo['name']}"
                last = repo.get("last_activity") or repo.get("last_seen") or "?"
                lines.append(f"- [{repo['name']}]({url}) — last activity `{last}`")
            lines.append("")
        if archived:
            lines.append("<details>")
            lines.append(f"<summary>Archived ({len(archived)})</summary>")
            lines.append("")
            for repo in archived:
                url = repo.get("url") or f"https://github.com/{org}/{repo['name']}"
                reason = repo.get("archive_reason") or "archived"
                lines.append(f"- [{repo['name']}]({url}) — {reason}")
            lines.append("")
            lines.append("</details>")
            lines.append("")
    return "\n".join(lines)


def _update_readme(jobs: list[Job], today: date, contributors: list[str]):
    month_name = MONTH_NAMES[today.month].title()
    year = today.year
    job_count = len(jobs)
    prev_link = _prev_month_link(today)

    # Keep README readable: collapse table; full interactive board has everything
    preview_limit = 80
    job_table = _generate_job_table(jobs, limit=preview_limit)

    updated_badge = _badge("last updated", today.isoformat(), "0A66C2")
    count_badge = _badge("jobs this month", str(job_count), "2ea44f")
    license_badge = _badge("license", "MIT", "informational")
    sources_badge = _badge("sources", "Simplify · jobright · LinkedIn · Community", "6f42c1")

    website_badge = _badge("website", "GitHub Pages", "222")

    contrib_section = "_Be the first community contributor this month — "
    contrib_section += "[add a job](CONTRIBUTING.md)!_"
    if contributors:
        chips = ", ".join(f"**{name}**" for name in contributors)
        contrib_section = f"Thanks to this month's contributors: {chips}."

    readme_content = f"""# Job Hunt Engine

Your open-source job board for tech roles — internships, new grad, and experienced.

**Website (sort & filter):** {PAGES_URL}/

<p>
  <a href="{PAGES_URL}/"><img src="{updated_badge}" alt="Last updated" /></a>
  <a href="{PAGES_URL}/"><img src="{count_badge}" alt="Job count" /></a>
  <a href="LICENSE"><img src="{license_badge}" alt="License" /></a>
  <a href="{PAGES_URL}/"><img src="{website_badge}" alt="Website" /></a>
  <img src="{sources_badge}" alt="Sources" />
</p>

**Quick links:** [Interactive Board (sort & filter)]({PAGES_URL}/) ·
[Contribute a job](CONTRIBUTING.md) ·
[Curator form](https://github.com/EshwarCVS/job-hunt-engine/issues/new?template=curator-submit.yml) ·
[Curator onboarding (maintainers)](sources/curators/ONBOARDING.md) ·
[Data sources](sources/README.md) ·
[How scraping works](pipeline/README.md) ·
[Credits](CREDITS.md) ·
[Security](SECURITY.md) ·
[Code of Conduct](CODE_OF_CONDUCT.md) ·
[Issues](https://github.com/EshwarCVS/job-hunt-engine/issues)

**Support the project:** ⭐ [Star this repo](https://github.com/EshwarCVS/job-hunt-engine) · ⭐ [Star @EshwarCVS](https://github.com/EshwarCVS)

---

## Help wanted

This project stays useful when the community helps. We especially need:

- New / hard-to-find listings via [community PR or issue](CONTRIBUTING.md)
- Curators: paste posts with the [curator form](https://github.com/EshwarCVS/job-hunt-engine/issues/new?template=curator-submit.yml) (secret key + owned year/month folder) · [request access](https://github.com/EshwarCVS/job-hunt-engine/issues/new?template=curator-request.yml)
- Bug reports for dead application links
- Improvements to scrapers and the interactive board ([live site]({PAGES_URL}/)) — see [pipeline/README.md](pipeline/README.md)
- ⭐ Star [this repo](https://github.com/EshwarCVS/job-hunt-engine) and [@EshwarCVS](https://github.com/EshwarCVS) if it helps you

---

## {month_name} {year} Jobs

> **{job_count}** active listings · newest first · previous month: {prev_link} ·
> full list with **sort & filter**: [Interactive Board]({PAGES_URL}/)

<details open>
<summary><strong>Job listings</strong> (click to collapse / expand) — preview of {min(job_count, preview_limit)} / {job_count}</summary>

{job_table}

</details>

---

## Job Archives

Browse previous months:

"""

    year_dirs = sorted(JOBS_DIR.iterdir()) if JOBS_DIR.exists() else []
    for year_dir in year_dirs:
        if not year_dir.is_dir() or year_dir.name.startswith("."):
            continue
        month_files = sorted(
            year_dir.glob("*.md"),
            key=lambda p: MONTH_NAMES.index(p.stem) if p.stem in MONTH_NAMES else 99,
        )
        if month_files:
            links = [f"[{mf.stem.title()}](jobs/{year_dir.name}/{mf.name})" for mf in month_files]
            readme_content += f"- **{year_dir.name}**: " + " | ".join(links) + "\n"

    readme_content += f"""
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
- [Resume Tips](skills/resume-tips.md) — plus [LinkedIn resume checklist](https://www.linkedin.com/posts/eshwarchandravidhyasagar_resumetips-jobsearch-softwareengineering-activity-7458586210945490946-1yzF) and [live resume review](https://www.linkedin.com/posts/eshwarchandravidhyasagar_resumereview-jobsearch-careersupport-share-7450549819946835968-e_pG)
- [Interview Checklist](skills/interview-checklist.md)
- [ATS Optimization](skills/ats-optimization.md)
- [Vigilant Lamp](https://github.com/EshwarCVS/vigilant-lamp) — learning tracks (SDE, data, FDE, systems)
- [More Resources](resources.md)

---

## Data Sources

| Source | What it provides | Config |
|--------|------------------|--------|
| [SimplifyJobs](https://github.com/SimplifyJobs) | Internships & new grad | [`sources/repos.json`](sources/repos.json) |
| [jobright-ai](https://github.com/jobright-ai) | SWE, Data, H1B by level | [`sources/repos.json`](sources/repos.json) |
| [LinkedIn profiles](sources/linkedin-profiles.json) | Hiring posts (throttled) | [`linkedin-profiles.json`](sources/linkedin-profiles.json) |
| [Curators](sources/curators/README.md) | Voluntary posts via keyed form | [`sources/curators/`](sources/curators/) |
| Community PRs | Submitted listings | [`community-jobs.json`](sources/community-jobs.json) |

### Source repository registry

{_registry_summary_md()}

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) to:

- Submit job listings via Pull Request or issue
- Curators: use the [keyed submission form](https://github.com/EshwarCVS/job-hunt-engine/issues/new?template=curator-submit.yml)
- Add LinkedIn profiles / new scrapers
- Report broken links

### Contributors — {month_name} {year}

{contrib_section}

---

## Credits & citations

This project is open source ([MIT](LICENSE)) and stands on upstream open data.
Please keep attribution when you reuse it.

- Full citations: **[CREDITS.md](CREDITS.md)**
- Upstream orgs: [SimplifyJobs](https://github.com/SimplifyJobs), [jobright-ai](https://github.com/jobright-ai)
- Curator spaces: [`sources/curators/`](sources/curators/)

Suggested blurb:

> Based on [Job Hunt Engine](https://github.com/EshwarCVS/job-hunt-engine) (MIT).
> Live board: {PAGES_URL}/
> Job data also attributed to SimplifyJobs, jobright-ai, and community curators.

---

## License

MIT — see [LICENSE](LICENSE).

> **Disclaimer**: Listings are aggregated from public and voluntarily submitted sources. Always verify details on the company's official careers page before applying.
"""

    with open(README_PATH, "w") as f:
        f.write(readme_content)

    print(f"Updated README.md with {job_count} jobs for {month_name} {year}")


def _write_board_html(jobs: list[Job], today: date) -> None:
    """Standalone interactive board for GitHub Pages (sort / filter / paginate)."""
    BOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(job.to_html_row() for job in jobs)
    categories = sorted({j.category for j in jobs if j.category})
    sources = sorted({j.source for j in jobs if j.source})
    cat_opts = "\n".join(f'<option value="{c}">{c}</option>' for c in categories)
    src_opts = "\n".join(f'<option value="{s}">{s}</option>' for s in sources)
    total = len(jobs)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="description" content="Browse and filter {total} tech jobs. Apply from the board." />
  <title>Job Hunt Engine — Board</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&family=Fragment+Mono:wght@400&display=swap" rel="stylesheet" />
  <style>
    :root {{
      --bg: #f3efe6;
      --ink: #1a1f16;
      --muted: #5c6554;
      --line: #d5d0c4;
      --accent: #0f6a4b;
      --accent-2: #c45c26;
      --card: #fffcf5;
      --shadow: 0 10px 30px rgba(26, 31, 22, .06);
      --sticky-top: 0;
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      font-family: "DM Sans", "Segoe UI", sans-serif;
      background:
        radial-gradient(900px 420px at 0% -5%, rgba(15, 106, 75, .12), transparent 55%),
        radial-gradient(700px 380px at 100% 0%, rgba(196, 92, 38, .10), transparent 50%),
        linear-gradient(180deg, #ebe5d8 0%, var(--bg) 28%, #efe9db 100%);
      color: var(--ink);
      min-height: 100vh;
    }}
    .shell {{ max-width: 1220px; margin: 0 auto; padding: 1.25rem 1.1rem 4rem; }}
    .hero {{
      display: grid; gap: .55rem; margin-bottom: 1rem;
      animation: rise .45s ease both;
    }}
    @keyframes rise {{
      from {{ opacity: 0; transform: translateY(8px); }}
      to {{ opacity: 1; transform: none; }}
    }}
    .eyebrow {{
      font-family: "Fragment Mono", ui-monospace, monospace;
      font-size: .78rem; letter-spacing: .04em; text-transform: uppercase;
      color: var(--accent); margin: 0;
    }}
    h1 {{
      margin: 0; font-size: clamp(1.85rem, 4vw, 2.55rem); line-height: 1.1;
      letter-spacing: -.02em;
    }}
    .lede {{ margin: 0; max-width: 46rem; color: var(--muted); font-size: 1.02rem; }}
    .meta-row {{
      display: flex; flex-wrap: wrap; gap: .65rem .9rem; align-items: center;
      color: var(--muted); font-size: .92rem;
    }}
    .meta-row a {{ color: var(--accent); font-weight: 600; text-decoration: none; }}
    .meta-row a:hover {{ text-decoration: underline; }}
    .toolbar {{
      position: sticky; top: 0; z-index: 20;
      margin: 1rem 0 .85rem;
      padding: .85rem;
      background: color-mix(in srgb, var(--card) 92%, transparent);
      backdrop-filter: blur(10px);
      border: 1px solid var(--line);
      border-radius: 16px;
      box-shadow: var(--shadow);
      animation: rise .5s ease .05s both;
    }}
    .controls {{
      display: flex; flex-wrap: wrap; gap: .55rem; align-items: center;
    }}
    .chips {{
      display: flex; flex-wrap: wrap; gap: .4rem; margin-top: .65rem;
    }}
    .chip {{
      border: 1px solid var(--line); background: #fff; color: var(--ink);
      border-radius: 999px; padding: .32rem .7rem; font-size: .86rem; cursor: pointer;
      transition: border-color .15s, background .15s, color .15s, transform .15s;
    }}
    .chip:hover {{ transform: translateY(-1px); border-color: var(--accent); }}
    .chip.active {{
      background: var(--accent); color: #fff; border-color: var(--accent);
    }}
    label.inline {{
      color: var(--muted); font-size: .88rem;
      display: inline-flex; gap: .35rem; align-items: center;
    }}
    input, select, button {{
      font: inherit; padding: .48rem .7rem; border-radius: 10px;
      border: 1px solid var(--line); background: #fff; color: var(--ink);
    }}
    input#q {{ min-width: min(100%, 260px); flex: 1.4; }}
    button {{
      background: var(--accent); color: #fff; border-color: var(--accent); cursor: pointer;
      font-weight: 600;
    }}
    button:hover:not(:disabled) {{ filter: brightness(1.05); }}
    button:disabled {{ opacity: .4; cursor: not-allowed; }}
    button.secondary {{
      background: #fff; color: var(--ink); border-color: var(--line); font-weight: 500;
    }}
    .count {{ font-size: .88rem; color: var(--muted); white-space: nowrap; }}
    .pager {{
      display: flex; flex-wrap: wrap; gap: .55rem; align-items: center;
      justify-content: space-between;
      margin: .75rem 0;
      padding: .7rem .8rem;
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 14px;
    }}
    .pager-nav {{ display: flex; flex-wrap: wrap; gap: .4rem; align-items: center; }}
    .table-wrap {{
      overflow: auto; border: 1px solid var(--line); border-radius: 16px;
      background: var(--card); box-shadow: var(--shadow);
      max-height: min(72vh, 920px);
    }}
    table {{ border-collapse: separate; border-spacing: 0; width: 100%; min-width: 980px; }}
    th, td {{
      padding: .72rem .78rem; border-bottom: 1px solid var(--line);
      text-align: left; vertical-align: top; font-size: .94rem;
    }}
    th {{
      position: sticky; top: 0; z-index: 5;
      background: #f7f3ea; cursor: pointer; user-select: none;
      font-size: .8rem; letter-spacing: .02em; text-transform: uppercase; color: var(--muted);
    }}
    th:hover {{ color: var(--accent); }}
    tbody tr {{ transition: background .12s ease; }}
    tbody tr:hover {{ background: #f4faf6; }}
    tr.hidden {{ display: none; }}
    .date {{
      font-family: "Fragment Mono", ui-monospace, monospace;
      font-size: .82rem; color: var(--muted); white-space: nowrap;
    }}
    .role-link {{
      color: var(--ink); font-weight: 600; text-decoration: none;
    }}
    .role-link:hover {{ color: var(--accent); text-decoration: underline; }}
    .pill {{
      display: inline-block; padding: .15rem .45rem; border-radius: 999px;
      background: #e8f3ec; color: #0f6a4b; font-size: .78rem; font-weight: 600;
      white-space: nowrap;
    }}
    .apply-col {{ white-space: nowrap; }}
    .apply-btn {{
      display: inline-flex; align-items: center; justify-content: center;
      padding: .38rem .7rem; border-radius: 999px;
      background: var(--accent-2); color: #fff !important; font-weight: 700;
      font-size: .82rem; text-decoration: none !important;
      box-shadow: 0 1px 0 rgba(0,0,0,.06);
      transition: transform .12s ease, filter .12s ease;
    }}
    .apply-btn:hover {{ transform: translateY(-1px); filter: brightness(1.05); }}
    .tip {{
      margin-top: 1rem; color: var(--muted); font-size: .88rem;
    }}
    #toTop {{
      position: fixed; right: 1rem; bottom: 1rem; z-index: 30;
      width: 2.6rem; height: 2.6rem; border-radius: 999px;
      display: grid; place-items: center; font-size: 1.1rem;
      box-shadow: var(--shadow); opacity: 0; pointer-events: none;
      transition: opacity .2s ease, transform .2s ease;
      transform: translateY(8px);
    }}
    #toTop.show {{ opacity: 1; pointer-events: auto; transform: none; }}
    @media (max-width: 720px) {{
      .table-wrap {{ max-height: 65vh; }}
      input#q {{ min-width: 100%; flex: 1 1 100%; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <header class="hero">
      <p class="eyebrow">Open-source · updated daily</p>
      <h1>Job Hunt Engine</h1>
      <p class="lede">Filter thousands of tech roles, then hit <strong>Apply</strong> — stays in your browser, no account.</p>
      <div class="meta-row">
        <span>{today.strftime("%B %Y")} · {total} listings · generated {today.isoformat()}</span>
        <a href="{REPO_URL}">GitHub</a>
        <a href="{REPO_URL}#readme">README</a>
        <a href="{PAGES_URL}/">Website</a>
      </div>
    </header>

    <div class="toolbar" id="toolbar">
      <div class="controls">
        <input id="q" type="search" placeholder="Search role, company, location, visa…" autocomplete="off" />
        <select id="category" aria-label="Category"><option value="">All categories</option>{cat_opts}</select>
        <select id="source" aria-label="Source"><option value="">All sources</option>{src_opts}</select>
        <label class="inline">Per page
          <select id="pageSize" aria-label="Rows per page">
            <option value="25">25</option>
            <option value="50" selected>50</option>
            <option value="75">75</option>
            <option value="100">100</option>
          </select>
        </label>
        <button type="button" id="reset" class="secondary">Reset</button>
        <span class="count" id="count"></span>
      </div>
      <div class="chips" id="chips" role="group" aria-label="Quick filters">
        <button type="button" class="chip" data-flag="remote">Remote</button>
        <button type="button" class="chip" data-flag="newgrad">New grad</button>
        <button type="button" class="chip" data-flag="intern">Internship</button>
        <button type="button" class="chip" data-flag="visa">Visa / H1B</button>
      </div>
    </div>

    <div class="pager" id="pagerTop">
      <div class="pager-nav">
        <button type="button" class="secondary" data-nav="first">« First</button>
        <button type="button" class="secondary" data-nav="prev">‹ Prev</button>
        <span class="count" data-page-info></span>
        <button type="button" class="secondary" data-nav="next">Next ›</button>
        <button type="button" class="secondary" data-nav="last">Last »</button>
      </div>
      <label class="inline">Go to
        <input data-goto type="number" min="1" step="1" style="min-width:4.2rem;flex:0" />
      </label>
    </div>

    <div class="table-wrap" id="tableWrap">
      <table id="jobs">
        <thead>
          <tr>
            <th data-key="date">Date</th>
            <th data-key="role">Role</th>
            <th data-key="company">Company</th>
            <th data-key="location">Location</th>
            <th data-key="category">Category</th>
            <th data-key="source">Source</th>
            <th data-key="info">Info</th>
            <th>Apply</th>
          </tr>
        </thead>
        <tbody>
{rows}
        </tbody>
      </table>
    </div>

    <div class="pager" id="pagerBottom">
      <div class="pager-nav">
        <button type="button" class="secondary" data-nav="first">« First</button>
        <button type="button" class="secondary" data-nav="prev">‹ Prev</button>
        <span class="count" data-page-info></span>
        <button type="button" class="secondary" data-nav="next">Next ›</button>
        <button type="button" class="secondary" data-nav="last">Last »</button>
      </div>
      <label class="inline">Go to
        <input data-goto type="number" min="1" step="1" style="min-width:4.2rem;flex:0" />
      </label>
    </div>
    <p class="tip">Tip: click column headers to sort. Use chips for Remote / New grad / Intern / Visa. Open roles in a new tab so you keep browsing.</p>
  </div>
  <button type="button" id="toTop" class="secondary" aria-label="Back to top">↑</button>

  <script>
    const q = document.getElementById('q');
    const category = document.getElementById('category');
    const source = document.getElementById('source');
    const pageSizeEl = document.getElementById('pageSize');
    const count = document.getElementById('count');
    const tbody = document.querySelector('#jobs tbody');
    const activeFlags = new Set();
    let sortKey = 'date';
    let sortAsc = false;
    let page = 1;

    // Backfill Apply + flags for older generated rows
    for (const row of tbody.rows) {{
      const link = row.querySelector('a[href]');
      if (!row.dataset.flags) {{
        const blob = (row.innerText || '').toLowerCase();
        const flags = [];
        if (blob.includes('remote')) flags.push('remote');
        if (blob.includes('new grad') || blob.includes('new college') || blob.includes('entry level')) flags.push('newgrad');
        if (blob.includes('intern') && !blob.includes('internal')) flags.push('intern');
        if (blob.includes('h1b') || blob.includes('sponsor')) flags.push('visa');
        row.dataset.flags = flags.join(' ');
      }}
      if (link && !row.querySelector('.apply-btn')) {{
        const td = document.createElement('td');
        td.className = 'apply-col';
        td.innerHTML = `<a class="apply-btn" href="${{link.href}}" rel="noopener noreferrer" target="_blank">Apply</a>`;
        row.appendChild(td);
        link.classList.add('role-link');
      }}
      const dateCell = row.cells[0];
      if (dateCell && !dateCell.querySelector('.date')) {{
        dateCell.innerHTML = `<span class="date">${{dateCell.textContent}}</span>`;
      }}
    }}

    function matchedRows() {{
      const term = q.value.trim().toLowerCase();
      const cat = category.value;
      const src = source.value;
      const out = [];
      for (const row of tbody.rows) {{
        const hay = (row.dataset.company + ' ' + row.dataset.location + ' ' +
                     row.dataset.category + ' ' + row.dataset.source + ' ' +
                     row.dataset.info + ' ' + row.innerText).toLowerCase();
        const flags = (row.dataset.flags || '').split(/\\s+/).filter(Boolean);
        const flagOk = [...activeFlags].every(f => flags.includes(f));
        const ok = (!term || hay.includes(term))
          && (!cat || row.dataset.category === cat)
          && (!src || row.dataset.source === src)
          && flagOk;
        if (ok) out.push(row);
      }}
      return out;
    }}

    function syncPagers(totalPages) {{
      document.querySelectorAll('[data-page-info]').forEach(el => {{
        el.textContent = `Page ${{page}} / ${{totalPages}}`;
      }});
      document.querySelectorAll('[data-goto]').forEach(el => {{
        el.value = String(page);
        el.max = String(totalPages);
      }});
      document.querySelectorAll('[data-nav]').forEach(btn => {{
        const action = btn.dataset.nav;
        if (action === 'first' || action === 'prev') btn.disabled = page <= 1;
        if (action === 'next' || action === 'last') btn.disabled = page >= totalPages;
      }});
    }}

    function apply() {{
      const matched = matchedRows();
      const pageSize = Math.max(1, parseInt(pageSizeEl.value, 10) || 50);
      const totalPages = Math.max(1, Math.ceil(matched.length / pageSize));
      if (page > totalPages) page = totalPages;
      if (page < 1) page = 1;
      const start = (page - 1) * pageSize;
      const end = start + pageSize;
      const onPage = new Set(matched.slice(start, end));

      for (const row of tbody.rows) {{
        row.classList.toggle('hidden', !onPage.has(row));
      }}

      const from = matched.length ? start + 1 : 0;
      const to = Math.min(end, matched.length);
      count.textContent = matched.length
        ? `Showing ${{from}}–${{to}} of ${{matched.length}}`
        : '0 matches';
      syncPagers(totalPages);
    }}

    function resetPageAndApply() {{
      page = 1;
      apply();
      document.getElementById('tableWrap').scrollTop = 0;
    }}

    function sortBy(key) {{
      if (sortKey === key) sortAsc = !sortAsc;
      else {{ sortKey = key; sortAsc = key !== 'date'; }}
      const rows = Array.from(tbody.rows);
      rows.sort((a, b) => {{
        let av, bv;
        if (key === 'date') {{ av = a.dataset.date; bv = b.dataset.date; }}
        else if (key === 'company') {{ av = a.dataset.company; bv = b.dataset.company; }}
        else if (key === 'location') {{ av = a.dataset.location; bv = b.dataset.location; }}
        else if (key === 'category') {{ av = a.dataset.category; bv = b.dataset.category; }}
        else if (key === 'source') {{ av = a.dataset.source; bv = b.dataset.source; }}
        else if (key === 'info') {{ av = a.dataset.info; bv = b.dataset.info; }}
        else {{
          av = (a.querySelector('.role-link') || a.cells[1]).innerText;
          bv = (b.querySelector('.role-link') || b.cells[1]).innerText;
        }}
        if (av < bv) return sortAsc ? -1 : 1;
        if (av > bv) return sortAsc ? 1 : -1;
        return 0;
      }});
      rows.forEach(r => tbody.appendChild(r));
      resetPageAndApply();
    }}

    q.addEventListener('input', resetPageAndApply);
    category.addEventListener('change', resetPageAndApply);
    source.addEventListener('change', resetPageAndApply);
    pageSizeEl.addEventListener('change', resetPageAndApply);
    document.getElementById('reset').addEventListener('click', () => {{
      q.value = ''; category.value = ''; source.value = '';
      pageSizeEl.value = '50'; page = 1; activeFlags.clear();
      document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
      apply();
    }});
    document.querySelectorAll('.chip').forEach(chip => {{
      chip.addEventListener('click', () => {{
        const flag = chip.dataset.flag;
        if (activeFlags.has(flag)) {{ activeFlags.delete(flag); chip.classList.remove('active'); }}
        else {{ activeFlags.add(flag); chip.classList.add('active'); }}
        resetPageAndApply();
      }});
    }});
    document.querySelectorAll('[data-nav]').forEach(btn => {{
      btn.addEventListener('click', () => {{
        const pageSize = Math.max(1, parseInt(pageSizeEl.value, 10) || 50);
        const totalPages = Math.max(1, Math.ceil(matchedRows().length / pageSize));
        const action = btn.dataset.nav;
        if (action === 'first') page = 1;
        if (action === 'prev') page -= 1;
        if (action === 'next') page += 1;
        if (action === 'last') page = totalPages;
        apply();
        document.getElementById('tableWrap').scrollTop = 0;
      }});
    }});
    document.querySelectorAll('[data-goto]').forEach(el => {{
      el.addEventListener('change', () => {{
        const pageSize = Math.max(1, parseInt(pageSizeEl.value, 10) || 50);
        const totalPages = Math.max(1, Math.ceil(matchedRows().length / pageSize));
        page = Math.min(totalPages, Math.max(1, parseInt(el.value, 10) || 1));
        apply();
      }});
    }});
    document.querySelectorAll('th[data-key]').forEach(th => {{
      th.addEventListener('click', () => sortBy(th.dataset.key));
    }});
    const toTop = document.getElementById('toTop');
    window.addEventListener('scroll', () => {{
      toTop.classList.toggle('show', window.scrollY > 480);
    }}, {{ passive: true }});
    toTop.addEventListener('click', () => window.scrollTo({{ top: 0, behavior: 'smooth' }}));
    apply();
  </script>
</body>
</html>
"""
    BOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    (BOARD_PATH.parent / ".nojekyll").write_text("", encoding="utf-8")
    with open(BOARD_PATH, "w") as f:
        f.write(html)
    with open(BOARD_INDEX_PATH, "w") as f:
        f.write(html)
    print(f"Updated {BOARD_PATH.relative_to(ROOT)} + {BOARD_INDEX_PATH.relative_to(ROOT)}")
    print(f"  Public board: {PAGES_URL}/")


def _write_month_file(jobs: list[Job], year: int, month: int, filepath: Path):
    month_name = MONTH_NAMES[month].title()
    job_table = _generate_job_table(jobs)

    nav_links = []
    if month == 1:
        prev_m, prev_y = 12, year - 1
    else:
        prev_m, prev_y = month - 1, year

    prev_file = filepath.parent.parent / str(prev_y) / f"{MONTH_NAMES[prev_m]}.md"
    if prev_file.exists():
        if prev_y != year:
            nav_links.append(f"[← {MONTH_NAMES[prev_m].title()} {prev_y}](../{prev_y}/{MONTH_NAMES[prev_m]}.md)")
        else:
            nav_links.append(f"[← {MONTH_NAMES[prev_m].title()}]({MONTH_NAMES[prev_m]}.md)")

    if month == 12:
        next_m, next_y = 1, year + 1
    else:
        next_m, next_y = month + 1, year
    next_file = filepath.parent.parent / str(next_y) / f"{MONTH_NAMES[next_m]}.md"
    if next_file.exists():
        if next_y != year:
            nav_links.append(f"[{MONTH_NAMES[next_m].title()} {next_y} →](../{next_y}/{MONTH_NAMES[next_m]}.md)")
        else:
            nav_links.append(f"[{MONTH_NAMES[next_m].title()} →]({MONTH_NAMES[next_m]}.md)")

    nav = " | ".join(nav_links) if nav_links else ""

    content = f"""# {month_name} {year} Jobs

[← Back to Current Listings]({REPO_URL}#readme) · [Interactive Board]({PAGES_URL}/)

{nav}

> **{len(jobs)}** listings for {month_name} {year}

<details open>
<summary><strong>Job listings</strong> (click to collapse / expand)</summary>

{job_table}

</details>

---

{nav}
"""
    with open(filepath, "w") as f:
        f.write(content)
    print(f"Updated {filepath.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    run()
