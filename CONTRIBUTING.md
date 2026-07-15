# Contributing to Job Hunt Engine

Thanks for helping make job hunting easier for everyone.

## Ways to contribute

| Path | Best for |
|------|----------|
| [Add Job Listing](https://github.com/EshwarCVS/job-hunt-engine/issues/new?template=add-job.yml) issue | One-off community jobs |
| PR editing `sources/community-jobs.json` | Batch community jobs |
| [Curator submission](https://github.com/EshwarCVS/job-hunt-engine/issues/new?template=curator-submit.yml) | Trusted curators (keyed) |
| PRs to scrapers / docs | Pipeline & UX improvements |

How scraping, filters, and dedup work (feedback welcome):
**[pipeline/README.md](pipeline/README.md)**.

⭐ **If this repo helps you, please star it** — and consider starring
[EshwarCVS](https://github.com/EshwarCVS) on GitHub too. Stars help others find
open-source job tools.

## Adding Job Listings (community)

### Option 1: Pull Request

Add an entry to `sources/community-jobs.json` and open a PR titled
`Add: Company Name — Role Title`.

### Option 2: Issue form

Use [Add Job Listing](https://github.com/EshwarCVS/job-hunt-engine/issues/new?template=add-job.yml).

### Job entry fields

| Field | Required | Example |
|-------|----------|---------|
| `title` | Yes | Software Engineer |
| `company` | Yes | Google |
| `location` | Yes | Mountain View, CA |
| `url` | Yes | https://careers.google.com/... |
| `date` | Yes | 2026-07-14 |
| `category` | No | Software Engineering |
| `work_model` | No | Remote |
| `info` | No | H1B Sponsor |
| `contributor` | No | alice |

### Info tags

`H1B Sponsor`, `H1B (Historical)`, `No Sponsorship`, `US Citizen Only`,
`Advanced Degree`, `New Grad`, seniority labels.

## Curator submissions (owned space + GitHub secret key)

Curators get `sources/curators/<id>/<year>/<month>/jobs.json`.

**Keys are GitHub Actions secrets — not files in the repo.**

1. Maintainer runs `python -m pipeline.generate_curator_key <id>` (prints a key; does not write the repo).
2. Maintainer adds it under **Settings → Secrets and variables → Actions** as `CURATOR_KEY_<ID>`.
3. Maintainer DMs the key to the curator.
4. Curator opens the [curator form](https://github.com/EshwarCVS/job-hunt-engine/issues/new?template=curator-submit.yml), pastes **curator id + key + post**.
5. Actions compares the form key to the secret. On match it appends `jobs.json` and redacts the key.

Details: [`sources/curators/README.md`](sources/curators/README.md).

## Adding scrapers / sources

Read **[pipeline/README.md](pipeline/README.md)** first (fetch → filter → dedup → publish).
Suggestions for better dedup, incremental sync, or official APIs are welcome as issues/PRs.

To add a scraper:

1. New module under `pipeline/sources/`
2. Return `list[Job]`
3. Wire into `pipeline/scraper.py`
4. Prefer voluntary curator / community intake over brittle authenticated scraping

## Reporting issues

Broken links, duplicates, or scraper errors — open an issue with details.

## Code style

- Python 3.12+
- Keep dependencies minimal (`pipeline/requirements.txt`)
- Type hints encouraged; scrapers should not crash on odd upstream HTML/JSON

## Credits

See [CREDITS.md](CREDITS.md) for how we cite SimplifyJobs, jobright-ai, and this project.

## Questions?

Open an issue. Contributions of all sizes are welcome.
