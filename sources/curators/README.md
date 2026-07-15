# Curator owned spaces

Maintainer onboarding (full steps): **[ONBOARDING.md](ONBOARDING.md)**

```text
sources/curators/
  _index.json
  ONBOARDING.md
  <curator-id>/
    profile.json
    <year>/
      <month>/
        jobs.json          # structured jobs extracted from posts
        posts/             # raw pasted LinkedIn text (no keys)
```

## Form flow

1. Curator opens **Curator submission** issue → id + passphrase + **post as-is**
2. Action **redacts the passphrase** from the issue immediately
3. Post is parsed (apply URLs + title/company/location/visa heuristics)
4. Files land on **`develop`** under the curator year/month folder
5. Scrape/publish is triggered → listings appear on **`master`**

## Secrets (`CURATOR_KEYS`)

One GitHub Actions secret (JSON). Do **not** put real passphrases in git.

```json
{
  "eshwarchandravidhyasagar": "<passphrase>",
  "CURATOR_ESHWARCHANDRAVIDHYASAGAR": "<passphrase>"
}
```

Alias = `CURATOR_` + id in screaming case. Onboard = edit this secret only (no workflow change).

Memorable passphrases are fine; rotate if one was visible before redact.

## Credits / git attribution

Commits from curator ingest use the submitter's GitHub identity when known
(form username → `_index.json` `github` → issue author → maintainer fallback).
Fill `github` in `_index.json` when onboarding so credit still works if a maintainer
pastes on their behalf.

See [CREDITS.md](../../CREDITS.md).
