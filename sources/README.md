# Data Sources Configuration

## linkedin-profiles.json

LinkedIn profiles to monitor for job postings. Uses your LinkedIn session cookie — completely free, no third-party services.

### Setup (one-time, ~2 minutes)

1. Open [linkedin.com](https://www.linkedin.com) in your browser (make sure you're logged in)
2. Open DevTools: **F12** (or **Cmd+Option+I** on Mac)
3. Go to the **Application** tab → **Cookies** → **linkedin.com**
4. Find the cookie named **`li_at`** and copy its value
5. In your GitHub repo, go to **Settings → Secrets and variables → Actions**
6. Click **New repository secret**:
   - **Name**: `LINKEDIN_LI_AT`
   - **Value**: paste the `li_at` cookie value
7. Done! The daily scraper will use this automatically

### Cookie expiry

The `li_at` cookie lasts ~1 year. If the LinkedIn scraper stops finding posts, refresh the cookie by repeating steps 1-6.

### Adding more profiles

```json
[
  {"name": "Madhan Vadlamudi", "url": "https://www.linkedin.com/in/madhanvadlamudi/"},
  {"name": "Another Person", "url": "https://www.linkedin.com/in/their-slug/"}
]
```

### Cost

**$0**. Uses GitHub Actions (free for public repos) + your own LinkedIn cookie.

## community-jobs.json

Jobs submitted by community contributors via PRs. Format:

```json
[
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
]
```
