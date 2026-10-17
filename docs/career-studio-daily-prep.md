# Daily job preparation: current scope

## Existing workflow

- `scripts/foreign_opportunities.py` reads a small allowlist of public employer ATS sources and saves verified observations into the existing application Manifest, Tracker, and event model.
- `scripts/daily_job_search.py` can generate English and Chinese review materials through `resume_pipeline`; it does not send email, fill application forms, start an application attempt, or submit.
- The Career Studio applications section already displays discovered jobs, evidence-based grades, eligibility warnings, preparation status, resume versions, and official links.
- `job_data.py` already reports outcomes from confirmed submission events and uses a 14-day minimum observation window by default. There is no 14-day sprint task record or Day 8/Day 14 review generator yet.

## New local entry point

Run from the repository root with the selected private case:

```sh
python3 scripts/daily_job_search.py --case /absolute/path/to/private-case --daily-prepare --limit 10
```

The command searches the configured reviewed sources, checks the official page again, then prepares bilingual materials for at most 10 verified-open A-level jobs per run. B/C/D/U jobs remain in the existing Tracker for review. Overseas jobs wait until work eligibility is supported; internships wait unless the official posting confirms eligibility for a graduate; explicitly unpaid internships are held. Each generated version is stored with the existing Manifest and appears in the existing Tracker; no application event or external action is created.

`--limit` accepts 1–100, with at most 10 live posting checks from each of the four currently configured Lever feeds. The current source allowlist is Welo Global, Wing Assistant, Veeva Systems, and RWS Group, so the current actual upper bound is 40. This coverage cannot produce 50–100 global leads by itself. The result states this limitation rather than filling the gap with unverified sources.

The private case preference `job_search_strategy.geographic_scope=global` enables worldwide location discovery. Overseas roles retain an unknown work-eligibility state until country-specific permission, sponsorship, employer entity, relocation, or remote residence eligibility is supported by the official JD and private facts. The previous location preferences are retained.

## Scheduling and limits

The command is not self-scheduling. No launchd job, cron entry, or hosted scheduler was installed. A local schedule would only run while the Mac is available and may miss network-dependent work while offline; a hosted runner would need an explicitly approved private-data connection and secure storage arrangement. Run the command manually for now. The API and existing UI button remain limited to their current 10-job action.

This is preparation only. Stage 2 application tests, external submission, email sending, and any batch authorization remain separate work requiring user review.
