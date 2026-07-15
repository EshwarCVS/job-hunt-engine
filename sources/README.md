# Data Sources Configuration

**Live board (sort & filter):** https://eshwarcvs.github.io/job-hunt-engine/

Admin-tunable settings live in [`config.json`](config.json). Discovered GitHub
repos are tracked in [`repos.json`](repos.json).

**How fetching, filtering, and dedup work** (open for suggestions):
[`pipeline/README.md`](../pipeline/README.md).

## config.json

| Key | Default | Meaning |
|-----|---------|---------|
| `archive_inactive_days` | `30` | Archive a tracked repo after this many days without activity (set `14`, `30`, `60`, etc.) |
| `linkedin_lookback_days` | `7` | How far back LinkedIn posts are collected |
| `linkedin_default_scrape_every_days` | `3` | Default min days between profile scrapes (override per profile) |
| `backfill_previous_month` | `false` | If true, also scrape prior-year seasonal repos. Left off so we don't invent historical archives. |
| `active_listing_max_age_days` | `60` | Drop listings whose upstream `date_posted` is older than this |

## repos.json

Auto-maintained registry of org/account repositories.

- **active** — currently scraped
- **archived** — moved here when `last_activity` is older than `archive_inactive_days`

Example seasonal flow: `SimplifyJobs/Summer2026-Internships` stays active through
the season; when a 2027 repo appears and 2026 goes quiet, the old one is archived
automatically (or sooner if you lower the threshold).

You can manually move entries between `active` and `archived` in a PR.

## linkedin-profiles.json

Generic list of LinkedIn profiles to mine for hiring links.

```json
[
  {
    "username": "eshwarchandravidhyasagar",
    "display_name": "Eshwar Chandra Vidhyasagar",
    "url": "https://www.linkedin.com/in/eshwarchandravidhyasagar/",
    "tags": ["swe", "new-grad", "internships"],
    "active": true,
    "scrape_every_days": 3,
    "notes": "Optional context for maintainers"
  }
]
```

| Field | Required | Notes |
|-------|----------|-------|
| `username` | Yes* | LinkedIn slug (`/in/{username}/`). *Or derive from `url` |
| `url` | Yes* | Profile URL. *Or build from `username` |
| `display_name` | No | Shown in contributor / via credits |
| `tags` | No | Free-form labels to organize profiles |
| `active` | No | Default `true`. Set `false` to pause without deleting |
| `scrape_every_days` | No | Min days between scrapes for this profile (default from config: 3) |
| `notes` | No | Maintainer notes |

### LinkedIn cookie setup (one-time)

1. Open [linkedin.com](https://www.linkedin.com) while logged in
2. DevTools → **Application** → **Cookies** → `linkedin.com`
3. Copy the **`li_at`** cookie value
4. GitHub repo → **Settings → Secrets and variables → Actions**
5. Create secret `LINKEDIN_LI_AT` with that value

Never commit the cookie. Use `.env` locally (gitignored) or Actions secrets only.

Listings respect **`scrape_every_days`** (Madhan = 3). State is stored in
`linkedin-state.json` and only advances after a successful scrape. Daily Actions
still run Simplify/jobright; Playwright/LinkedIn only install when a profile is due.
Force a scrape via workflow_dispatch → `force_linkedin=true`, or locally
`FORCE_LINKEDIN=1`.

### Reducing LinkedIn blocks (workarounds)

LinkedIn actively throttles automation. Same `li_at` used from GitHub Actions IPs
daily is risky. Mitigations already in this project:

1. **Slow cadence** — scrape each profile every N days (not daily).
2. **Skip Playwright** on days nothing is due (less automation footprint).
3. **Cookie rotation** — optional pool of secondary accounts:
   - `LINKEDIN_LI_AT` — primary
   - `LINKEDIN_LI_AT_2` — alternate account cookie
   - `LINKEDIN_LI_AT_POOL` — comma/newline-separated cookies  
   The scraper picks one cookie per day (`day % pool_size`).
4. **Human-ish pacing** — random delays, viewport, user-agent; fewer scrolls.
5. **Don't reuse your main personal account** for scraping — use a secondary
   LinkedIn account you can afford to lose if restricted.
6. **Refresh cookies** when you see login/authwall in logs; expired/`li_at`
   banned cookies fail closed without advancing the schedule.
7. Prefer community + GitHub sources as the high-volume path; treat LinkedIn as
   a low-frequency bonus signal, not a hard dependency.

There is no fully reliable public workaround — LinkedIn ToS disallows bots.
Cadence + rotation + secondary accounts are the practical approach.

## community-jobs.json

Jobs submitted by contributors via PRs:

```json
[
  {
    "title": "Software Engineer",
    "company": "Company Name",
    "location": "City, State",
    "url": "https://apply-link.com",
    "date": "2026-07-14",
    "category": "Software Engineering",
    "work_model": "Remote",
    "info": "H1B Sponsor",
    "contributor": "Your GitHub Handle"
  }
]
```

The `info` field is for sponsorship / visa / seniority tags (`H1B Sponsor`,
`No Sponsorship`, `US Citizen Only`, `New Grad`, etc.).

## contributors.json

Optional shout-outs rendered under “Contributors — {month}” in the README:

```json
[
  { "name": "alice", "month": "2026-07" },
  { "name": "bob" }
]
```

Entries without `month` always count; with `month` only for that YYYY-MM.
