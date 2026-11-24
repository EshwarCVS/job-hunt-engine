# Job Hunt Engine

Your open-source job board for tech roles — internships, new grad, and experienced.

**Website (sort & filter):** https://eshwarcvs.github.io/job-hunt-engine/

<p>
  <a href="https://eshwarcvs.github.io/job-hunt-engine/"><img src="https://img.shields.io/static/v1?label=last%20updated&message=2026-11-24&color=0A66C2" alt="Last updated" /></a>
  <a href="https://eshwarcvs.github.io/job-hunt-engine/"><img src="https://img.shields.io/static/v1?label=jobs%20this%20month&message=0&color=2ea44f" alt="Job count" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/static/v1?label=license&message=MIT&color=informational" alt="License" /></a>
  <a href="https://eshwarcvs.github.io/job-hunt-engine/"><img src="https://img.shields.io/static/v1?label=website&message=GitHub%20Pages&color=222" alt="Website" /></a>
  <img src="https://img.shields.io/static/v1?label=sources&message=Simplify%20%C2%B7%20jobright%20%C2%B7%20LinkedIn%20%C2%B7%20Community&color=6f42c1" alt="Sources" />
</p>

**Quick links:** [Interactive Board (sort & filter)](https://eshwarcvs.github.io/job-hunt-engine/) ·
[Contribute a job](CONTRIBUTING.md) ·
[Curator form](https://github.com/EshwarCVS/job-hunt-engine/issues/new?template=curator-submit.yml) ·
[Curator onboarding (maintainers)](sources/curators/ONBOARDING.md) ·
[Data sources](sources/README.md) ·
[How scraping works](pipeline/README.md) ·
[Credits](CREDITS.md) ·
[Security](SECURITY.md) ·
[Code of Conduct](CODE_OF_CONDUCT.md) ·
[Issues](https://github.com/EshwarCVS/job-hunt-engine/issues)

**Support the project:** ⭐ [Star this repo](https://github.com/EshwarCVS/job-hunt-engine) · ⭐ [Star @EshwarCVS](https://github.com/EshwarCVS)

---

## Help wanted

This project stays useful when the community helps. We especially need:

- New / hard-to-find listings via [community PR or issue](CONTRIBUTING.md)
- Curators: paste posts with the [curator form](https://github.com/EshwarCVS/job-hunt-engine/issues/new?template=curator-submit.yml) (secret key + owned year/month folder) · [request access](https://github.com/EshwarCVS/job-hunt-engine/issues/new?template=curator-request.yml)
- Bug reports for dead application links
- Improvements to scrapers and the interactive board ([live site](https://eshwarcvs.github.io/job-hunt-engine/)) — see [pipeline/README.md](pipeline/README.md)
- ⭐ Star [this repo](https://github.com/EshwarCVS/job-hunt-engine) and [@EshwarCVS](https://github.com/EshwarCVS) if it helps you

---

## November 2026 Jobs

> **0** active listings · newest first · previous month: _no prior archive yet_ ·
> full list with **sort & filter**: [Interactive Board](https://eshwarcvs.github.io/job-hunt-engine/)

<details open>
<summary><strong>Job listings</strong> (click to collapse / expand) — preview of 0 / 0</summary>

_No verified listings for this period yet. Jobs appear after the next successful scrape from public sources or a community/curator submission with a real application URL._

</details>

---

## Job Archives

Browse previous months:

- **2026**: [November](jobs/2026/november.md)

---

## Tips & Tricks

### Resume Optimization
- **Tailor your resume** for each application — match keywords from the job description
- **Quantify impact** — "Reduced API latency by 40%" beats "Improved performance"
- **ATS-friendly format** — use standard section headers, avoid tables/columns, stick to PDF
- **One page** for < 5 years experience, two pages max for senior roles

### Application Strategy
- **Apply early** — most roles fill within 2 weeks of posting
- **Track everything** — use a spreadsheet or tool to avoid duplicate applications
- **Referrals matter** — a referral increases your callback rate by 5-10x
- **Don't self-reject** — apply if you meet 60%+ of the requirements

### Interview Preparation
- **System design** — practice with real-world scenarios, not just textbook patterns
- **Behavioral questions** — prepare 8-10 STAR stories covering leadership, conflict, failure, and impact
- **Coding practice** — LeetCode medium-level problems, focus on patterns not memorization
- **Research the company** — know their product, recent news, and tech stack

### Negotiation
- **Always negotiate** — the first offer is rarely the best offer
- **Get competing offers** — leverage is your best friend
- **Consider total comp** — base, bonus, equity, benefits, and growth potential
- **Get it in writing** — verbal offers aren't binding

### Resources
- [Resume Tips](skills/resume-tips.md) — plus [LinkedIn resume checklist](https://www.linkedin.com/posts/eshwarchandravidhyasagar_resumetips-jobsearch-softwareengineering-activity-7458586210945490946-1yzF) and [live resume review](https://www.linkedin.com/posts/eshwarchandravidhyasagar_resumereview-jobsearch-careersupport-share-7450549819946835968-e_pG)
- [Interview Checklist](skills/interview-checklist.md)
- [ATS Optimization](skills/ats-optimization.md)
- [Vigilant Lamp](https://github.com/EshwarCVS/vigilant-lamp) — learning tracks (SDE, data, FDE, systems)
- [More Resources](resources.md)

---

## Data Sources

| Source | What it provides | Config |
|--------|------------------|--------|
| [SimplifyJobs](https://github.com/SimplifyJobs) | Internships & new grad | [`sources/repos.json`](sources/repos.json) |
| [jobright-ai](https://github.com/jobright-ai) | SWE, Data, H1B by level | [`sources/repos.json`](sources/repos.json) |
| [LinkedIn profiles](sources/linkedin-profiles.json) | Hiring posts (throttled) | [`linkedin-profiles.json`](sources/linkedin-profiles.json) |
| [Curators](sources/curators/README.md) | Voluntary posts via keyed form | [`sources/curators/`](sources/curators/) |
| Community PRs | Submitted listings | [`community-jobs.json`](sources/community-jobs.json) |

### Source repository registry

Tracked source repositories (auto-updated each scrape). Inactive repos are archived after the threshold in [`sources/config.json`](sources/config.json).

### SimplifyJobs

**Active**

- [New-Grad-Positions](https://github.com/SimplifyJobs/New-Grad-Positions) — last activity `2026-11-23`
- [Summer2026-Internships](https://github.com/SimplifyJobs/Summer2026-Internships) — last activity `2026-11-23`
- [Summer2027-Internships](https://github.com/SimplifyJobs/Summer2027-Internships) — last activity `2026-11-23`

<details>
<summary>Archived (1)</summary>

- [Summer2025-Internships](https://github.com/SimplifyJobs/Summer2025-Internships) — Not scraped (backfill disabled); incorrect URL corrected

</details>

### jobright-ai

**Active**

- [2026-Data-Analysis-Internship](https://github.com/jobright-ai/2026-Data-Analysis-Internship) — last activity `2026-11-23`
- [2026-Data-Analysis-New-Grad](https://github.com/jobright-ai/2026-Data-Analysis-New-Grad) — last activity `2026-11-23`
- [2026-Software-Engineer-Internship](https://github.com/jobright-ai/2026-Software-Engineer-Internship) — last activity `2026-11-23`
- [2026-Software-Engineer-New-Grad](https://github.com/jobright-ai/2026-Software-Engineer-New-Grad) — last activity `2026-11-23`
- [Daily-H1B-Jobs-In-Tech](https://github.com/jobright-ai/Daily-H1B-Jobs-In-Tech) — last activity `2026-05-06`


---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) to:

- Submit job listings via Pull Request or issue
- Curators: use the [keyed submission form](https://github.com/EshwarCVS/job-hunt-engine/issues/new?template=curator-submit.yml)
- Add LinkedIn profiles / new scrapers
- Report broken links

### Contributors — November 2026

_Be the first community contributor this month — [add a job](CONTRIBUTING.md)!_

---

## Credits & citations

This project is open source ([MIT](LICENSE)) and stands on upstream open data.
Please keep attribution when you reuse it.

- Full citations: **[CREDITS.md](CREDITS.md)**
- Upstream orgs: [SimplifyJobs](https://github.com/SimplifyJobs), [jobright-ai](https://github.com/jobright-ai)
- Curator spaces: [`sources/curators/`](sources/curators/)

Suggested blurb:

> Based on [Job Hunt Engine](https://github.com/EshwarCVS/job-hunt-engine) (MIT).
> Live board: https://eshwarcvs.github.io/job-hunt-engine/
> Job data also attributed to SimplifyJobs, jobright-ai, and community curators.

---

## License

MIT — see [LICENSE](LICENSE).

> **Disclaimer**: Listings are aggregated from public and voluntarily submitted sources. Always verify details on the company's official careers page before applying.
