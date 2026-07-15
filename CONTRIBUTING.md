# Contributing to Job Hunt Engine

Thanks for helping make job hunting easier for everyone! Here's how you can contribute.

## Adding Job Listings

### Option 1: Submit via Pull Request

1. Fork this repository
2. Add your job entry to `sources/community-jobs.json`:

```json
{
  "title": "Software Engineer",
  "company": "Company Name",
  "location": "City, State",
  "url": "https://apply-link.com",
  "date": "2026-07-14",
  "category": "Software Engineering",
  "work_model": "Remote",
  "info": "H1B Sponsor"
}
```

3. Open a Pull Request with the title: `Add: Company Name — Role Title`

### Option 2: Submit via Issue

Use the [Add Job Listing](../../issues/new?template=add-job.yml) issue template to submit a job without needing to edit files.

## Job Entry Format

Every job entry needs these fields:

| Field | Required | Example | Notes |
|-------|----------|---------|-------|
| `title` | Yes | Software Engineer | Job title as listed |
| `company` | Yes | Google | Company name |
| `location` | Yes | Mountain View, CA | City, State or "Remote" |
| `url` | Yes | https://careers.google.com/... | Direct application link |
| `date` | Yes | 2026-07-14 | YYYY-MM-DD format |
| `category` | No | Software Engineering | See categories below |
| `work_model` | No | Hybrid | Remote, Hybrid, or On Site |
| `info` | No | H1B Sponsor | Visa, level, degree info |

### Categories

Use one of these categories:

- `Software Engineering` (default)
- `Frontend`
- `Backend`
- `Full Stack`
- `Data/ML`
- `DevOps/Infra`
- `Mobile`
- `Security`
- `Embedded/HW`
- `Internship`

### Info Tags

Common tags for the `info` field:

- `H1B Sponsor` — company sponsors H1B visas
- `H1B (Historical)` — company has sponsored in the past
- `No Sponsorship` — no visa sponsorship available
- `US Citizen Only` — requires US citizenship
- `Advanced Degree` — requires Master's or PhD
- `New Grad` — entry-level / new graduate role
- `Senior`, `Staff`, `Principal` — seniority level

## Adding Data Sources

To add a new automated data source:

1. Create a new scraper in `pipeline/sources/`
2. Follow the pattern of existing scrapers (return `list[Job]`)
3. Add the import and call in `pipeline/scraper.py`
4. Open a PR with a description of the source and update frequency

## Reporting Issues

- **Broken link?** Open an issue with the job title and company
- **Duplicate listing?** Open an issue with both entries
- **Scraper bug?** Include the error output and which source failed

## Adding LinkedIn Feed Sources

To add a LinkedIn user whose posts contain job listings:

1. Set up an RSS feed for their posts using a service like [rss.app](https://rss.app)
2. Add the feed URL to `sources/linkedin-feeds.json`
3. Submit a PR

## Code Style

- Python 3.12+
- No external dependencies beyond what's in `requirements.txt` unless necessary
- Type hints encouraged
- Keep scrapers resilient to format changes (don't crash on unexpected input)

## Questions?

Open an issue or start a discussion. We're happy to help!
