"""Fetch job postings from LinkedIn profiles using Playwright.

Expands truncated posts ("…more"), scrapes the last N days (default 7),
and attributes listings as LinkedIn — @username.

Rate limits per profile (default every 3 days) to reduce LinkedIn blocks.
Supports rotating multiple li_at cookies via LINKEDIN_LI_AT_POOL.

Requires at least one of: LINKEDIN_LI_AT, LINKEDIN_LI_AT_POOL.
Profiles: sources/linkedin-profiles.json
State:    sources/linkedin-state.json (last successful scrape per profile)
"""

from __future__ import annotations

import json
import os
import random
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from pipeline.models import Job, normalize_info_tags
from pipeline.registry import load_config

ROOT = Path(__file__).parent.parent.parent
PROFILES_FILE = ROOT / "sources" / "linkedin-profiles.json"
STATE_FILE = ROOT / "sources" / "linkedin-state.json"

JOB_DOMAINS = [
    "greenhouse.io", "lever.co", "jobs.lever.co",
    "boards.greenhouse.io", "apply.workable.com",
    "careers.", "jobs.", "linkedin.com/jobs",
    "myworkdayjobs.com", "smartrecruiters.com",
    "icims.com", "ashbyhq.com", "wellfound.com",
    "jobvite.com", "breezy.hr", "recruitee.com",
    "applytojob.com", "hire.lever.co", "oraclecloud.com",
    "successfactors", "workday.com", "taleo.net",
]

RELATIVE_AGE = re.compile(
    r"\b(\d+)\s*(months?|mos?|weeks?|wks?|days?|hours?|hrs?|hr|h|m|w|d)\b",
    re.I,
)

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]


def _username_from_profile(profile: dict) -> str:
    if profile.get("username"):
        return profile["username"].lstrip("@").strip()
    url = profile.get("url", "")
    slug = urlparse(url).path.rstrip("/").split("/")[-1]
    return slug or "unknown"


def _load_state() -> dict:
    if not STATE_FILE.exists():
        return {"profiles": {}}
    try:
        with open(STATE_FILE) as f:
            data = json.load(f)
        data.setdefault("profiles", {})
        return data
    except (json.JSONDecodeError, OSError):
        return {"profiles": {}}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.utcnow().isoformat() + "Z"
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _scrape_interval_days(profile: dict, config: dict) -> int:
    if "scrape_every_days" in profile:
        return max(1, int(profile["scrape_every_days"]))
    return max(1, int(config.get("linkedin_default_scrape_every_days", 3)))


def _force_linkedin() -> bool:
    return os.environ.get("FORCE_LINKEDIN", "").strip().lower() in {"1", "true", "yes"}


def _should_scrape_profile(profile: dict, state: dict, config: dict) -> tuple[bool, str]:
    if profile.get("active") is False:
        return False, "inactive"

    username = _username_from_profile(profile)
    if _force_linkedin():
        return True, "forced"

    interval = _scrape_interval_days(profile, config)
    last = _parse_iso_date(state.get("profiles", {}).get(username, {}).get("last_success"))
    if last is None:
        return True, "never scraped"

    due = last + timedelta(days=interval)
    if date.today() >= due:
        return True, f"due (last {last.isoformat()}, every {interval}d)"
    return False, f"skip until {due.isoformat()} (last {last.isoformat()}, every {interval}d)"


def should_scrape_any() -> bool:
    """Used by CI to decide whether Playwright is needed this run."""
    if not _resolve_cookies():
        return False
    if not PROFILES_FILE.exists():
        return False
    with open(PROFILES_FILE) as f:
        profiles = json.load(f)
    if not profiles:
        return False
    config = load_config()
    state = _load_state()
    return any(_should_scrape_profile(p, state, config)[0] for p in profiles)


def _resolve_cookies() -> list[str]:
    """Collect and rotate session cookies to reduce single-account burn risk."""
    cookies: list[str] = []
    primary = os.environ.get("LINKEDIN_LI_AT", "").strip()
    if primary:
        cookies.append(primary)

    pool = os.environ.get("LINKEDIN_LI_AT_POOL", "").strip()
    if pool:
        for part in re.split(r"[\n,;]+", pool):
            part = part.strip()
            if part and part not in cookies:
                cookies.append(part)

    # Optional numbered secrets / env vars LINKEDIN_LI_AT_2, _3, …
    for i in range(2, 6):
        extra = os.environ.get(f"LINKEDIN_LI_AT_{i}", "").strip()
        if extra and extra not in cookies:
            cookies.append(extra)

    return cookies


def _pick_cookie(cookies: list[str]) -> str:
    if len(cookies) == 1:
        return cookies[0]
    # Stable rotation by calendar day so a single run stays on one cookie,
    # but successive days use different accounts when a pool is configured.
    idx = date.today().toordinal() % len(cookies)
    print(f"  [linkedin] Using cookie slot {idx + 1}/{len(cookies)} (rotated by day)")
    return cookies[idx]


def _is_job_url(url: str) -> bool:
    url_lower = url.lower()
    if "linkedin.com/in/" in url_lower or "linkedin.com/company/" in url_lower:
        return False
    if "linkedin.com/feed" in url_lower or "linkedin.com/posts" in url_lower:
        return False
    return any(domain in url_lower for domain in JOB_DOMAINS)


def _extract_job_urls(text: str) -> list[str]:
    urls = re.findall(r'https?://[^\s<>"\')\],]+', text)
    urls = [u.rstrip(".,;:") for u in urls if _is_job_url(u)]
    seen: set[str] = set()
    unique: list[str] = []
    for url in urls:
        clean = url.split("?")[0].rstrip("/").lower()
        if clean not in seen:
            seen.add(clean)
            unique.append(url)
    return unique


def _parse_relative_age_days(text: str) -> int | None:
    match = RELATIVE_AGE.search(text[:200])
    if not match:
        head = text[:80].lower()
        if "just now" in head or "now" == head.strip():
            return 0
        if "yesterday" in head:
            return 1
        return None

    value = int(match.group(1))
    unit = match.group(2).lower()
    if unit.startswith("h") or unit == "m":
        return 0
    if unit.startswith("d"):
        return value
    if unit.startswith("w"):
        return value * 7
    if unit.startswith("mo"):
        return value * 30
    return None


def _guess_company(text: str, url: str) -> str:
    patterns = [
        r"(?:at|@|joining|join)\s+([A-Z][A-Za-z0-9&.\- ]{1,40})",
        r"([A-Z][A-Za-z0-9&.\- ]{1,40})\s+is hiring",
        r"hiring at\s+([A-Z][A-Za-z0-9&.\- ]{1,40})",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            company = m.group(1).strip(" .-|,")
            if len(company) >= 2 and company.lower() not in {"the", "our", "this", "a"}:
                return company

    host = urlparse(url).netloc.lower().replace("www.", "")
    for noise in ("boards.greenhouse.io", "jobs.lever.co", "job-boards.greenhouse.io"):
        if noise in host:
            parts = urlparse(url).path.strip("/").split("/")
            if parts:
                return parts[0].replace("-", " ").title()
    return host.split(".")[0].replace("-", " ").title() if host else "See post"


def _guess_title(text: str) -> str:
    patterns = [
        r"(?:hiring|looking for|role|position|opening)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9/+\- ]{5,80})",
        r"\b((?:Senior |Staff |Principal |Junior )?Software Engineer[A-Za-z0-9/+\- ]{0,40})",
        r"\b((?:Data Scientist|Machine Learning Engineer|Product Manager|SWE Intern|Software Intern)[A-Za-z0-9/+\- ]{0,40})",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            title = re.sub(r"\s+", " ", m.group(1)).strip(" .-|,")
            if 4 <= len(title) <= 90:
                return title
    for line in text.splitlines():
        line = line.strip()
        if len(line) >= 8 and not line.lower().startswith("http"):
            return line[:90]
    return "Open Role (see post)"


def _guess_location(text: str) -> str:
    patterns = [
        r"(?:location|based in|office)\s*[:\-]?\s*([A-Za-z0-9,.\- ]{3,60})",
        r"\b(Remote(?: in [A-Z]{2,3})?)\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return m.group(1).strip()[:80]
    return ""


def _guess_work_model(text: str) -> str:
    lower = text.lower()
    if "hybrid" in lower:
        return "Hybrid"
    if "remote" in lower:
        return "Remote"
    if "on-site" in lower or "onsite" in lower or "in-office" in lower:
        return "On Site"
    return ""


def _guess_info(text: str) -> str:
    lower = text.lower()
    tags: list[str] = []
    if "h1b" in lower or "h-1b" in lower or "visa sponsor" in lower:
        tags.append("H1B Sponsor")
    if "no sponsorship" in lower or "cannot sponsor" in lower or "no visa" in lower:
        tags.append("No Sponsorship")
    if "us citizen" in lower or "u.s. citizen" in lower or "clearance" in lower:
        tags.append("US Citizen Only")
    if "internship" in lower or "intern " in lower:
        tags.append("Internship")
    if "new grad" in lower or "new graduate" in lower or "university grad" in lower:
        tags.append("New Grad")
    return normalize_info_tags(*tags)


def _expand_see_more(page) -> None:
    selectors = [
        "button.feed-shared-inline-show-more-text",
        "button.see-more",
        "button[aria-label*='more' i]",
        "button[aria-label*='see more' i]",
        ".feed-shared-inline-show-more-text",
        "span.line-clamp-show-more-button",
    ]
    for selector in selectors:
        buttons = page.query_selector_all(selector)
        for btn in buttons[:25]:
            try:
                if btn.is_visible():
                    btn.click(timeout=1000)
                    page.wait_for_timeout(random.randint(150, 400))
            except Exception:
                continue


def _human_pause(min_ms: int = 800, max_ms: int = 2200) -> None:
    time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


def _scrape_profile(profile: dict, li_at: str, lookback_days: int) -> tuple[list[Job], bool]:
    """Returns (jobs, success). success=False means authwall / hard failure — don't advance schedule."""
    from playwright.sync_api import sync_playwright

    username = _username_from_profile(profile)
    display = profile.get("display_name") or profile.get("name") or username
    source_label = f"LinkedIn — @{username}"
    activity_url = f"https://www.linkedin.com/in/{username}/recent-activity/all/"
    jobs: list[Job] = []
    cutoff = date.today() - timedelta(days=lookback_days)
    success = False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={
                "width": random.choice([1280, 1365, 1440]),
                "height": random.choice([800, 900, 960]),
            },
            locale="en-US",
            timezone_id=random.choice(["America/Chicago", "America/New_York", "America/Los_Angeles"]),
        )
        context.add_cookies([{
            "name": "li_at",
            "value": li_at,
            "domain": ".linkedin.com",
            "path": "/",
            "httpOnly": True,
            "secure": True,
        }])
        page = context.new_page()

        try:
            print(f"  [linkedin] @{username} — loading recent activity (last {lookback_days}d)...")
            _human_pause(400, 1200)
            page.goto(activity_url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(random.randint(2000, 4000))

            if "login" in page.url.lower() or "authwall" in page.url.lower() or "checkpoint" in page.url.lower():
                print(f"  [linkedin] @{username} — blocked/login wall (rotate cookie or wait)")
                browser.close()
                return [], False

            # Gentle scroll — fewer passes than a daily full crawl
            scroll_passes = random.randint(4, 6)
            for _ in range(scroll_passes):
                _expand_see_more(page)
                page.evaluate("window.scrollBy(0, Math.floor(window.innerHeight * 0.85))")
                page.wait_for_timeout(random.randint(900, 1800))
            _expand_see_more(page)
            page.wait_for_timeout(random.randint(500, 1000))

            post_elements = page.query_selector_all(
                "div.feed-shared-update-v2, "
                "div[data-urn*='activity'], "
                "div.occludable-update"
            )
            if not post_elements:
                post_elements = page.query_selector_all("div[class*='feed-shared']")

            print(f"  [linkedin] @{username} — {len(post_elements)} posts found")
            success = True

            for el in post_elements:
                try:
                    text = el.inner_text() or ""
                    age_days = _parse_relative_age_days(text)
                    if age_days is not None and age_days > lookback_days:
                        continue

                    hrefs = el.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
                    all_text = text + "\n" + "\n".join(hrefs)
                    job_urls = _extract_job_urls(all_text)
                    if not job_urls:
                        continue

                    posted = date.today() if age_days is None else max(cutoff, date.today() - timedelta(days=age_days))
                    title = _guess_title(text)
                    location = _guess_location(text)
                    work_model = _guess_work_model(text)
                    info = normalize_info_tags(_guess_info(text), f"Via @{username}")

                    for url in job_urls:
                        company = _guess_company(text, url)
                        category = "Internship" if "intern" in title.lower() else "Software Engineering"
                        jobs.append(Job(
                            title=title,
                            company=company,
                            location=location or "See post",
                            url=url,
                            date_posted=posted,
                            source=source_label,
                            category=category,
                            work_model=work_model,
                            info=info,
                            contributor=display,
                        ))
                except Exception:
                    continue

        except Exception as e:
            print(f"  [linkedin] @{username} — error: {e}")
            success = False
        finally:
            browser.close()

    print(f"  [linkedin] @{username} — {len(jobs)} job links")
    return jobs, success


def scrape(lookback_days: int | None = None) -> list[Job]:
    config = load_config()
    if lookback_days is None:
        lookback_days = int(config.get("linkedin_lookback_days", 7))

    all_jobs: list[Job] = []
    cookies = _resolve_cookies()
    if not cookies:
        print("  [linkedin] No LINKEDIN_LI_AT / pool set, skipping LinkedIn scraper")
        return all_jobs

    if not PROFILES_FILE.exists():
        print("  [linkedin] No linkedin-profiles.json found")
        return all_jobs

    with open(PROFILES_FILE) as f:
        profiles = json.load(f)

    if not profiles:
        print("  [linkedin] No profiles configured")
        return all_jobs

    state = _load_state()
    li_at = _pick_cookie(cookies)
    due_profiles = []

    for profile in profiles:
        ok, reason = _should_scrape_profile(profile, state, config)
        username = _username_from_profile(profile)
        if not ok:
            print(f"  [linkedin] @{username} — {reason}")
            continue
        print(f"  [linkedin] @{username} — will scrape ({reason})")
        due_profiles.append(profile)

    if not due_profiles:
        print("  [linkedin] No profiles due this run (interval throttling)")
        return all_jobs

    for i, profile in enumerate(due_profiles):
        username = _username_from_profile(profile)
        if i > 0:
            # Space out profile visits — never blast many profiles back-to-back
            _human_pause(2500, 6000)
        try:
            jobs, success = _scrape_profile(profile, li_at, lookback_days)
            all_jobs.extend(jobs)
            if success:
                state.setdefault("profiles", {})[username] = {
                    "last_success": date.today().isoformat(),
                    "last_job_count": len(jobs),
                    "scrape_every_days": _scrape_interval_days(profile, config),
                }
                _save_state(state)
            else:
                print(f"  [linkedin] @{username} — not updating schedule (unsuccessful run)")
        except Exception as e:
            print(f"  [linkedin] Error scraping @{username}: {e}")

    print(f"  [linkedin] Total: {len(all_jobs)} jobs from LinkedIn this run")
    return all_jobs
