# Credits & Citations

Job Hunt Engine is open source (MIT) and aggregates listings from public /
voluntarily submitted sources. Keep attribution if you fork or reuse.

## Upstream data sources

Upstream job lists do **not** ship a formal `CITATION.cff`. We follow their
community norms: **link back**, credit maintainers, and keep application URLs
pointing at employers (not mirrors of post text).

| Source | Credit | Link |
|--------|--------|------|
| **SimplifyJobs / Pitt CSC** | Summer internships & new-grad lists maintained by [Pitt CSC](https://pittcsc.org/) and [Simplify](https://simplify.jobs/) | [SimplifyJobs org](https://github.com/SimplifyJobs) |
| **jobright-ai** | SWE / Data / H1B board repos | [jobright-ai org](https://github.com/jobright-ai) |
| **Community & curators** | Voluntary submissions (PR / keyed form) | [`sources/`](sources/) |

Each board row includes a **Source** column. Prefer linking to the original apply URL.

## Open-source software

| Component | Role | License |
|-----------|------|---------|
| This repository | Aggregator, scrapers, board | [MIT](LICENSE) · [Live site](https://eshwarcvs.github.io/job-hunt-engine/) |
| [leash-secrets](https://github.com/FasterApiWeb/leash-secrets) | Secret scanning in CI | MIT |
| Python `requests`, `playwright` | HTTP / browser automation | Upstream licenses |

## How to cite / credit this project

```text
Based on Job Hunt Engine — https://github.com/EshwarCVS/job-hunt-engine (MIT)  
Live board: https://eshwarcvs.github.io/job-hunt-engine/
Job data also attributed to SimplifyJobs (Pitt CSC & Simplify), jobright-ai,
and community curators.
```

If you build something on SimplifyJobs data, also consider giving their repos a
star — they invite shout-outs for cool projects in their READMEs.

## Disclaimer

Listings are aggregated from public and voluntarily submitted sources. We do not
guarantee accuracy. Always verify on the employer’s careers page. Third-party
trademarks belong to their owners.
