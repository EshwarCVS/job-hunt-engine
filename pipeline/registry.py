"""Persistent registry of discovered source repos with auto-archive.

Admins control inactivity threshold via sources/config.json
(`archive_inactive_days`, default 30).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
REPOS_FILE = ROOT / "sources" / "repos.json"
CONFIG_FILE = ROOT / "sources" / "config.json"


def load_config() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        return {"archive_inactive_days": 30, "linkedin_lookback_days": 7, "backfill_previous_month": True}
    with open(CONFIG_FILE) as f:
        return json.load(f)


def load_registry() -> dict[str, Any]:
    if not REPOS_FILE.exists():
        return {"version": 1, "updated_at": None, "orgs": {}, "accounts": {}}
    with open(REPOS_FILE) as f:
        return json.load(f)


def save_registry(registry: dict[str, Any]) -> None:
    registry["updated_at"] = date.today().isoformat()
    REPOS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REPOS_FILE, "w") as f:
        json.dump(registry, f, indent=2)
        f.write("\n")


def _ensure_org(registry: dict[str, Any], org: str) -> dict[str, Any]:
    orgs = registry.setdefault("orgs", {})
    org_entry = orgs.setdefault(org, {"active": [], "archived": []})
    org_entry.setdefault("active", [])
    org_entry.setdefault("archived", [])
    return org_entry


def touch_repo(
    org: str,
    name: str,
    *,
    url: str | None = None,
    branch: str = "main",
    last_activity: date | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    """Record that a repo was discovered / successfully scraped today."""
    registry = load_registry()
    org_entry = _ensure_org(registry, org)
    today = date.today().isoformat()
    activity = (last_activity or date.today()).isoformat()
    repo_url = url or f"https://github.com/{org}/{name}"

    # Revive from archived if rediscovered
    archived = org_entry["archived"]
    for i, item in enumerate(list(archived)):
        if item.get("name") == name:
            archived.pop(i)
            break

    for item in org_entry["active"]:
        if item.get("name") == name:
            item["last_seen"] = today
            item["last_activity"] = activity
            item["url"] = repo_url
            item["branch"] = branch
            if meta:
                item.setdefault("meta", {}).update(meta)
            save_registry(registry)
            return

    entry = {
        "name": name,
        "url": repo_url,
        "branch": branch,
        "first_seen": today,
        "last_seen": today,
        "last_activity": activity,
        "meta": meta or {},
    }
    org_entry["active"].append(entry)
    org_entry["active"].sort(key=lambda r: r["name"])
    save_registry(registry)
    print(f"  [registry] Added {org}/{name} to active repos")


def archive_stale_repos(org: str | None = None) -> list[str]:
    """Archive active repos with no activity past the configured threshold."""
    config = load_config()
    threshold_days = int(config.get("archive_inactive_days", 30))
    cutoff = date.today() - timedelta(days=threshold_days)

    registry = load_registry()
    archived_names: list[str] = []
    orgs = registry.get("orgs", {})
    targets = [org] if org else list(orgs.keys())

    for org_name in targets:
        org_entry = orgs.get(org_name)
        if not org_entry:
            continue
        remaining = []
        for item in org_entry.get("active", []):
            raw = item.get("last_seen") or item.get("last_activity")
            try:
                activity = datetime.strptime(raw, "%Y-%m-%d").date()
            except (TypeError, ValueError):
                remaining.append(item)
                continue

            if activity < cutoff:
                item["archived_at"] = date.today().isoformat()
                item["archive_reason"] = (
                    f"Not seen by scraper for {threshold_days}+ days"
                )
                org_entry.setdefault("archived", []).append(item)
                archived_names.append(f"{org_name}/{item['name']}")
                print(f"  [registry] Archived {org_name}/{item['name']} ({item['archive_reason']})")
            else:
                remaining.append(item)
        org_entry["active"] = remaining
        org_entry["archived"].sort(key=lambda r: r.get("archived_at") or "", reverse=True)

    if archived_names:
        save_registry(registry)
    else:
        # Still persist updated_at when called from scrape
        save_registry(registry)

    return archived_names


def list_active(org: str) -> list[dict[str, Any]]:
    registry = load_registry()
    return list(_ensure_org(registry, org).get("active", []))
