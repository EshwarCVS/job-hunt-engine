"""Load voluntary curator submissions from
sources/curators/<id>/<year>/<month>/jobs.json.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

from pipeline.models import Job, normalize_info_tags

CURATORS_DIR = Path(__file__).parent.parent.parent / "sources" / "curators"
INDEX_FILE = CURATORS_DIR / "_index.json"

JOBS_FILE = re.compile(r"jobs\.json$")


def _index_by_id() -> dict[str, dict]:
    if not INDEX_FILE.exists():
        return {}
    with open(INDEX_FILE) as f:
        data = json.load(f)
    return {c["id"]: c for c in data.get("curators", []) if c.get("id")}


def scrape() -> list[Job]:
    if not CURATORS_DIR.exists():
        return []

    index = _index_by_id()
    jobs: list[Job] = []

    for path in sorted(CURATORS_DIR.glob("*/*/*/jobs.json")):
        if not JOBS_FILE.search(path.name):
            continue

        # .../<id>/<year>/<month>/jobs.json
        month_dir = path.parent
        year_dir = month_dir.parent
        curator_id = year_dir.parent.name

        meta = index.get(curator_id, {})
        if meta.get("active") is False:
            continue

        display = meta.get("display_name") or curator_id
        source = f"Curator — @{curator_id}"

        try:
            with open(path) as f:
                entries = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"  [curators] Skip {path}: {e}")
            continue

        if not isinstance(entries, list):
            continue

        for entry in entries:
            url = (entry.get("url") or "").strip()
            if not url:
                raw = entry.get("raw_post") or entry.get("content") or ""
                urls = re.findall(r"https?://[^\s<>\")\]]+", raw)
                url = next((u.rstrip(".,);") for u in urls if "linkedin.com/in/" not in u.lower()), "")
            if not url:
                continue

            try:
                posted = datetime.strptime(entry["date"], "%Y-%m-%d").date()
            except (ValueError, KeyError):
                posted = date.today()

            info = normalize_info_tags(
                entry.get("info", ""),
                entry.get("type", ""),
                f"Via @{curator_id}",
            )

            jobs.append(Job(
                title=entry.get("title") or "Open Role (see post)",
                company=entry.get("company") or "See post",
                location=entry.get("location") or "See post",
                url=url,
                date_posted=posted,
                source=source,
                category=entry.get("category") or _type_to_category(entry.get("type", "")),
                work_model=entry.get("work_model") or "",
                info=info,
                contributor=entry.get("submitted_as") or display,
            ))

    print(f"  [curators] Loaded {len(jobs)} curator-submitted jobs")
    return jobs


def _type_to_category(job_type: str) -> str:
    t = (job_type or "").lower()
    if "intern" in t:
        return "Internship"
    if "data" in t or "ml" in t or "ai" in t:
        return "Data/ML"
    return "Software Engineering"
