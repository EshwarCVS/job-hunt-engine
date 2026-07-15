# Curator owned spaces

```text
sources/curators/
  _index.json                          # public registry (NO keys)
  <curator-id>/
    profile.json
    <year>/
      <month>/
        jobs.json                      # voluntary submissions
```

Example: `sources/curators/madhanvadlamudi/2026/07/jobs.json`

## How keys work (GitHub Secrets — not the repo)

```text
You (maintainer)                    Madhan (curator)                 GitHub Actions
─────────────────                   ────────────────                 ──────────────
1. Generate a random key
2. Store it as Actions secret
   CURATOR_KEY_MADHANVADLAMUDI ──┐
3. DM the same key to Madhan      │
                                  │ 4. Opens Curator issue form
                                  │ 5. Pastes curator id + key
                                  │ 6. Pastes LinkedIn post as-is
                                  └────────────────────────────────► 7. Loads secret from GitHub
                                                                     8. Constant-time compare
                                                                     9. If match → append jobs.json
                                                                    10. Redact key on the issue
```

- **Where the key is stored:** only in **GitHub → Settings → Secrets and variables → Actions**
  (secret name `CURATOR_KEY_MADHANVADLAMUDI`, or a JSON map secret `CURATOR_KEYS`).
- **Not stored in git:** `_index.json` only lists the secret *name*, never the value.
- **How Madhan enters it:** the [Curator submission](../../issues/new?template=curator-submit.yml) form field **Curator key**.
- **How validation works:** the workflow injects `${{ secrets.CURATOR_KEY_… }}` into the job environment; `pipeline/curator_ingest.py` compares the form value with `hmac.compare_digest`. No match → nothing is written.

### Maintainer setup

```bash
python -m pipeline.generate_curator_key madhanvadlamudi
# Copy printed name + value into GitHub Actions secrets.
# DM the value to the curator. Do not commit it.
```

For new curators, also add an `env:` line in `.github/workflows/curator-submit.yml`:

```yaml
CURATOR_KEY_NEWPERSON: ${{ secrets.CURATOR_KEY_NEWPERSON }}
```

(or put everyone in one `CURATOR_KEYS` JSON secret: `{"madhanvadlamudi":"…","other":"…"}`).

### Security notes

- Rotate the secret if an issue showed the key before redact.
- Prefer a secondary identity for automation; never put personal passwords in secrets meant for curators.
- Public issue forms are briefly visible — redact runs after ingest; treat keys as rotatable.

## Credits

See [CREDITS.md](../../CREDITS.md).
