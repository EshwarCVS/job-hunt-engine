# Pipeline: how scraping works

This document explains how Job Hunt Engine collects, filters, and publishes
listings so reviewers can suggest better approaches.

Run locally:

```bash
python -m pipeline.scraper
```

Config knobs: [`sources/config.json`](../sources/config.json).  
Source credentials / curator intake: [`sources/README.md`](../sources/README.md).

---

## End-to-end flow

```text
┌─────────────────┐   ┌──────────────────┐   ┌─────────────────┐
│ Source scrapers │ → │ Quality filters  │ → │ Deduplicate     │
│ (parallel-ish)  │   │ (real URLs only) │   │ (by apply URL)  │
└─────────────────┘   └──────────────────┘   └────────┬────────┘
                                                      ↓
                      ┌──────────────────┐   ┌─────────────────┐
                      │ README + board   │ ← │ Current-month   │
                      │ docs/board.html  │   │ jobs/YYYY/mon.md│
                      └──────────────────┘   └─────────────────┘
```

Implemented in [`scraper.py`](scraper.py) (`run()`).

### 1. Fetch sources

| Module | Source | What it pulls |
|--------|--------|----------------|
| [`sources/simplify.py`](sources/simplify.py) | SimplifyJobs GitHub | Active rows from `listings.json` |
| [`sources/jobright.py`](sources/jobright.py) | jobright-ai GitHub | README markdown tables |
| [`sources/linkedin_rss.py`](sources/linkedin_rss.py) | LinkedIn profiles | Optional; throttled; needs `LINKEDIN_LI_AT` |
| [`sources/community.py`](sources/community.py) | `sources/community-jobs.json` | PR / issue submissions |
| [`sources/curators.py`](sources/curators.py) | `sources/curators/<id>/<year>/<month>/jobs.json` | Keyed curator form |

Each source returns `list[Job]` ([`models.py`](models.py)). Failures in one source are logged; others continue.

Discovered GitHub repos are recorded in [`sources/repos.json`](../sources/repos.json) via [`registry.py`](registry.py).

### 2. Quality filter (no made-up rows)

Before dedup, listings must pass [`_is_real_listing`](scraper.py):

- `http`/`https` apply URL with a host  
- No placeholder hosts (`example.com`, demo greenhouse paths, etc.)  
- Non-empty real **title** and **company** (rejects `See Link`, `TODO`, …)

Then [`_filter_recent_active`](scraper.py) drops rows whose `date_posted` is older than
`active_listing_max_age_days` (default **60**).

`backfill_previous_month` defaults to **false** so we don’t recreate historical
month folders from prior-year seasonal repos.

### 3. Deduplication

[`deduplicator.py`](deduplicator.py) runs on the **current scrape batch** (across
sources). It does **not** merge against yesterday’s CSV for the published board;
each successful run rebuilds the board from this fetch + filters.

**Duplicate key** = apply URL with query string stripped, trailing `/` removed,
lowercased.

**On conflict:** keep the job with the **higher completeness score**, not the
newest date:

| Field | Points |
|-------|--------|
| `info` (visa / sponsorship / etc.) | +3 |
| `work_model` | +2 |
| concrete `location` | +2 |
| non-default `category` | +1 |
| concrete `company` | +1 |
| concrete `title` | +1 |
| `contributor` | +1 |

- Higher score → **replaces** the other copy  
- Tie or lower → **ignored** (first kept wins)  
- Surviving row keeps **its own** `date_posted` (date is not the tie-break)

### 4. Publish

- Persist snapshot: `pipeline/jobs_data.csv` (gitignored)  
- Archive **current calendar month only**: `jobs/YYYY/<month>.md`  
- Regenerate root `README.md` (collapsible preview) and `docs/board.html` (sort/filter)

Past month files are not invented from upstream timestamps. Prior archives appear
only if they were produced by real runs in those months.

### 5. Automation

[`.github/workflows/scrape-jobs.yml`](../.github/workflows/scrape-jobs.yml) runs
daily / on demand, commits as `EshwarCVS` when outputs change.

Curator issue form → [`.github/workflows/curator-submit.yml`](../.github/workflows/curator-submit.yml)
appends into the curator year/month folder after GitHub-secret key check.

---

## Design choices (open to challenge)

| Choice | Current behavior | Why |
|--------|------------------|-----|
| Fresh scrape replaces board | Don’t merge old CSV into README | Avoids resurrecting stale / backfilled archives |
| Dedup by URL | One row per apply link | Same role often appears in multiple aggregators |
| Score over date | Prefer richer metadata | H1B/location from one source beats a sparse newer copy |
| Max age window | Drop very old `date_posted` | Keeps the board “currently useful” |
| LinkedIn optional + throttled | Every N days, secret cookie | ToS / block risk; curators preferred for that signal |

---

## Suggest a better approach

Open an issue or PR if you have ideas such as:

- Deduping by company + role (fuzzy) when URLs differ  
- Preferring **newest** `date_posted` on ties, or merging fields from both rows  
- Incremental sync (merge with previous CSV) without bringing back junk  
- Official board APIs instead of README/`listings.json` scraping  
- Safer LinkedIn alternatives (curator form only, licensed feeds)

Tag ideas with **pipeline** or reference this doc so maintainers can compare tradeoffs.

See also [CONTRIBUTING.md](../CONTRIBUTING.md) and [CREDITS.md](../CREDITS.md).
