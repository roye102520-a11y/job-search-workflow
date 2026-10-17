# Daily job preparation: current scope

## Existing workflow

- `scripts/foreign_opportunities.py` reads an exact allowlist of public employer ATS sources and saves verified observations into the existing application Manifest, Tracker, and event model. The adapters cover reviewed Lever feeds, Greenhouse public board APIs, Ashby public job-board APIs, exact Workday tenants, SmartRecruiters details, and structured enterprise JobPosting pages.
- `scripts/daily_job_search.py` can generate English and Chinese review materials through `resume_pipeline`; it does not send email, fill application forms, start an application attempt, or submit.
- The Career Studio applications section already displays discovered jobs, evidence-based grades, eligibility warnings, preparation status, resume versions, and official links.
- `job_data.py` already reports outcomes from confirmed submission events and uses a 14-day minimum observation window by default. There is no 14-day sprint task record or Day 8/Day 14 review generator yet.

## New local entry point

Run from the repository root with the selected private case:

```sh
python3 scripts/daily_job_search.py --case /absolute/path/to/private-case --daily-prepare --limit 10
```

The command searches the configured reviewed sources, checks the official page again, then prepares bilingual materials for at most 10 verified-open A-level jobs per run. B/C/D/U jobs remain in the existing Tracker for review. Overseas jobs wait until work eligibility is supported; internships wait unless the official posting confirms eligibility for a graduate; explicitly unpaid internships are held. Each generated version is stored with the existing Manifest and appears in the existing Tracker; no application event or external action is created.

`--limit` accepts 1–100, with at most 10 live posting checks from each selected source. The backwards-compatible default CLI/API selection remains the four original Lever feeds. `--all-sources` (or the browser's explicit source list) adds reviewed Greenhouse boards (Anthropic, Study.com, Arize AI), Ashby boards (OpenAI, Ramp, Notion, Cursor), and exact Workday tenants (Cerence, Sanofi, Signify). A failed or stale source is reported as unavailable and cannot create a verified job. This coverage still cannot guarantee 50–100 suitable leads; the result states the limitation rather than filling the gap with unverified sources.

The private case preference `job_search_strategy.geographic_scope=global` enables worldwide location discovery. Overseas roles retain an unknown work-eligibility state until country-specific permission, sponsorship, employer entity, relocation, or remote residence eligibility is supported by the official JD and private facts. The previous location preferences are retained.

The browser's existing “搜索官方岗位” action explicitly requests the expanded source list; no new page or database is introduced. Additional tenants require an explicit code-reviewed allowlist entry before they can be used. Wildcards, arbitrary hosts, authenticated feeds, and cross-domain redirects remain rejected.

## Scheduling and limits

The command is not self-scheduling. No launchd job, cron entry, or hosted scheduler was installed. A local schedule would only run while the Mac is available and may miss network-dependent work while offline; a hosted runner would need an explicitly approved private-data connection and secure storage arrangement. Run the command manually for now. The API and existing UI button remain limited to their current 10-job action.

This is preparation only. Stage 2 application tests, external submission, email sending, and any batch authorization remain separate work requiring user review.
