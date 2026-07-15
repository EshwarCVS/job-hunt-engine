#!/usr/bin/env python3
"""Ingest a curator GitHub Issue form submission.

- Auth via CURATOR_KEYS (never printed)
- Parse pasted LinkedIn post into structured jobs
- Upsert into sources/curators/<id>/<year>/<month>/jobs.json by apply URL
  (repeat pushes from the same curator update existing rows)
- Save unique raw posts under .../posts/post-<fingerprint>.md
"""

from __future__ import annotations

import hmac
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

from pipeline.post_extract import content_fingerprint, extract_jobs_from_post

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "sources" / "curators" / "_index.json"
CURATORS_DIR = ROOT / "sources" / "curators"

FIELD_ALIASES = {
    "curator_id": ["Curator ID", "Curator id", "Your curator ID"],
    "curator_key": ["Curator key", "Curator Key", "Submit key"],
    "name": ["Your name", "Display name", "Name"],
    "github": ["GitHub username", "GitHub", "GitHub profile"],
    "linkedin_url": ["LinkedIn profile URL", "LinkedIn URL", "Profile URL"],
    "raw_post": ["LinkedIn post content", "Post content (as-is)", "Post content"],
    "url": ["Application URL", "Apply URL", "Job URL"],
    "title": ["Job title", "Role / title", "Title"],
    "company": ["Company", "Company name"],
    "location": ["Location", "Location / type"],
    "work_model": ["Work model"],
    "category": ["Category / type", "Category", "Type"],
    "info": ["Visa / sponsorship / info", "Additional info", "Info"],
    "date": ["Date posted", "Post date"],
}


def _gh_output(key: str, value: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{key}={value}\n")


def _normalize_github_login(value: str) -> str:
    value = (value or "").strip().lstrip("@")
    if "github.com/" in value.lower():
        value = value.rstrip("/").split("/")[-1]
    return re.sub(r"[^A-Za-z0-9-]", "", value)


def curator_secret_env_name(curator_id: str) -> str:
    return "CURATOR_" + curator_id.strip().upper().replace("-", "_")


def _parse_issue_body(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    parts = re.split(r"\n###\s+", body.strip())
    for part in parts:
        part = part.strip()
        if not part:
            continue
        lines = part.splitlines()
        heading = lines[0].lstrip("#").strip()
        value = "\n".join(lines[1:]).strip()
        if value.lower() in {"_no response_", "no response", ""}:
            value = ""
        fields[heading] = value

    out: dict[str, str] = {}
    lower_map = {k.lower(): v for k, v in fields.items()}
    for canonical, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if alias.lower() in lower_map:
                out[canonical] = lower_map[alias.lower()]
                break
    return out


def _normalize_id(value: str) -> str:
    value = (value or "").strip().lstrip("@").lower()
    if "linkedin.com/in/" in value:
        path = urlparse(value).path.rstrip("/")
        value = path.split("/")[-1]
    return re.sub(r"[^a-z0-9_-]", "", value)


def _name_from_linkedin_url(url: str) -> str:
    if not url:
        return ""
    path = urlparse(url.strip()).path.rstrip("/")
    slug = path.split("/")[-1] if path else ""
    if not slug:
        return ""
    if "-" in slug:
        return " ".join(p.capitalize() for p in slug.split("-") if p)
    return slug


def _load_index() -> dict[str, dict]:
    with open(INDEX) as f:
        data = json.load(f)
    return {c["id"]: c for c in data.get("curators", []) if c.get("id")}


def _load_keys_map() -> dict[str, str]:
    pooled = os.environ.get("CURATOR_KEYS", "").strip()
    if not pooled:
        return {}
    try:
        mapping = json.loads(pooled)
    except json.JSONDecodeError:
        print("WARN: CURATOR_KEYS is not valid JSON", file=sys.stderr)
        return {}
    if not isinstance(mapping, dict):
        return {}
    return {str(k): str(v or "") for k, v in mapping.items()}


def _secret_for_curator(curator_id: str) -> str:
    keys = _load_keys_map()
    env_name = curator_secret_env_name(curator_id)
    for candidate in (curator_id, env_name):
        if candidate and keys.get(candidate):
            return keys[candidate].strip()
    return os.environ.get(env_name, "").strip()


def _keys_match(submitted: str, expected: str) -> bool:
    if not submitted or not expected:
        return False
    return hmac.compare_digest(submitted.strip().encode("utf-8"), expected.strip().encode("utf-8"))


def _month_paths(curator_id: str, posted: date) -> tuple[Path, Path]:
    base = CURATORS_DIR / curator_id / f"{posted.year:04d}" / f"{posted.month:02d}"
    base.mkdir(parents=True, exist_ok=True)
    (base / "posts").mkdir(exist_ok=True)
    return base / "jobs.json", base / "posts"


def append_submission(parsed: dict[str, str], curator: dict) -> tuple[Path, int]:
    curator_id = curator["id"]
    today = date.today()
    try:
        posted = date.fromisoformat((parsed.get("date") or today.isoformat()).strip()[:10])
    except ValueError:
        posted = today

    jobs_file, posts_dir = _month_paths(curator_id, posted)

    linkedin_url = (parsed.get("linkedin_url") or curator.get("linkedin_url") or "").strip()
    github_login = (
        _normalize_github_login(parsed.get("github") or "")
        or _normalize_github_login(os.environ.get("ISSUE_USER_LOGIN") or "")
        or _normalize_github_login(curator.get("github") or "")
    )
    submitted_as = (
        (parsed.get("name") or "").strip()
        or _name_from_linkedin_url(linkedin_url)
        or curator.get("display_name")
        or curator_id
    )

    raw_post = (parsed.get("raw_post") or "").strip()
    if not raw_post and not (parsed.get("url") or "").strip():
        raise SystemExit("Paste the LinkedIn post content (as-is), including apply links.")

    extracted = extract_jobs_from_post(
        raw_post,
        defaults={
            "url": (parsed.get("url") or "").strip(),
            "title": (parsed.get("title") or "").strip(),
            "company": (parsed.get("company") or "").strip(),
            "location": (parsed.get("location") or "").strip(),
            "work_model": (parsed.get("work_model") or "").strip(),
            "category": (parsed.get("category") or "").strip(),
            "info": (parsed.get("info") or "").strip(),
        },
    )
    if not extracted:
        raise SystemExit(
            "Could not find any application URLs in the post. "
            "Include greenhouse/lever/ashby/careers links in the pasted text "
            "or fill Application URL."
        )

    # Save raw post once per unique content fingerprint (supports multiple curator pushes)
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    issue_no = os.environ.get("ISSUE_NUMBER", "manual")
    fp = content_fingerprint(raw_post)
    post_path = posts_dir / f"post-{fp}.md"
    if not post_path.exists():
        post_path.write_text(
            f"# Curator post (@{curator_id})\n\n"
            f"- issue: #{issue_no}\n"
            f"- submitted_as: {submitted_as}\n"
            f"- linkedin: {linkedin_url}\n"
            f"- fingerprint: {fp}\n"
            f"- first_captured: {stamp}\n\n"
            f"---\n\n{raw_post}\n",
            encoding="utf-8",
        )
    else:
        # Append note that same content was re-submitted
        with open(post_path, "a", encoding="utf-8") as f:
            f.write(f"\n\n<!-- re-submitted issue #{issue_no} at {stamp} -->\n")

    entries: list = []
    if jobs_file.exists():
        with open(jobs_file) as f:
            entries = json.load(f)
            if not isinstance(entries, list):
                entries = []

    by_url = {
        (e.get("url") or "").split("?")[0].rstrip("/").lower(): e
        for e in entries
        if e.get("url")
    }
    added = 0
    updated = 0
    for job in extracted:
        url_key = job["url"].split("?")[0].rstrip("/").lower()
        prev = by_url.get(url_key)
        entry = {
            "date": posted.isoformat(),
            "title": job["title"],
            "company": job["company"],
            "location": job["location"],
            "work_model": job["work_model"],
            "category": job["category"],
            "type": job.get("type") or job["category"],
            "url": job["url"],
            "info": job["info"],
            "raw_post": job["raw_post"],
            "submitted_as": submitted_as,
            "github": github_login,
            "linkedin_url": linkedin_url,
            "source_issue": str(issue_no),
            "raw_post_file": str(post_path.relative_to(ROOT)),
            "content_fingerprint": fp,
            "updated_at": stamp,
            "submission_count": 1,
        }
        if prev:
            entry["submission_count"] = int(prev.get("submission_count") or 1) + 1
            entry["first_seen"] = prev.get("first_seen") or prev.get("date") or posted.isoformat()
            # Keep earliest date_posted; refresh metadata/title if newer parse is richer
            if prev.get("date"):
                entry["date"] = min(str(prev["date"]), posted.isoformat())
            updated += 1
        else:
            entry["first_seen"] = posted.isoformat()
            added += 1
        by_url[url_key] = entry

    merged = list(by_url.values())
    merged.sort(key=lambda e: e.get("updated_at") or e.get("date") or "", reverse=True)

    with open(jobs_file, "w") as f:
        json.dump(merged, f, indent=2)
        f.write("\n")

    print(
        f"OK @{curator_id}: parsed={len(extracted)} added={added} updated={updated} "
        f"→ {jobs_file.relative_to(ROOT)}"
    )
    print(f"RAW_POST={post_path.relative_to(ROOT)}")
    print(f"JOBS_ADDED={added}")
    print(f"JOBS_UPDATED={updated}")
    return jobs_file, added + updated


def main() -> int:
    body = os.environ.get("ISSUE_BODY") or ""
    if not body and len(sys.argv) > 1:
        body = Path(sys.argv[1]).read_text()
    if not body.strip():
        print("No ISSUE_BODY provided", file=sys.stderr)
        return 1

    parsed = _parse_issue_body(body)
    submitted_key = parsed.pop("curator_key", "") or ""
    # Never print submitted_key

    curator_id = _normalize_id(parsed.get("curator_id") or "")
    if not curator_id:
        curator_id = _normalize_id(parsed.get("linkedin_url") or "")

    index = _load_index()
    curator = index.get(curator_id)
    if not curator or curator.get("active") is False:
        print("AUTH_FAILED: unknown or inactive curator id", file=sys.stderr)
        return 10

    expected = _secret_for_curator(curator_id)
    if not expected:
        print("AUTH_FAILED: passphrase not configured for this curator", file=sys.stderr)
        return 10

    if not _keys_match(submitted_key, expected):
        print("AUTH_FAILED: curator key does not match", file=sys.stderr)
        return 10

    try:
        append_submission(parsed, curator)
    except SystemExit as exc:
        print(str(exc) or "ingest failed", file=sys.stderr)
        return 1

    form_github = _normalize_github_login(parsed.get("github") or "")
    print(f"CURATOR_ID={curator['id']}")
    print(f"FORM_GITHUB={form_github}")
    _gh_output("curator_id", curator["id"])
    _gh_output("form_github", form_github)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
