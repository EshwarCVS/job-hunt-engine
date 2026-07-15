#!/usr/bin/env python3
"""Print the CURATOR_<ID> name to add into the CURATOR_KEYS GitHub secret.

Does NOT write the repo. Onboard flow:

1. Add curator to sources/curators/_index.json + folder
2. Settings → Secrets → Actions → edit CURATOR_KEYS (JSON)
3. Add: "eshwarchandravidhyasagar": "their-passphrase"
   and/or "CURATOR_ESHWARCHANDRAVIDHYASAGAR": "their-passphrase"
4. DM the passphrase to the curator

Usage:
  python -m pipeline.generate_curator_key eshwarchandravidhyasagar
"""

from __future__ import annotations

import secrets
import sys

from pipeline.curator_ingest import curator_secret_env_name


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: python -m pipeline.generate_curator_key <curator_id>", file=sys.stderr)
        return 2
    curator_id = argv[1].strip().lstrip("@").lower()
    env_name = curator_secret_env_name(curator_id)
    suggested = secrets.token_urlsafe(16)
    print(f"Curator id:           {curator_id}")
    print(f"Secret map name:      CURATOR_KEYS   (one GitHub Actions secret for everyone)")
    print(f"JSON entry (id):      \"{curator_id}\": \"<passphrase>\"")
    print(f"JSON entry (alias):   \"{env_name}\": \"<passphrase>\"")
    print()
    print("You may use a memorable passphrase instead of random — just never commit it.")
    print(f"Random suggestion (optional): {suggested}")
    print()
    print("Edit GitHub → Settings → Secrets → Actions → CURATOR_KEYS only.")
    print("Do not commit passphrases. Do not add a new workflow env line per curator.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
