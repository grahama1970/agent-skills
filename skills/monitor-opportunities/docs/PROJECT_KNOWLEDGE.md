# monitor-opportunities project knowledge

Updated: 2026-08-14
Authoritative branch target: `grahama1970/agent-skills@main`
Immutable goal: see `../SKILL.md`. Rubric: `best-practices-opportunities`.

## Current state (2026-08-14): promoted Stage 0 cron path proven, effects gated

WebGPT review on 2026-08-13 found that current main could produce success-looking reports
with schema-invalid Meetup values, loose required-source matching, hidden downstream work,
LinkedIn-only opportunity admission, and test-fixture claim authority. The current repair
line makes those paths fail closed and has live promoted receipts:

- report manifests validate against the committed `schemas/report.schema.json` before
  rendering;
- the authoritative shortlist and all downstream apply-prep artifacts are capped at the
  report-visible set;
- required source receipts bind exact `required_source_id`, lane/channel/source-class, and
  accepted terminal states;
- API failure fallback requires a bound website/browser receipt with retained evidence;
- LinkedIn rows and Meetup groups render as `source_intel`, not opportunities;
- Meetup source intelligence cannot create resume, outreach, application, or application
  packet artifacts;
- claim-bearing artifacts bind one run-scoped claim snapshot digest, and live runs cannot
  use `tests/fixtures` as claim authority;
- Indeed and HiddenJobs mandatory browser captures are read-only source-health evidence
  only and do not admit aggregator rows as opportunities;
- `apply` is an implemented local gate over report-visible application packets. It checks
  packet drift, unresolved `human_required` fields, human authorization, and capability
  authority, then fails closed with `external_effects=false`;
- ranking is mandate-first before geography, with a regression proving a high-fit remote
  Principal AI role outranks a mediocre local role;
- browser pacing no longer calls `surf wait`; live promoted receipts show
  `browser_control.status=OK`, `events=0` after the repair;
- a Tau local creator/reviewer smoke runs one report-visible opportunity through a
  Tau generic artifact transaction with producer, validator, reviewer, goal-hash
  binding, and receipts (`scripts/tau_opportunity_eval_smoke.py`). This is
  `provider_live=false` proof of Tau plumbing, not semantic provider evaluation.
- WebGPT review on 2026-08-14 returned `NEEDS_ATTENTION` for enabling provider-live
  Tau semantic evaluation in the 2 AM cron. The accepted next slice is a non-blocking
  sidecar path. Slice `MO-TAU-SEM-01` now freezes
  `monitor_opportunities.tau_semantic_input.v1` through
  `schemas/tau-semantic-input.schema.json` and `validate_tau_semantic_input()`.
  It requires immutable-goal hash binding, primary non-Meetup opportunity evidence,
  retained source/artifact hashes, redacted relationship facts, Meetup supplemental-only
  policy, and `external_effects=false`.

`external_effects` remains FALSE by design: no auto-submit, no InMail/Gmail send, and no
LinkedIn platform action.

Latest deterministic receipts on `main`:

- pushed runtime-proof revision: `5e5618bf253de4fe21612515c6f0c845c2f8c710`;
- full sanity: `304 passed`, `monitor-opportunities sanity: PASS`;
- live promoted nightly receipt:
  `skills/monitor-opportunities/local/nightly/latest/nightly-receipt.json`
  in the cron worktree, with `status=PASS`, `mocked=false`, `live=true`,
  `mode=PROMOTED_STAGE_0`, `external_effects=false`,
  `expected_revision=5e5618bf253de4fe21612515c6f0c845c2f8c710`, and
  `browser_control.status=OK`;
- run status: `operational_readiness=STAGE_0_READY`, source health
  `degraded_count=0` across 43 receipts, 8 opportunities, 8 applications,
  8 application packets, 8 resume variants, 16 outreach packets, 57 relationship
  signals, 105 visible action-worthy artifacts, and `hidden_total=0`;
- digest counts: 8 employment items and 4 consulting signals;
- prospect queue: 74 prospects, including 57 relationship signals and 13 federal
  entries;
- Memory readback: `readback_found=true`,
  `relationship_readback_found=true`, `external_effects=false`;
- Buzz readback: `posted=true`, `live=true`, `external_effects=false`;
- Tau local evaluator smoke:
  `/tmp/monitor-opportunities-tau-eval-smoke-20260814T2120Z/tau-eval-smoke-receipt.json`,
  with `status=PASS`, `mocked=false`, `live=true`, `provider_live=false`,
  `completed_node_count=1`, review verdict `PASS`, and `external_effects=false`;
- WebGPT Ask/Tau review:
  local run directory
  `skills/monitor-opportunities/local/review/ask-webgpt-tau-semantic-eval/...`,
  with Surf provider result `response_proven`, provider live true, and WebGPT verdict
  `NEEDS_ATTENTION` for adding provider-live semantic evaluation to the 2 AM cron
  before slices `MO-TAU-SEM-01` through `MO-TAU-SEM-05` have live receipts;
- scheduler receipt:
  `/home/graham/.pi/scheduler/receipts/monitor-opportunities-nightly-receipt.json`,
  cron `0 2 * * *`, enabled, workdir
  `/home/graham/workspace/experiments/agent-skills-worktrees/monitor-opportunities-cron-main`
  (read back after each scheduler update), pinned to revision
  `5e5618bf253de4fe21612515c6f0c845c2f8c710`.

Pipeline (deterministic orchestrator; browser/LLM work is bounded sub-steps):
1. **Discovery** — read-only browser capture of SAM.gov + LinkedIn advanced-search &
   top-applicant (human's OWN authenticated session, via `surf window.new` like `/ask`);
   Greenhouse/Ashby ATS sweeps; brave-search client research. Dead API → website fallback
   is enforced in code (`_enforce_api_website_fallback`).
2. **Filtering** — 2-week recency gate (`REJECT_STALE_AGE`), role-type targeting
   (`REJECT_ROLE_TYPE`, token-safe), and mandate relevance via `/extract-entities` against
   the `opportunity_vocabulary` ArangoDB corpus (NOT regex; fail-soft to regex).
3. **Tailoring** — claim-bound custom resume per top job (`apply-prep`, top-N, gated).
4. **ATS capture** — live read-only application-form schema (Greenhouse API / surf DOM).
5. **Tracking** — each opportunity is a GitHub issue in the PRIVATE repo
   `grahama1970/opportunities`, deduped by `content_hash`, lifecycle via labels; dual
   queues `track:employment` and `track:consulting` (prospect queue = federal
   solicitations + commercial signals, mandate-filtered).
6. **Delivery** — memory (`morning_opportunities`) + Buzz summary; query via ops-buzz.

Still not complete against the immutable goal (honest gaps):
- Full per-opportunity `/tau` semantic provider evaluation loop in the nightly path
  (`opportunity-evaluator` + `opportunity-evaluation-reviewer` contracts in `agents/`,
  pass best-practices-subagent). Current proof is a local Tau artifact-transaction
  smoke over one report item plus a committed input contract; it does not prove
  provider/model semantic quality, all top-N opportunities, or 2 AM OAuth/provider
  behavior.
- **Learned relevance classifier** — label flywheel (`opportunity_labels`) accumulating
  toward `MIN_LABELS_TO_TRAIN=300`; trains via `/classifier-lab` when ready.
- Actual ATS submit remains blocked by stage and policy. Submit requires separate
  site/provider promotion plus exact per-application human authorization bound to the
  packet digest. Stage 0 `apply` never submits or prefills.

Live nightly readiness is no longer gated on Indeed/HiddenJobs, claim authority, or
delivery/readback for the current Stage 0 cron path; those have receipt-backed coverage.

The local kernel now includes two Buzz adapters. `buzz-summary` turns a completed report
run into an `ops_buzz.message.v1` shortlist/result summary and receipts it through
`ops-buzz post`; dry-run is the safe default, while `--post` is an explicit Buzz write.
`buzz-review` turns the same run into an `ops_buzz.agent_request.v1` advisory handoff and
runs it through `ops-buzz ask-agent --dry-run`. These prove typed seams and receipts only.
They do not make Buzz the opportunity finder, observe agent response quality, create
Gmail/InMail drafts, or mutate the monitor decision ledger.

Draft storage decision (Graham, 2026-08-05): outreach drafts of record live in the
memory service's ArangoDB `outreach_drafts` collection (`POST /store` on
`http://127.0.0.1:8601`, keys `draft-YYYYMMDD-<packet>`), digest-bound to the reviewed
packet payload with the roundtable verdict and human gates attached. Gmail mailbox
draft creation is NOT the draft store: a 2026-08-05 trial created five mailbox drafts
via the authenticated browser and Graham chose to delete them the same day because the
mailbox namespace is ambiguous (subject collisions with pre-existing drafts) and UI
automation is brittle. Nightly runs should write drafts to memory, not Gmail. Gmail
send and LinkedIn automation remain permanently forbidden; the human transmits.

Interface decision (Graham, 2026-08-05): chat is the interface; the report is a
receipt. The nightly transaction (`run.sh nightly`) runs the sweep, publishes the
shortlist into the memory `morning_opportunities` collection (recallable via
/memory, BM25 + semantic), and posts the Buzz summary to the configured channel
(`config/notifications.json`). Graham asks agents about the morning shortlist and
records decisions through the ledger-backed `decision` command; the rendered
report stays in the run directory as the frozen audit artifact and no longer
requires Tailscale serving or remote readback. Scheduler registration
(`monitor-opportunities-nightly`, cron 0 2 * * *) is live.

The report is the product. The first working-value milestone is not auto-apply; it is a
zero-network Stage 0 kernel that can validate and render the expected morning report,
write a verification receipt, and prove Gmail, LinkedIn, and ATS effects are unreachable.

`local/HANDOFF.md` is a timestamped historical snapshot. Its statement that the skill was
untracked was superseded by commit `76697ea5ec0561aba83cfe0adbe0e3c475b2a6de`, which
added the initial contract to `main`. Its substantive implementation warning remains
correct for every capability not explicitly reported as implemented by `status`.

## Product decisions

1. One report manifest and one human entry point expose all action-worthy work. Hidden
   drafts, variants, plans, blockers, or decisions are defects.
2. Co-equal lanes mean honest coverage, not equal output.
3. Buffalo/WNY is an eligibility gate. Relocation-required roles are rejected before
   ranking.
4. Search/aggregator results can locate primary evidence but cannot independently admit
   an opportunity.
5. Public ATS posting interfaces prove discovery content, not submit authority.
6. “Algorithm-aware” tailoring is represented as an evidence-backed
   `screening_interface_profile`, never proprietary-weight speculation.
7. Candidate facts come from one approved claim snapshot. Tailoring cannot mint facts.
8. Gmail send and all LinkedIn outbound/action automation are permanently outside this
   skill. `ops-linkedin` may provide authorized read-only opportunity evidence from a
   human-supplied tab, but the human transmits every message and performs every LinkedIn
   action.
9. ATS inspect, prefill, and submit are separate site/provider capabilities. Submit also
   requires per-application exact-payload human authorization.
10. Unknown or sensitive application fields, and every free-text field, are
    `human_required`.
11. Empty nights are valid. Volume is audit data, not a success objective.
12. Feed failure, no matches, and not searched are distinct evidence states.

## Focused implementation sequence

| Order | Issue / PR | Slice | Value unlocked |
|---:|---:|---|---|
| 1 | #1165 / #1176 | Freeze report, safety, tailoring, and source contracts | implementation target and expected fixture |
| 2 | #1166 / #1180 | Zero-network status/report/verify kernel | first runnable, safe user value |
| 3 | #1167 | Research-first read-only discovery | real source and feed-health evidence |
| 4 | #1168 | Hard eligibility then deterministic ranking | defensible shortlist or valid empty night |
| 5 | #1169 | Claim-bound resume compiler | safe per-opportunity resume artifacts |
| 6 | #1170 | Append-only local decision loop | actual interactive morning product |
| 7 | #1171 | Resumable nightly run and scheduler readback | daily Stage 0 operation |
| 8 | #1172 | Draft-only Gmail and local LinkedIn handoffs | human-transmitted outreach workflow |
| 9 | #1173 | Site-specific ATS inspect/prefill/submit gates | bounded auto-apply after human authorization |

Do not collapse these into one implementation PR. The first seven slices establish useful
Stage 0 operation without external effects. Issues #1172 and #1173 are promotion work and
must not block the report-first value path.

Recommended merge order is #1176 first, then rebase/read back #1180 against the merged
contract and run the committed fixture through `report` and `verify`. Both PRs were tested
for compatibility before publication; merge-time readback remains required.

## Readiness gates

### Stage 0 report kernel

Required before any live discovery:

- expected report fixture validates and renders;
- status distinguishes implemented, unimplemented, and unauthorized capabilities;
- negative gates reject hidden items, sendable outreach, Stage 0 ATS authorization,
  auto-filled free text, relocation shortlist entries, and shortlist size over eight;
- `verify` writes and reads back a machine-readable receipt;
- no network client or connected-system adapter exists in the kernel.

### Live read-only nightly product

Required before scheduler registration:

- at least one live official Lane A source receipt;
- honest Lane B health result;
- primary-source Lane C result or valid no-match;
- eligibility/ranking receipts;
- claim-bound variant generation and prohibited-delta probes;
- one report entry point with hidden-artifact count zero;
- decision replay and crash recovery;
- one full Stage 0 run with `external_effects: false`.

### External effects

Required separately per capability:

- human promotion receipt with exact scope, evidence, version, expiry/revocation;
- exact item/payload authorization where required;
- idempotency/reservation and readback;
- `INDETERMINATE` reconciliation before retry;
- report and ledger reflect the observed effect;
- negative proof that neighboring forbidden capabilities remain unreachable.

## Known external dependencies and blockers

- `/memory` or an approved export must expose exactly one current claim snapshot. Direct
  database access is forbidden.
- Gmail OAuth requires human browser authorization. Gmail integration must be merged and
  independently proven before mailbox drafts are promoted.
- LinkedIn is only one source in the monitor. `ops-linkedin` may capture one
  human-authorized opportunity tab as read-only local evidence, but the monitor remains
  responsible for cross-source discovery, eligibility, ranking, and report visibility.
  Hiddenjobs.dev, Indeed/source locators, employer ATS sources, DARPA, SAM.gov, and
  commercial primary sources are still co-equal lanes.
- Human attestations for clearance, citizenship/work authorization, salary, phone, and
  self-identification remain missing/unknown until explicitly provided. The system may not
  infer them.
- Source/provider behavior and terms are time-sensitive. Each live adapter qualification
  records current evidence and limitations.

## Non-claims

- The proven promoted nightly is Stage 0 research/report operation only; it does not
  prove ATS submission, Gmail send, LinkedIn outbound action, or job/client outcomes.
- The expected fixture and Stage 0 kernel do not prove ranking quality, resume
  effectiveness, Gmail draft creation, or ATS submission.
- A working ATS discovery interface does not prove an application-submit interface.
- A model or roundtable verdict is advisory and cannot authorize facts or effects.
- This project does not optimize application volume or promise job/client outcomes.
