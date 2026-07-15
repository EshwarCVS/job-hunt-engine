#!/usr/bin/env python3
"""Ingest a curator GitHub Issue form submission into
sources/curators/<id>/<year>/<month>/jobs.json.

Auth: compare submitted key to GitHub Actions secret CURATOR_KEY_<ID>
(and optional CURATOR_KEYS JSON map). Never log or write plaintext keys.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "sources" / "curators" / "_index.json"
CURATORS_DIR = ROOT / "sources" / "curators"

FIELD_ALIASES = {
    "curator_id": ["Curator ID", "Curator id", "Your curator ID"],
    "curator_key": ["Curator key", "Curator Key", "Submit key"],
    "name": ["Your name", "Display name", "Name"],
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
    # Allow pasting full LinkedIn URL as ID
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


def _secret_for_curator(curator_id: str, meta: dict) -> str:
    """Resolve plaintext key from Actions env — never from the git tree."""
    # Preferred: explicit JSON map secret
    pooled = os.environ.get("CURATOR_KEYS", "").strip()
    if pooled:
        try:
            mapping = json.loads(pooled)
            if isinstance(mapping, dict) and curator_id in mapping:
                return str(mapping[curator_id] or "")
        except json.JSONDecodeError:
            print("WARN: CURATOR_KEYS secret is not valid JSON", file=sys.stderr)

    # Named secret, e.g. CURATOR_KEY_MADHANVADLAMUDI
    candidates = [
        meta.get("secret_name") or "",
        "CURATOR_KEY_" + curator_id.upper().replace("-", "_"),
    ]
    for name in candidates:
        if not name:
            continue
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _keys_match(submitted: str, expected: str) -> bool:
    if not submitted or not expected:
        return False
    return hmac.compare_digest(submitted.strip().encode("utf-8"), expected.strip().encode("utf-8"))


def _extract_first_job_url(text: str) -> str:
    urls = re.findall(r"https?://[^\s<>\")\]]+", text or "")
    skip = ("linkedin.com/in/", "linkedin.com/feed", "linkedin.com/posts")
    for url in urls:
        clean = url.rstrip(".,);")
        lower = clean.lower()
        if any(s in lower for s in skip):
            continue
        return clean
    return ""


def append_submission(parsed: dict[str, str], curator: dict) -> Path:
    curator_id = curator["id"]
    today = date.today()
    try:
        posted = date.fromisoformat((parsed.get("date") or today.isoformat()).strip()[:10])
    except ValueError:
        posted = today

    year_dir = CURATORS_DIR / curator_id / f"{posted.year:04d}" / f"{posted.month:02d}"
    year_dir.mkdir(parents=True, exist_ok=True)
    month_file = year_dir / "jobs.json"

    linkedin_url = (parsed.get("linkedin_url") or curator.get("linkedin_url") or "").strip()
    submitted_as = (
        (parsed.get("name") or "").strip()
        or _name_from_linkedin_url(linkedin_url)
        or curator.get("display_name")
        or curator_id
    )

    registered = (curator.get("linkedin_url") or "").rstrip("/").lower()
    if linkedin_url and registered:
        provided = linkedin_url.rstrip("/").lower()
        if registered not in provided and provided not in registered:
            print(
                f"WARNING: LinkedIn URL does not match registered profile for @{curator_id}; "
                "continuing because curator key matched."
            )

    raw_post = parsed.get("raw_post") or ""
    url = (parsed.get("url") or "").strip() or _extract_first_job_url(raw_post)
    if not url:
        raise SystemExit("No application URL found — add Application URL or include a job link in the post.")

    entry = {
        "date": posted.isoformat(),
        "title": (parsed.get("title") or "Open Role (see post)").strip(),
        "company": (parsed.get("company") or "See post").strip(),
        "location": (parsed.get("location") or "").strip(),
        "work_model": (parsed.get("work_model") or "").strip(),
        "category": (parsed.get("category") or "Software Engineering").strip(),
        "type": (parsed.get("category") or "").strip(),
        "url": url,
        "info": (parsed.get("info") or "").strip(),
        "raw_post": raw_post.strip(),
        "submitted_as": submitted_as,
        "linkedin_url": linkedin_url,
        "source_issue": os.environ.get("ISSUE_NUMBER", ""),
    }

    entries: list = []
    if month_file.exists():
        with open(month_file) as f:
            entries = json.load(f)
            if not isinstance(entries, list):
                entries = []

    key = url.split("?")[0].rstrip("/").lower()
    entries = [e for e in entries if (e.get("url") or "").split("?")[0].rstrip("/").lower() != key]
    entries.append(entry)

    with open(month_file, "w") as f:
        json.dump(entries, f, indent=2)
        f.write("\n")

    return month_file


def main() -> int:
    body = os.environ.get("ISSUE_BODY") or ""
    if not body and len(sys.argv) > 1:
        body = Path(sys.argv[1]).read_text()
    if not body.strip():
        print("No ISSUE_BODY provided", file=sys.stderr)
        return 1

    parsed = _parse_issue_body(body)
    # Never print the key
    submitted_key = parsed.pop("curator_key", "") or ""

    curator_id = _normalize_id(parsed.get("curator_id") or "")
    if not curator_id:
        curator_id = _normalize_id(parsed.get("linkedin_url") or "")

    index = _load_index()
    curator = index.get(curator_id)
    if not curator or curator.get("active") is False:
        print("AUTH_FAILED: unknown or inactive curator id", file=sys.stderr)
        return 10

    expected = _secret_for_curator(curator_id, curator)
    if not expected:
        print(
            "AUTH_FAILED: no GitHub secret configured for this curator "
            f"(expected env {curator.get('secret_name') or 'CURATOR_KEY_' + curator_id.upper()})",
            file=sys.stderr,
        )
        return 10

    if not _keys_match(submitted_key, expected):
        print("AUTH_FAILED: curator key does not match", file=sys.stderr)
        return 10

    if not (parsed.get("raw_post") or parsed.get("url")):
        print("Need LinkedIn post content and/or an application URL", file=sys.stderr)
        return 1

    path = append_submission(parsed, curator)
    print(f"OK appended for @{curator['id']} → {path.relative_to(ROOT)}")
    print(f"CURATOR_ID={curator['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
