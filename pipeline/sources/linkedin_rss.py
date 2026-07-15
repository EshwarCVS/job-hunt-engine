"""Fetch job postings from LinkedIn profiles using Playwright.

Opens a headless browser with the li_at session cookie, navigates to
each profile's recent activity page, scrolls to load posts from the
past week, and extracts job application URLs.

Requires LINKEDIN_LI_AT environment variable.
Profiles to monitor are configured in sources/linkedin-profiles.json.
"""

import json
import os
import re
from datetime import date, timedelta
from pathlib import Path

from pipeline.models import Job

PROFILES_FILE = Path(__file__).parent.parent.parent / "sources" / "linkedin-profiles.json"

JOB_DOMAINS = [
    "greenhouse.io", "lever.co", "jobs.lever.co",
    "boards.greenhouse.io", "apply.workable.com",
    "careers.", "jobs.", "linkedin.com/jobs",
    "myworkdayjobs.com", "smartrecruiters.com",
    "icims.com", "ashbyhq.com", "wellfound.com",
    "jobvite.com", "breezy.hr", "recruitee.com",
    "applytojob.com", "hire.lever.co",
]


def _is_job_url(url: str) -> bool:
    """Check if a URL looks like a job application link."""
    url_lower = url.lower()
    if "linkedin.com/in/" in url_lower or "linkedin.com/company/" in url_lower:
        return False
    return any(domain in url_lower for domain in JOB_DOMAINS)


def _extract_job_urls(text: str) -> list[str]:
    """Extract unique job application URLs from text."""
    urls = re.findall(r'https?://[^\s<>"\')\],]+', text)
    urls = [u.rstrip(".,;:") for u in urls if _is_job_url(u)]

    seen = set()
    unique = []
    for url in urls:
        clean = url.split("?")[0].rstrip("/").lower()
        if clean not in seen:
            seen.add(clean)
            unique.append(url)
    return unique


def _scrape_profile(profile: dict, li_at: str, lookback_days: int) -> list[Job]:
    """Scrape a single LinkedIn profile's recent posts using Playwright."""
    from playwright.sync_api import sync_playwright

    profile_url = profile.get("url", "")
    name = profile.get("name", "Unknown")
    slug = profile_url.rstrip("/").split("/")[-1]

    if not slug:
        return []

    activity_url = f"https://www.linkedin.com/in/{slug}/recent-activity/all/"
    jobs: list[Job] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )

        context.add_cookies([{
            "name": "li_at",
            "value": li_at,
            "domain": ".linkedin.com",
            "path": "/",
        }])

        page = context.new_page()

        try:
            print(f"  [linkedin] Navigating to {name}'s activity page...")
            page.goto(activity_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            if "login" in page.url.lower() or "authwall" in page.url.lower():
                print(f"  [linkedin] Redirected to login — li_at cookie may be expired")
                browser.close()
                return []

            scroll_count = 5
            for i in range(scroll_count):
                page.evaluate("window.scrollBy(0, window.innerHeight)")
                page.wait_for_timeout(1500)

            post_elements = page.query_selector_all(
                "div.feed-shared-update-v2, "
                "div[data-urn*='activity'], "
                "div.occludable-update"
            )

            if not post_elements:
                post_elements = page.query_selector_all(
                    "div[class*='update-components'], "
                    "div[class*='feed-shared']"
                )

            if post_elements:
                print(f"  [linkedin] Found {len(post_elements)} post elements")
                for el in post_elements:
                    try:
                        text = el.inner_text()
                        hrefs = el.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
                        all_text = text + " " + " ".join(hrefs)
                        job_urls = _extract_job_urls(all_text)
                        for url in job_urls:
                            jobs.append(Job(
                                title="See Link",
                                company="See Link",
                                location="See Link",
                                url=url,
                                date_posted=date.today(),
                                source="LinkedIn",
                                category="Software Engineering",
                                work_model="",
                                info=f"Via {name}",
                            ))
                    except Exception:
                        continue
            else:
                print(f"  [linkedin] No post elements found, trying full page text...")
                page_text = page.inner_text("body")
                all_links = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
                full_text = page_text + " " + " ".join(all_links)
                job_urls = _extract_job_urls(full_text)
                for url in job_urls:
                    jobs.append(Job(
                        title="See Link",
                        company="See Link",
                        location="See Link",
                        url=url,
                        date_posted=date.today(),
                        source="LinkedIn",
                        category="Software Engineering",
                        work_model="",
                        info=f"Via {name}",
                    ))

        except Exception as e:
            print(f"  [linkedin] Error scraping {name}: {e}")
        finally:
            browser.close()

    print(f"  [linkedin] Found {len(jobs)} job links from {name}'s posts")
    return jobs


def scrape(lookback_days: int = 7) -> list[Job]:
    """Scrape LinkedIn profiles for job postings."""
    all_jobs: list[Job] = []

    li_at = os.environ.get("LINKEDIN_LI_AT", "")

    if not li_at:
        print("  [linkedin] LINKEDIN_LI_AT not set, skipping LinkedIn scraper")
        return all_jobs

    if not PROFILES_FILE.exists():
        print("  [linkedin] No linkedin-profiles.json found")
        return all_jobs

    with open(PROFILES_FILE) as f:
        profiles = json.load(f)

    if not profiles:
        print("  [linkedin] No profiles configured")
        return all_jobs

    for profile in profiles:
        try:
            all_jobs.extend(_scrape_profile(profile, li_at, lookback_days))
        except Exception as e:
            name = profile.get("name", "unknown")
            print(f"  [linkedin] Error scraping {name}: {e}")

    print(f"  [linkedin] Total: {len(all_jobs)} jobs from LinkedIn")
    return all_jobs
