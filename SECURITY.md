# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue for secrets or account compromises.

Email the maintainer via GitHub ([EshwarCVS](https://github.com/EshwarCVS)) using a private channel, or open a **private** security advisory on the repository if enabled.

## Secrets

Never commit:

- LinkedIn `li_at` cookies
- Curator submit keys
- API tokens / `.env` files

Use GitHub Actions secrets / local `.env` (gitignored). Curator keys belong in
`Settings → Secrets and variables → Actions` only.

## Automated checks

Pushes run [leash-secrets](https://github.com/FasterApiWeb/leash-secrets) on changed files.
