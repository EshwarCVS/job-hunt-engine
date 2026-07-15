#!/usr/bin/env python3
"""Generate a random curator submit key for GitHub Actions secrets.

Does NOT write anything to the repo. Copy the printed key into:
  Repo → Settings → Secrets and variables → Actions → New repository secret
  Name:  CURATOR_KEY_<CURATORID_UPPER>
  Value: <printed key>

Then send the same value to the curator privately (DM). They paste it in the
curator issue form. The Action compares form input to the secret.

Usage:
  python -m pipeline.generate_curator_key madhanvadlamudi
"""

from __future__ import annotations

import secrets
import sys


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: python -m pipeline.generate_curator_key <curator_id>", file=sys.stderr)
        return 2
    curator_id = argv[1].strip().lstrip("@").lower().replace("-", "")
    secret_name = "CURATOR_KEY_" + curator_id.upper().replace("-", "_")
    key = secrets.token_urlsafe(32)
    print(f"GitHub secret name:  {secret_name}")
    print(f"GitHub secret value: {key}")
    print()
    print("1) Add the secret in GitHub (Settings → Secrets → Actions).")
    print("2) DM the value to the curator — do not commit it, do not paste it in issues yourself.")
    print("3) Tell them to use the Curator submission issue form and paste the key there.")
    print("4) Wire the secret into .github/workflows/curator-submit.yml env if it is a new curator.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
