# monitor-opportunities project agent

## Immutable goal

Daily top opportunities that are highly targeted, delivered in an interactive
report/interview, with auto-apply using a custom targeted resume given the algorithm
likely employed by the employer or client.

“Algorithm likely employed” is operationalized as an evidence-backed screening-interface
profile with explicit unknowns, not a claim about proprietary ranking weights.

## Current implementation boundary (updated 2026-08-08)

The nightly pipeline is OPERATIONAL and scheduled (`monitor-opportunities-nightly`,
cron `0 2 * * *`, verified success). It runs live: read-only browser capture (SAM.gov
website, LinkedIn advanced-search + top-applicant of the human's OWN authenticated
session), Greenhouse/Ashby ATS sweeps, brave-search client research, 2-week recency +
role-type + mandate-relevance (via `/extract-entities` vocabulary) filtering,
mandate-tailored resumes for the top jobs, live ATS application-form capture, a
memory-backed morning report, and per-opportunity tracking as issues in the PRIVATE
repo `grahama1970/opportunities` (dual queues: `track:employment`, `track:consulting`).

`external_effects` remains FALSE by design: nothing is auto-submitted and no InMail/Gmail
is auto-sent. Submit is human-authorized (application_plan gate); outreach drafts go to
`/memory` and the human transmits. `network_access` is TRUE (browser, brave-search, memory).

Written but NOT yet live-proven: the per-opportunity `/tau` creator-reviewer evaluation
loop (opportunity-evaluator + opportunity-evaluation-reviewer subagent contracts in
`agents/`), mandate-first ranking, and the learned relevance classifier (label flywheel
accumulating toward `MIN_LABELS_TO_TRAIN`). The rubric is `best-practices-opportunities`.

## Post-run requirement

After changing this skill:

1. run `./sanity.sh`;
2. run `./run.sh verify --out <retained-directory>`;
3. read back `verification-receipt.json`, `positive-report/report.json`, and
   `positive-report/index.html`;
4. report each failed case, exact error code, changed files, commands, source version,
   limitations, and non-claims;
5. create or update the focused maintainer ticket for any discovered gap.

## Forbidden self-improvement

The agent may propose but must not silently change the immutable goal, Buffalo geography,
capability authority, target/source registry, claim facts, human attestations, thresholds,
caps, or external-effect policy.
