# Job Hunt Engine

Open-source community job aggregator for tech roles at all levels.

## Architecture

- `pipeline/scraper.py` — main orchestrator, run via `python -m pipeline.scraper`
- `pipeline/sources/` — one module per data source (simplify, jobright, linkedin, community)
- `pipeline/models.py` — `Job` dataclass, shared across all sources
- `pipeline/deduplicator.py` — URL-based dedup
- `sources/` — config files for data sources (LinkedIn profiles, community submissions)
- `jobs/YYYY/month.md` — monthly archives with navigation links
- `.github/workflows/scrape-jobs.yml` — daily GitHub Actions cron

## Running locally

```
python3.12 -m venv .venv
.venv/bin/pip install -r pipeline/requirements.txt
.venv/bin/python -m pipeline.scraper
```

Set `LINKEDIN_LI_AT` env var to enable LinkedIn scraping.

## Data sources

- **SimplifyJobs**: fetches `listings.json` from their repos (structured JSON)
- **jobright-ai**: auto-discovers repos from the org, parses README markdown tables
- **LinkedIn**: uses `li_at` cookie to fetch profile activity pages, extracts job URLs
- **Community**: loads `sources/community-jobs.json` submitted via PRs

## Key behaviors

- Monthly rollover: archives current month to `jobs/YYYY/month.md` when a new month starts
- Auto-detection: discovers new repos from SimplifyJobs and jobright-ai orgs automatically
- Dedup: by normalized URL, keeps the entry with the most metadata
- README: regenerated each run with current month's jobs + tips/resources
