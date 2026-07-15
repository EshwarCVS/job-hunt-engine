"""Load community-submitted job listings from community-jobs.json."""

import json
from datetime import date, datetime
from pathlib import Path

from pipeline.models import Job

COMMUNITY_FILE = Path(__file__).parent.parent.parent / "sources" / "community-jobs.json"


def scrape() -> list[Job]:
    """Load community-submitted jobs."""
    if not COMMUNITY_FILE.exists():
        return []

    with open(COMMUNITY_FILE) as f:
        data = json.load(f)

    if not data:
        return []

    jobs = []
    for entry in data:
        if not entry.get("url"):
            continue
        try:
            posted = datetime.strptime(entry["date"], "%Y-%m-%d").date()
        except (ValueError, KeyError):
            posted = date.today()

        jobs.append(Job(
            title=entry.get("title", "See Link"),
            company=entry.get("company", "Unknown"),
            location=entry.get("location", "Not Listed"),
            url=entry["url"],
            date_posted=posted,
            source="Community",
            category=entry.get("category", "Software Engineering"),
            work_model=entry.get("work_model", ""),
            info=entry.get("info", ""),
        ))

    print(f"  [community] Loaded {len(jobs)} community-submitted jobs")
    return jobs
