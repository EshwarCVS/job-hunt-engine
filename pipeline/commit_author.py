#!/usr/bin/env python3
"""Resolve git commit author for curator / community contributions.

Prefer the person contributing (issue submitter or registered GitHub),
fall back to the maintainer in sources/config.json.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "sources" / "config.json"
INDEX = ROOT / "sources" / "curators" / "_index.json"


def _normalize_login(value: str) -> str:
    value = (value or "").strip().lstrip("@")
    if "github.com/" in value.lower():
        value = value.rstrip("/").split("/")[-1]
    value = re.sub(r"[^A-Za-z0-9-]", "", value)
    return value


def maintainer_author() -> tuple[str, str]:
    try:
        data = json.loads(CONFIG.read_text())
        ca = data.get("commit_author") or {}
        name = (ca.get("name") or "EshwarCVS").strip()
        email = (ca.get("email") or "EshwarCVS@users.noreply.github.com").strip()
        return name, email
    except (OSError, json.JSONDecodeError):
        return "EshwarCVS", "EshwarCVS@users.noreply.github.com"


def registered_curator_github(curator_id: str) -> str:
    if not curator_id or not INDEX.exists():
        return ""
    try:
        data = json.loads(INDEX.read_text())
    except (OSError, json.JSONDecodeError):
        return ""
    for c in data.get("curators") or []:
        if c.get("id") == curator_id:
            return _normalize_login(c.get("github") or "")
    return ""


def noreply_email(login: str, user_id: str | int | None = None) -> str:
    login = _normalize_login(login)
    if user_id not in (None, "", 0, "0"):
        return f"{user_id}+{login}@users.noreply.github.com"
    return f"{login}@users.noreply.github.com"


def resolve_author(
    *,
    issue_login: str = "",
    issue_id: str = "",
    issue_type: str = "",
    form_github: str = "",
    curator_id: str = "",
) -> dict[str, str]:
    """Pick commit author so contributors get credit when they have a GitHub identity.

    Priority:
      1. GitHub username from the submission form (explicit)
      2. Registered curator github in _index.json
      3. Issue author (they used GitHub to contribute)
      4. Maintainer (sources/config.json commit_author)
    """
    maintainer_name, maintainer_email = maintainer_author()
    form_login = _normalize_login(form_github)
    issue_login_n = _normalize_login(issue_login)
    issue_ok = (issue_type or "User") == "User" and bool(issue_login_n)
    registered = registered_curator_github(curator_id)

    def _pack(login: str, source: str, prefer_issue_id: bool = False) -> dict[str, str]:
        uid = ""
        if prefer_issue_id and issue_ok and login.lower() == issue_login_n.lower():
            uid = issue_id
        elif source == "issue":
            uid = issue_id
        return {
            "name": login,
            "email": noreply_email(login, uid or None),
            "login": login,
            "source": source,
        }

    if form_login:
        return _pack(form_login, "form", prefer_issue_id=True)

    if registered:
        return _pack(registered, "curator_index", prefer_issue_id=True)

    if issue_ok:
        return _pack(issue_login_n, "issue")

    return {
        "name": maintainer_name,
        "email": maintainer_email,
        "login": maintainer_name,
        "source": "maintainer",
    }


def _write_github_output(mapping: dict[str, str]) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        for key, value in mapping.items():
            f.write(f"{key}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve contribution commit author")
    parser.add_argument("--curator-id", default=os.environ.get("CURATOR_ID", ""))
    parser.add_argument("--form-github", default=os.environ.get("FORM_GITHUB", ""))
    parser.add_argument("--issue-login", default=os.environ.get("ISSUE_USER_LOGIN", ""))
    parser.add_argument("--issue-id", default=os.environ.get("ISSUE_USER_ID", ""))
    parser.add_argument("--issue-type", default=os.environ.get("ISSUE_USER_TYPE", "User"))
    args = parser.parse_args()

    author = resolve_author(
        issue_login=args.issue_login,
        issue_id=args.issue_id,
        issue_type=args.issue_type,
        form_github=args.form_github,
        curator_id=args.curator_id,
    )
    print(
        f"author={author['name']} <{author['email']}> "
        f"(source={author['source']}, login={author['login']})",
        file=sys.stderr,
    )
    _write_github_output({
        "name": author["name"],
        "email": author["email"],
        "login": author["login"],
        "source": author["source"],
    })
    # Also stdout for local use
    print(f"{author['name']}\t{author['email']}\t{author['login']}\t{author['source']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
