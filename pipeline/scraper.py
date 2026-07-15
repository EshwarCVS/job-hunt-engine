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
            f"[Interactive Board](docs/board.html) to browse all* | | | | | |"
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

    contrib_section = "_Be the first community contributor this month — "
    contrib_section += "[add a job](CONTRIBUTING.md)!_"
    if contributors:
        chips = ", ".join(f"**{name}**" for name in contributors)
        contrib_section = f"Thanks to this month's contributors: {chips}."

    readme_content = f"""# Job Hunt Engine

Your open-source job board for tech roles — internships, new grad, and experienced.

<p>
  <a href="docs/board.html"><img src="{updated_badge}" alt="Last updated" /></a>
  <a href="docs/board.html"><img src="{count_badge}" alt="Job count" /></a>
  <a href="LICENSE"><img src="{license_badge}" alt="License" /></a>
  <img src="{sources_badge}" alt="Sources" />
</p>

**Quick links:** [Interactive Board (sort & filter)](docs/board.html) ·
[Contribute a job](CONTRIBUTING.md) ·
[Curator form](https://github.com/EshwarCVS/job-hunt-engine/issues/new?template=curator-submit.yml) ·
[Data sources](sources/README.md) ·
[How scraping works](pipeline/README.md) ·
[Credits](CREDITS.md) ·
[Issues](https://github.com/EshwarCVS/job-hunt-engine/issues)

**Support the project:** ⭐ [Star this repo](https://github.com/EshwarCVS/job-hunt-engine) · ⭐ [Star @EshwarCVS](https://github.com/EshwarCVS)

---

## Help wanted

This project stays useful when the community helps. We especially need:

- New / hard-to-find listings via [community PR or issue](CONTRIBUTING.md)
- Curators: paste posts with the [curator form](https://github.com/EshwarCVS/job-hunt-engine/issues/new?template=curator-submit.yml) (secret key + owned year/month folder)
- Bug reports for dead application links
- Improvements to scrapers and the interactive board — see [pipeline/README.md](pipeline/README.md)
- ⭐ Star [this repo](https://github.com/EshwarCVS/job-hunt-engine) and [@EshwarCVS](https://github.com/EshwarCVS) if it helps you

---

## {month_name} {year} Jobs

> **{job_count}** active listings · newest first · previous month: {prev_link} ·
> full list with **sort & filter**: [Interactive Board](docs/board.html)

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
- [Resume Tips](skills/resume-tips.md)
- [Interview Checklist](skills/interview-checklist.md)
- [ATS Optimization](skills/ats-optimization.md)
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
    """Standalone board with client-side sort + filter (works on GitHub Pages / local)."""
    BOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(job.to_html_row() for job in jobs)
    categories = sorted({j.category for j in jobs if j.category})
    sources = sorted({j.source for j in jobs if j.source})
    cat_opts = "\n".join(f'<option value="{c}">{c}</option>' for c in categories)
    src_opts = "\n".join(f'<option value="{s}">{s}</option>' for s in sources)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Job Hunt Engine — Board</title>
  <style>
    :root {{
      --bg: #f6f4ef;
      --ink: #1c1917;
      --muted: #57534e;
      --line: #d6d3d1;
      --accent: #0a66c2;
      --card: #fffcf7;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      background: radial-gradient(1200px 600px at 10% -10%, #dbeafe 0%, transparent 50%),
                  radial-gradient(900px 500px at 100% 0%, #fde68a 0%, transparent 45%),
                  var(--bg);
      color: var(--ink);
    }}
    header {{
      padding: 2rem 1.25rem 1rem; max-width: 1200px; margin: 0 auto;
    }}
    h1 {{ margin: 0 0 .35rem; font-size: clamp(1.6rem, 3vw, 2.2rem); }}
    .meta {{ color: var(--muted); margin-bottom: 1rem; }}
    .controls {{
      display: flex; flex-wrap: wrap; gap: .6rem; align-items: center;
      background: var(--card); border: 1px solid var(--line); border-radius: 12px;
      padding: .85rem; margin-bottom: 1rem;
    }}
    input, select, button {{
      font: inherit; padding: .45rem .65rem; border-radius: 8px;
      border: 1px solid var(--line); background: #fff;
    }}
    input {{ min-width: 220px; flex: 1; }}
    button {{
      background: var(--accent); color: #fff; border-color: var(--accent); cursor: pointer;
    }}
    main {{ max-width: 1200px; margin: 0 auto; padding: 0 1.25rem 3rem; }}
    .table-wrap {{
      overflow: auto; border: 1px solid var(--line); border-radius: 12px; background: var(--card);
    }}
    table {{ border-collapse: collapse; width: 100%; min-width: 900px; }}
    th, td {{ padding: .65rem .75rem; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ position: sticky; top: 0; background: #fafaf9; cursor: pointer; user-select: none; }}
    th:hover {{ color: var(--accent); }}
    tr.hidden {{ display: none; }}
    a {{ color: var(--accent); }}
    .count {{ font-size: .9rem; color: var(--muted); }}
  </style>
</head>
<body>
  <header>
    <h1>Job Hunt Engine</h1>
    <p class="meta">{today.strftime("%B %Y")} · generated {today.isoformat()} ·
      <a href="../README.md">Back to README</a>
    </p>
    <div class="controls">
      <input id="q" type="search" placeholder="Filter by role, company, location, info…" />
      <select id="category"><option value="">All categories</option>{cat_opts}</select>
      <select id="source"><option value="">All sources</option>{src_opts}</select>
      <button type="button" id="reset">Reset</button>
      <span class="count" id="count"></span>
    </div>
  </header>
  <main>
    <div class="table-wrap">
      <table id="jobs">
        <thead>
          <tr>
            <th data-key="date">Date</th>
            <th data-key="role">Role</th>
            <th data-key="company">Company</th>
            <th data-key="location">Location / Type</th>
            <th data-key="category">Category</th>
            <th data-key="source">Source</th>
            <th data-key="info">Info</th>
          </tr>
        </thead>
        <tbody>
{rows}
        </tbody>
      </table>
    </div>
  </main>
  <script>
    const q = document.getElementById('q');
    const category = document.getElementById('category');
    const source = document.getElementById('source');
    const count = document.getElementById('count');
    const tbody = document.querySelector('#jobs tbody');
    let sortKey = 'date';
    let sortAsc = false;

    function apply() {{
      const term = q.value.trim().toLowerCase();
      const cat = category.value;
      const src = source.value;
      let visible = 0;
      for (const row of tbody.rows) {{
        const hay = (row.dataset.company + ' ' + row.dataset.location + ' ' +
                     row.dataset.category + ' ' + row.dataset.source + ' ' +
                     row.dataset.info + ' ' + row.innerText).toLowerCase();
        const ok = (!term || hay.includes(term))
          && (!cat || row.dataset.category === cat)
          && (!src || row.dataset.source === src);
        row.classList.toggle('hidden', !ok);
        if (ok) visible++;
      }}
      count.textContent = visible + ' shown';
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
        else {{ av = a.cells[1].innerText; bv = b.cells[1].innerText; }}
        if (av < bv) return sortAsc ? -1 : 1;
        if (av > bv) return sortAsc ? 1 : -1;
        return 0;
      }});
      rows.forEach(r => tbody.appendChild(r));
    }}

    q.addEventListener('input', apply);
    category.addEventListener('change', apply);
    source.addEventListener('change', apply);
    document.getElementById('reset').addEventListener('click', () => {{
      q.value = ''; category.value = ''; source.value = ''; apply();
    }});
    document.querySelectorAll('th[data-key]').forEach(th => {{
      th.addEventListener('click', () => sortBy(th.dataset.key));
    }});
    apply();
  </script>
</body>
</html>
"""
    with open(BOARD_PATH, "w") as f:
        f.write(html)
    print(f"Updated {BOARD_PATH.relative_to(ROOT)}")


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

[← Back to Current Listings](../../README.md) · [Interactive Board](../../docs/board.html)

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
