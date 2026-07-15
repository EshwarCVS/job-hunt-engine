# Curator onboarding (maintainer guide)

Trusted curators paste LinkedIn hiring posts via a keyed GitHub Issue form.
The bot parses apply links, stores jobs under their folder on **`develop`**,
attributes the commit to their GitHub when known, and publishes to **`master`**.

Passphrases live **only** in the Actions secret `CURATOR_KEYS`. Never commit them.

**Reference example id / profile (maintainer):**
`eshwarchandravidhyasagar` ·
https://www.linkedin.com/in/eshwarchandravidhyasagar/

---

## GitHub Actions wiring checklist

| Piece | Must be true |
|-------|----------------|
| Workflows on **both** `develop` and `master` | `curator-submit.yml`, `scrape-jobs.yml`, `secret-scan.yml` |
| Issue forms on `master` (default branch) | `curator-submit.yml`, `curator-request.yml`, `add-job.yml` |
| Labels exist | `curator-submission`, `curator-onboarding`, `ingested`, `needs-curator-fix`, `job-submission` |
| Secret **`CURATOR_KEYS`** (preferred) | JSON map of id → passphrase (see below) |
| Optional LinkedIn | `LINKEDIN_LI_AT` (scrape skips LinkedIn if unset) |
| Actions enabled | Settings → Actions → Allow actions |

After editing workflows locally, **push/merge to `develop` and `master`** or GitHub still runs the old files.

### Secrets (preferred vs fallback)

**Preferred — one secret `CURATOR_KEYS`:**

```json
{
  "madhanvadlamudi": "<passphrase>",
  "CURATOR_MADHANVADLAMUDI": "<passphrase>",
  "eshwarchandravidhyasagar": "<passphrase>",
  "CURATOR_ESHWARCHANDRAVIDHYASAGAR": "<passphrase>"
}
```

Per-curator secrets like `CURATOR_MADHANVADLAMUDI` still work **only if** that name is listed in `.github/workflows/curator-submit.yml` `env:`. New curators should go into `CURATOR_KEYS` only (no workflow edit).

---

## How a request is received (no Gmail required)

| Step | Where | What happens |
|------|--------|----------------|
| 1. Someone asks | GitHub Issue → **[Request curator access](https://github.com/EshwarCVS/job-hunt-engine/issues/new?template=curator-request.yml)** (label `curator-onboarding`) | Public request with LinkedIn / preferred id / consent. **No passphrase yet.** |
| 2. You review | Same issue in the repo’s Issues tab (also email/notification if you watch the repo) | Approve, ask a question, or close. |
| 3. You create the key | GitHub → **Settings → Secrets → Actions → `CURATOR_KEYS`** | You generate a passphrase locally; put it only in that secret JSON. Not in git. |
| 4. You send the key | **Private channel** (LinkedIn DM preferred) | Tell them their `curator id` + passphrase. Never comment the passphrase on the public issue. |
| 5. They submit jobs | **[Curator submission](https://github.com/EshwarCVS/job-hunt-engine/issues/new?template=curator-submit.yml)** | Bot redacts key, writes `sources/curators/<id>/…`, publishes via scrape. |

**You do not need Gmail or a mail server.** GitHub Issues is the inbox for “please onboard me.”  
Delivering the passphrase is a **private human message** (LinkedIn DM is enough; optional email only if both of you prefer it, after you ask privately).

You can also onboard someone you already know (skip step 1) — invite them yourself and still DM the key.

---

## Checklist (new curator)

### 1. Pick an id

- Lowercase, no spaces — usually the LinkedIn slug  
  Example: `eshwarchandravidhyasagar`

### 2. Add them to the index (PR to `develop`)

Edit [`_index.json`](_index.json):

```json
{
  "id": "eshwarchandravidhyasagar",
  "display_name": "Eshwar Chandra Vidhyasagar",
  "linkedin_url": "https://www.linkedin.com/in/eshwarchandravidhyasagar/",
  "github": "EshwarCVS",
  "active": true,
  "notes": "Passphrase is stored only in GitHub Actions (never in this file)."
}
```

- `github` is optional but recommended → commit credit even if you submit on their behalf
- `active: false` pauses ingest without deleting history

### 3. Create their folder + profile

```bash
mkdir -p sources/curators/eshwarchandravidhyasagar
```

Add `sources/curators/eshwarchandravidhyasagar/profile.json`:

```json
{
  "id": "eshwarchandravidhyasagar",
  "display_name": "Eshwar Chandra Vidhyasagar",
  "linkedin_url": "https://www.linkedin.com/in/eshwarchandravidhyasagar/",
  "consent": {
    "submits_voluntarily": true,
    "may_republish_jobs": true,
    "agreed_at": "2026-07-15"
  },
  "tags": ["swe", "new-grad"]
}
```

Consent should be explicit (DM/email). We only republish job links they submit.

### 4. Create / update `CURATOR_KEYS` (Actions secret)

1. Repo → **Settings** → **Secrets and variables** → **Actions**
2. Create or edit secret named exactly **`CURATOR_KEYS`**
3. Value is JSON (one object for all curators):

```json
{
  "eshwarchandravidhyasagar": "<passphrase>",
  "CURATOR_ESHWARCHANDRAVIDHYASAGAR": "<passphrase>"
}
```

Both keys can hold the same passphrase. Alias formula:

`CURATOR_` + id with `-` → `_`, uppercased  
→ `eshwarchandravidhyasagar` becomes `CURATOR_ESHWARCHANDRAVIDHYASAGAR`

Helper (prints names + optional random passphrase; does not write secrets):

```bash
python -m pipeline.generate_curator_key eshwarchandravidhyasagar
```

### 5. Send the passphrase privately (not Gmail-required)

Preferred: **LinkedIn DM** to their profile from the request issue.

In the private message send:

- Curator id (e.g. `eshwarchandravidhyasagar`)
- Passphrase
- Form link: https://github.com/EshwarCVS/job-hunt-engine/issues/new?template=curator-submit.yml

Also fine: any private channel you both use. Optional email only if they chose that and you asked for an address **in a private reply** — never put the passphrase in the public issue.

Then comment publicly on the onboarding issue (safe text only), e.g.:

> Approved as `@theirid`. Passphrase sent via LinkedIn DM. Use the Curator submission form to post.

Close the issue with label `curator-onboarding` kept (or add `onboarded`).

### 6. Smoke test

1. Curator opens the form with a sample post that has ≥1 careers URL
2. Workflow **Ingest Curator Submission** should:
   - Redact the key field on the issue
   - Commit under `sources/curators/<id>/YYYY/MM/`
   - Attribute the commit to their GitHub when possible
   - Trigger scrape → publish to `master`
3. Confirm boards: `README.md` / live site https://eshwarcvs.github.io/job-hunt-engine/ / monthly archive

If auth fails: check id spelling, `active: true`, and that `CURATOR_KEYS` JSON includes that id/alias.

### 7. Offboard

- Set `"active": false` in `_index.json`, **or**
- Remove their entries from `CURATOR_KEYS` (rotate shared secret carefully — rewrite the whole JSON)

Keep historical `jobs.json` unless they ask for removal.

---

## What curators do day-to-day

1. Open **Curator submission**
2. Fill **Curator ID** + **Curator key** + paste LinkedIn post (and comment jobs)
3. Optional: GitHub username, LinkedIn URL, post date
4. Submit and wait for the bot comment (“Accepted on develop”)

They do **not** need git, PRs, or access to repo secrets.

---

## Architecture (why this design)

| Piece | Role |
|-------|------|
| `_index.json` | Public registry (no secrets) |
| `CURATOR_KEYS` | Private map of passphrases |
| Issue form | Paste UX; key redacted immediately |
| `pipeline/curator_ingest.py` | Auth + upsert jobs by apply URL |
| `pipeline/post_extract.py` | Parse multi-URL posts / pipe `Company \| Role \| Loc` |
| `pipeline/commit_author.py` | Credit their GitHub when known |
| `develop` → scrape → `master` | Queue then public board |

Multiple pushes from the same curator **upsert** by URL (no duplicate listings).

---

## Common mistakes

| Mistake | Fix |
|---------|-----|
| Putting passphrase in `_index.json` or a PR | Remove; rotate `CURATOR_KEYS` |
| Forgetting alias + id in JSON | Add both (or at least the id) |
| Workflow only on `master` while queue is `develop` | Keep workflows on both tips / merge develop regularly |
| Curator pastes post **without** apply URLs | Ask them to include careers / greenhouse / ashby / `lnkd.in` links |
| Using the community “Add Job” form for a curator | Point them to the keyed curator form |

See also [CONTRIBUTING.md](../../CONTRIBUTING.md) and [SECURITY.md](../../SECURITY.md).
