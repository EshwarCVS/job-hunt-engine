"""Deduplicate jobs across sources using URL normalization and fuzzy matching."""

from pipeline.models import Job


def deduplicate(jobs: list[Job]) -> list[Job]:
    """Remove duplicate jobs, keeping the entry with the most info."""
    seen: dict[str, Job] = {}

    for job in jobs:
        key = job.dedup_key
        if key in seen:
            existing = seen[key]
            if _score(job) > _score(existing):
                seen[key] = job
        else:
            seen[key] = job

    return list(seen.values())


def _score(job: Job) -> int:
    """Score a job entry by completeness — higher is better."""
    score = 0
    if job.info and job.info != "-":
        score += 3
    if job.work_model:
        score += 2
    if job.location and job.location not in ("Not Listed", "See Link"):
        score += 2
    if job.category and job.category != "Software Engineering":
        score += 1
    if job.company and job.company not in ("Unknown", "See Link"):
        score += 1
    return score
