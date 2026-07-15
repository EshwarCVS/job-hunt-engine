# Contributing to Job Hunt Engine

Thanks for helping make job hunting easier for everyone.

## Branching

| Branch | Role |
|--------|------|
| **`master`** | Public board — what everyone should look at |
| **`develop`** | Queue / workspace — curator JSON, community PRs, scrape runs here first |

Flow: contributions → `develop` → daily **Scrape Jobs + Publish** Action scrapes on `develop`, then merges to `master` so both tips match.

Open PRs against **`develop`**.

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

## Who approves community job submissions?

| Path | What happens | Who publishes to the board |
|------|----------------|----------------------------|
| **Add Job Listing** issue | Creates a labeled issue (`job-submission`). **Not auto-merged.** | A **maintainer** (repo admin) reviews, then opens/merges a PR that adds the row to `sources/community-jobs.json`, **or** closes as duplicate/spam |
| **PR** editing `community-jobs.json` | CI / review on the PR | Maintainer **merges** the PR → next scrape includes it |
| **Curator form** | Authed by `CURATOR_KEYS` secret | **Automated** append on **`develop`** if the key matches; public board updates on next scrape→`master` publish |

There is no anonymous auto-write for public job issues — that would spam the board. Curators are the exception because they share a passphrase stored in GitHub Secrets.

## Curator submissions (owned space + `CURATOR_KEYS`)

**Want curator access?** Open
[Request curator access](https://github.com/EshwarCVS/job-hunt-engine/issues/new?template=curator-request.yml).
Maintainers create a passphrase in GitHub Secrets and send it **privately** (usually LinkedIn DM). No email server required.

Curators get `sources/curators/<id>/<year>/<month>/jobs.json`.

**One secret for every curator** (no workflow change when onboarding):

1. Add the person to `sources/curators/_index.json`
2. Edit GitHub **Actions secret** `CURATOR_KEYS` (JSON), e.g.
   `{"eshwarchandravidhyasagar":"<passphrase>","CURATOR_ESHWARCHANDRAVIDHYASAGAR":"<passphrase>"}`
3. DM them the passphrase **privately** (never in a public issue/PR)
4. They submit via the [curator form](https://github.com/EshwarCVS/job-hunt-engine/issues/new?template=curator-submit.yml)

Alias formula: `CURATOR_` + id in screaming case → e.g. `eshwarchandravidhyasagar` → `CURATOR_ESHWARCHANDRAVIDHYASAGAR`.

Details: [`sources/curators/ONBOARDING.md`](sources/curators/ONBOARDING.md) (full checklist) and
[`sources/curators/README.md`](sources/curators/README.md).

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

## Contribution attribution

Curator ingest commits are attributed to the person who contributed when we can:

1. Optional **GitHub username** on the form
2. Registered `github` on their curator row in `_index.json`
3. The GitHub account that opened the issue
4. Otherwise the maintainer from `sources/config.json` → `commit_author`

So curators who use GitHub get credit on the contribution graph. Board scrape/publish commits stay under the maintainer identity.

When merging community **Add Job** issues by hand, attribute the commit to the issue author (or add `Co-authored-by: login <id+login@users.noreply.github.com>`).

## Questions?

Open an issue. Contributions of all sizes are welcome.
