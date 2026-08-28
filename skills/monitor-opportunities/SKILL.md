---
name: monitor-opportunities
description: >
  Nightly opportunity monitor that researches a bounded set of target employers and
  clients, ranks only eligible opportunities, compiles claim-bound resume variants,
  and emits one interactive morning report covering human-transmitted outreach and
  separately gated ATS application state. Use when the user asks for today's
  opportunities, the morning opportunity report, a targeted resume, what needs human
  action, or to run or schedule the nightly opportunity sweep.
allowed-tools:
  - Bash
  - Read
  - Write
triggers:
  - monitor opportunities
  - today's opportunities
  - morning opportunity report
  - opportunity digest
  - what should I apply to
  - tailor my resume for this job
  - targeted resume for this posting
  - nightly opportunity sweep
  - what needs sending
  - opportunity report
  - find me work
  - client prospects
metadata:
  short-description: Nightly opportunity report with claim-bound tailoring and gated effects
  author: Graham
  version: "0.2.0"
runtime_self_improvement: substantial

provides:
  - opportunity-discovery
  - opportunity-ranking
  - targeted-resume-generation
  - interactive-opportunity-report
composes:
  - memory
  - monitor-contacts
  - brave-search
  - extract-entities
  - surf
  - ticket
  - ops-buzz
  - classifier-lab
  - mailbox-mining
  - ops-linkedin
  - monitor-website
  - test-interactions
  - gmail
  - ask
  - scheduler
  - task-monitor
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-arangodb
  - best-practices-roundtable
  - best-practices-security
  - best-practices-opportunities
taxonomy:
  - operations
  - retrieval
  - precision
  - human-in-the-loop
  - composition
disciplines:
  - research-retrieval
  - observability-operations
---

# monitor-opportunities

## Immutable goal

> **monitor-opportunities does the grunt work of the daily job and consulting
> search; Graham only reviews our collaboration and approves. Each day it
> discovers, ranks, and surfaces the most-targeted opportunities — Buffalo/WNY
> first, then credible remote — and surfaces where Graham is a LinkedIn top
> applicant or a role offers quick (Easy) apply. On Graham's authorization
> for one exact opportunity after reviewing the morning report), the agent may
> perform the application end-to-end: tailoring a truthful custom resume to the
> employer's likely screening algorithm, answering only from Graham's attested
> facts, and submitting on employer ATS or LinkedIn Easy Apply with duplicate
> protection and an openable receipt for every action. Graham authorizes a
> specific payload after collaboration; the agent executes that authorized
> payload. Nothing is fabricated, and no required answer without a truthful
> basis is ever submitted — any genuine screening question is surfaced to
> Graham, never guessed.**

> **Easy Apply authorization correction (Graham, 2026-08-26):** LinkedIn Top
> Applicant and Easy Apply are discovery and prioritization signals. They are
> not standing authorization and must never trigger automatic application
> submission. The nightly report must surface these opportunities, prepare the
> truthful resume/payload material, and wait for Graham's explicit
> post-collaboration authorization for that exact opportunity and payload before
> any LinkedIn Easy Apply or employer ATS submit command is run. LinkedIn remains
> read-only for discovery and contact evidence everywhere else (no scraping,
> connecting, messaging, posting, or broad platform automation).

Operationally, “algorithm likely employed” means an evidence-backed
`screening_interface_profile`: observed ATS/provider host, observed form fields and file
constraints, job-description conventions, bounded presentation inferences, confidence,
evidence references, limitations, and explicit unknowns. It does **not** mean knowledge
of proprietary ranking weights, knockout logic, recruiter workflow, or a hidden scoring
algorithm.

Each morning the candidate opens **one entry point** backed by one source-of-truth report
manifest. It exposes a small ranked set of real opportunities, every associated artifact,
every blocker, and every available decision. Every message to another human is
transmitted **by the candidate**. Every application is submitted only when the human gives
explicit permission for that exact opportunity and payload; this skill must never
autonomously apply.

## Architecture (2026-08-08 — see docs/PROJECT_KNOWLEDGE.md for current state)

```
cron (0 2 * * *) → deterministic nightly (reliable orchestration; keep)
  discovery  → SAM.gov + LinkedIn (read-only, human's own session) + Greenhouse/Ashby + brave-search
             + monitor-contacts relationship graph (direct + adjacent contacts, event co-presence)
  filter     → recency (2wk) · role-type · mandate relevance via /extract-entities vocabulary (not regex)
  per top-N  → validated Tau semantic inputs materialized in the nightly run
             → optional `/ask tau-dag` provider-live addenda only with explicit `--tau-semantic-provider`
  tailor     → claim-bound resume · live ATS form capture (human-gated submit)
  track      → PRIVATE repo grahama1970/opportunities (issue per opp, dedup, lifecycle labels)
               dual queues: track:employment · track:consulting (prospect queue)
  deliver    → /memory (morning_opportunities) + Buzz summary
  flywheel   → opportunity_labels accumulate → /classifier-lab trains learned relevance at N≥300
```

Ranking/evaluation rubric: **best-practices-opportunities** (evaluator scores against it,
reviewer reviews against it, ranker orders by it — no bespoke top-N). GitHub `/ticket`
(public agent-skills) is for the skill's own code defects only; opportunities are private.
Effects are human-gated: **no auto-apply, no auto-submit, no auto-send**.

`monitor-contacts` is a standard composition, not an optional side quest. Every
run should preserve direct contacts, adjacent ARCOS/formal-methods contacts,
company sponsors, Meetup co-presence, role moves, and project-win signals as
relationship evidence. These signals may become consulting/reconnect prospects
or attendance/watch decisions, but they are never outreach authority.

Relationship evidence is stored through `/memory` as recallable
`morning_opportunities` documents with graph-shaped node/edge payloads. Do not
write raw ArangoDB AQL or vector arrays from this skill; use Memory `/store` or
`/upsert` and query via `/recall`.

Relationship signals must carry channel guidance. Corporate email is often
blocked, filtered, or stale after a long gap, especially when a contact has moved
roles or organizations. Prefer a LinkedIn human handoff when available; an
authorized persona Gmail address may be listed only as a non-deceptive,
human-transmitted route. These channel hints do not authorize automated email,
LinkedIn messages, Meetup RSVP, or any external effect.

## The interactive report is the product

Not a byproduct. One report manifest and one human entry point per completed run cover:

| Section | Contents | Candidate action |
|---|---|---|
| Opportunities | ranked, ≤8, dossier, eligibility, fit, source evidence, why this candidate | keep / reject / defer |
| Tailored resume | claim-bound variant, artifacts, and presentation-only diff | accept / propose claim amendment |
| InMail | verbatim local handoff text, claim keys, roundtable state, human steps | candidate transmits |
| Gmail | verbatim text and, only after separate promotion, mailbox draft location | candidate transmits |
| ATS application | inspect/prefill/submit state, exact payload binding, blockers | authorize / withhold |
| Relationship signals | direct/adjacent monitor-contact graph, source provenance, event/company path, channel risk | reconnect / defer |
| Interview prep | source- and claim-bound talking points | read |
| Tau semantic addenda | provider addenda installed from validated Tau inputs, when explicitly run | read / ignore |
| Coverage and health | lanes searched, source receipts, feed failures, unknowns | inspect |

Every action-worthy staged artifact must have `visible_in_report: true`. The manifest
records action-worthy, visible, and hidden counts; `hidden_total` must be zero. Staging
without presenting is a silent queue and is a defect.

“Co-equal lanes” means each enabled lane is honestly inspected and visibly reported. It
does not require equal output or filler opportunities.

## Lanes

- **A — employment** (`employment_posting`): WNY hybrid/onsite preferred, credible
  remote acceptable. **Buffalo is a hard constraint. Relocation-required roles are
  rejected before ranking.**
- **B — federal/defense** (`federal_notice`): SAM.gov Sources Sought/RFI and bounded,
  source-backed subcontract signals.
- **C — commercial contract** (`commercial_signal`) for grahamaco: document extraction,
  agent pipelines, agentic integration, and applied R&D. Usually there is no apply
  button; find and source the need before proposing work.
- **Relationship/reconnect signals** (`relationship_signal`, report-visible metadata):
  direct contacts, adjacent ARCOS/formal-methods contacts, event co-presence, company
  sponsors, role moves, funding/contract wins, and source-backed contact paths from
  `monitor-contacts`. These are standard consulting and networking signals attached to
  lanes A/B/C, not a fourth application lane.

Federal notices and commercial signals are not forced into an employment-posting schema.
Relationship signals are not forced into employment, federal, or commercial schemas; they
remain local human-decision records and Memory recall graph documents.

## Discovery: research first, never board enumeration

Enumerate-and-filter is a spray architecture and is forbidden as the primary strategy.
Maintain a reviewed target-account registry, identify which employers or clients are
worth inspecting, and read their primary sources.

Initial official employment discovery interfaces:

```text
greenhouse  boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
lever       api.lever.co/v0/postings/{slug}?mode=json
ashby       api.ashbyhq.com/posting-api/job-board/{slug}
```

These can establish published job content and the employer-hosted apply URL. They do
**not** establish candidate-side submission authority. Open-web or aggregator results
may locate a primary source, but cannot by themselves admit a shortlisted opportunity.

LinkedIn is one source, not the product. `ops-linkedin` may contribute explicitly
authorized, read-only evidence from a human-supplied LinkedIn Jobs/opportunity tab. Saved,
exported, pasted, screenshot, and `ops-linkedin` capture artifacts are ingested as local
evidence, then the workflow leaves the platform. The monitor still ranks across all
enabled lanes and must not become LinkedIn-only.

## API break must fall back to the website (unignorable)

When any source's API path fails — non-2xx, `FEED_DOWN`, `AUTH_FAILED`,
`INVALID_RESPONSE` — the skill MUST fall back to the source website via
read-only browser capture. A bare API-failure receipt is a DEFECT, never an
acceptable answer (Graham, 2026-08-06). `config/required_sources.json` flags each
`api_failure_requires_browser` source with its `website_fallback`, and
`pipeline._enforce_api_website_fallback` FAILS the live run with
`API_BREAK_REQUIRES_WEBSITE` when such a source reports an API failure and has no
companion `*_website` / human-supplied browser-capture receipt. Example: SAM.gov's
API returns 404, so the run is only valid with a `--federal-evidence` website
capture. This is enforced in code and covered by tests.

## Mandatory sources are enforced in code, not prose

Discovery is not a suggestion. `config/required_sources.json` lists the sources
that MUST be attempted on every live run, and `pipeline._enforce_required_sources`
(called from `run_stage0` for live runs, covered by
`tests/test_required_sources.py`) FAILS the run with `REQUIRED_SOURCE_NOT_SEARCHED`
when a mandated source is absent or reports `NOT_SEARCHED`. A run cannot claim
success while silently skipping a source.

Mandated sources: LinkedIn top-applicant (human-supplied read-only capture /
`--linkedin-evidence`; AUTH_REQUIRED when none, never a fake MATCHES), Indeed and
hiddenjobs (read-only browser capture — the only legitimate channel), Greenhouse
and Ashby (registry APIs), SAM.gov and DARPA (federal), and mandatory
client-services research (live brave-search over the candidate mandates). An
honest FEED_DOWN/AUTH_REQUIRED receipt is allowed; absence or NOT_SEARCHED is a
defect that stops the run. The nightly transaction inherits this gate — it is the
same `run` path.

## Source and feed truth

Each source attempt writes a receipt. Closed run-result vocabulary:

```text
MATCHES
NO_MATCHES
FEED_DOWN
AUTH_REQUIRED
AUTH_FAILED
RATE_LIMITED
POLICY_BLOCKED
STALE_DATA
INVALID_REQUEST
INVALID_RESPONSE
NOT_SEARCHED
```

A feed failure must never render as no opportunities. Source health is run-specific
evidence, not permanent prose. `NOT_SEARCHED` is distinct from `NO_MATCHES`.

## Eligibility before ranking

Every candidate first receives a deterministic eligibility result. Ranking cannot
rescue a rejected or human-review item. Required geographic order, all else equal:

```text
WNY hybrid > WNY onsite > credible remote
```

Relocation-required, source-invalid, stale, duplicate/already-applied, or explicitly
ineligible opportunities are rejected before scoring. Ambiguous location, clearance,
citizenship/work-authorization, salary, and other human-attested facts remain `UNKNOWN`
or `human_required`; a model cannot infer an attestation.

A promoted morning report with zero shortlisted opportunities is a failed monitor result.
Never relax threshold, geography, or eligibility policy to manufacture volume; fix source
coverage, evidence capture, or ranking so the report surfaces real opportunities.

## Claim-bound resume tailoring

Tailoring compiles a presentation from exactly one approved career-profile/claim
snapshot. It selects, orders, labels, and renders approved claims; it never mints a
factual assertion.

May change per opportunity:

- section order and headers;
- approved claim selection and bullet ordering;
- approved aliases and keyword surface;
- a clearly labeled target-role summary;
- ATS-safe layout and file format.

May never change:

- employers or historical employment titles;
- dates, clients, technologies, credentials, metrics, or outcomes;
- clearance, citizenship, work authorization, salary, or self-identification facts;
- any assertion not bound to an approved `claim_key` and wording variant.

Target-role language may appear in a clearly labeled target/summary field. It may not
replace an historical employment title. Every variant carries a claim snapshot digest,
claim keys, a semantic presentation diff, and explicit prohibited-delta validation.
Claim amendment creates a human-review proposal; it does not mutate the canonical ledger.

## Canonical resume and render handoff

The public canonical resume presentation in this repository is:

```text
RESUME.md
docs/resume/graham-anderson-resume.pdf
docs/resume/graham-anderson-resume.docx
```

`RESUME.md` is the human-edited baseline presentation. The PDF and DOCX are generated by
`.github/workflows/resume-pdf.yml` on pushes to `main`, or manually with:

```bash
uv run --with markdown-pdf==1.13.2 python scripts/build_markdown_pdf.py \
  RESUME.md \
  docs/resume/graham-anderson-resume.pdf \
  --title "Graham Anderson Resume" \
  --author "Graham Anderson"

uv run --with python-docx python scripts/build_resume_docx.py \
  RESUME.md \
  docs/resume/graham-anderson-resume.docx \
  --omit-section "DEEPER DETAIL"
```

That Markdown file is a presentation baseline, not the fact ledger. The canonical fact
authority remains the approved `career_profile` claim snapshot. A per-opportunity variant
must start from approved claims, bind every factual assertion to `claim_key` values,
produce the requested ATS-safe formats, emit a semantic diff against the canonical
presentation, and appear in the morning report before use. The public workflow renders
only the public canonical resume; the tailoring runtime owns per-opportunity rendering
after claim validation passes.

## Public website interaction gate — no exceptions

`grahama.co` and `grahama.co/resume` are opportunity-facing artifacts. Any
morning report, targeted resume handoff, LinkedIn profile handoff, or outreach
packet that relies on the public site must require a fresh `monitor-website`
interaction receipt from `$test-interactions` discovery plus replay.

Use the executable gate:

```bash
./run.sh website-gate --output-dir <dir> --json
```

This delegates to `monitor-website interaction-check` for:

- `https://grahama.co/`
- `https://grahama.co/resume`

The gate is required before committing or pushing UI-visible grahama.co changes
or using those public surfaces as current opportunity evidence. A stale
screenshot, stale CDP marker, DOM-only grep, or successful static build is not a
substitute. This gate does not authorize LinkedIn mutation, ATS submit, email
send, or Calendly booking effects.

## Intended command surface

The command list is the target contract. Current implementation status is authoritative
only in `./run.sh status --json` and `docs/PROJECT_KNOWLEDGE.md`.

```bash
./run.sh run --out <run-root>                 # one resumable nightly transaction
./run.sh sweep --lane A,B,C --out <dir>       # read-only discovery receipts
./run.sh rank --input <run> --limit 8          # eligibility first, then score
./run.sh tailor --posting <key> --out <dir>    # claim-bound resume artifacts
./run.sh report --input <manifest> --out <dir> # validate and render one report
./run.sh serve --report <run-dir>              # loopback decision entry point
./run.sh buzz-summary --run <run-dir> ...      # Buzz-ready report summary via ops-buzz
./run.sh buzz-review --run <run-dir> ...       # dry-run Buzz agent review request
./run.sh tau-semantic-prepare --run <run-dir> --out <dir> --top-n 3
./run.sh tau-semantic-provider-eval --input <json> --out <dir> --execute
./run.sh tau-semantic-install --run <run-dir> --provider-receipt <json>
./run.sh decision ...                          # append-only human decision event
./run.sh replay --run <run-id>                 # rebuild projection from events
./run.sh apply --posting <key>                 # separately gated ATS effect only
./run.sh status --json                         # readiness, stage, feeds, blockers
./run.sh verify --out <dir>                    # machine-readable verification receipt
./run.sh website-gate --output-dir <dir>       # live grahama.co + /resume test-interactions gate
./run.sh schedule --cron "0 2 * * *"           # register the full run, then read back
./sanity.sh                                    # deterministic behavioral gates
```

Unsupported commands must fail non-zero with an explicit `NOT_IMPLEMENTED`; a
success-looking placeholder is forbidden.

## Capability authority and human authorization

Current stage: **`STAGE_0_RESEARCH_ONLY`**.

| Capability | Stage 0 authority |
|---|---|
| Read approved public sources | allowed when implemented |
| Write local source/dossier artifacts | allowed |
| Rank eligible opportunities | allowed |
| Compile local claim-bound resume variants | allowed |
| Render local outreach text in the report | allowed, not sendable |
| Create Gmail mailbox draft | blocked pending separate capability promotion |
| Send Gmail | permanently forbidden to this skill |
| Prepare LinkedIn human handoff as ready | blocked pending separate promotion |
| Access or automate LinkedIn | permanently forbidden |
| Inspect ATS form | blocked pending site/provider promotion |
| Prefill ATS form | blocked pending separate promotion |
| Submit ATS form | blocked pending site/provider promotion and exact human authorization |
| Materialize Tau semantic inputs | allowed; local deterministic artifact only |
| Run provider-live Tau semantic addenda | separately gated by explicit `--tau-semantic-provider`; no external site effects |

Nightly runs materialize validated Tau semantic inputs under
`<run>/tau-semantic/` by default. This is local preparation evidence only:
`provider_live=false`, `external_effects=false`, and it does not browse, message,
apply, RSVP, or mutate the report by itself. Provider-live addenda require the
explicit `--tau-semantic-provider` flag and are admitted to the report only after
closed-schema parse plus `tau-semantic-install`. Provider addenda never authorize
ATS submit, Gmail send, LinkedIn action, Meetup RSVP, or claim mutation.

Capability promotion is explicit, capability-specific, scoped, receipt-bearing,
revocable, and never granted by elapsed time, exit zero, agent agreement, or prior
success. It does not authorize future unknown application payloads.

Every ATS submission additionally requires a per-application human authorization bound
to the exact posting, form schema, resume, attachments, answer set, policy, and payload
digest. Any change invalidates authorization. Permission for one opportunity never
authorizes any other application, outreach, platform action, retry, or future payload.

External ATS effects use:

```text
PREPARED -> HUMAN_AUTHORIZED -> COMMITTING -> COMMITTED | BLOCKED | INDETERMINATE
```

`INDETERMINATE` blocks automatic retry until reconciliation proves whether the effect
occurred.

## Who transmits

**The human. Always.** Applications are human-submitted only after explicit
per-opportunity permission. Gmail is draft-only after a separate promotion; Gmail send,
schedule-send, and forwarding are forbidden. LinkedIn output is a local human handoff
packet; this skill never logs in, drives the platform, posts, comments, connects, or
messages.

Every proposed outbound message requires a completed `/ask` roundtable under
`best-practices-roundtable`: concurrent topology, one immutable goal, at least two PASS
seats, attributed synthesis and dissent, no more than three rounds, and verdict
`SEND_AS_IS` or `SEND_WITH_REVISIONS`.

## Never auto-answer

EEO, veteran, disability, gender/race/ethnicity self-identification, clearance,
citizenship/work authorization, salary, legal, background/criminal disclosures,
ambiguous choice fields, and **every free-text field** are `human_required`. Anything
without an exact approved answer-bank hit is also `human_required`.

## Quality and audit counts

Caps: eight shortlisted opportunities, three applications per run, five per week.
Application, resume, board, and candidate counts may exist as audit/reconciliation data,
but are forbidden as optimization or success metrics. Success is a defensible small set
with source, eligibility, claim, and decision evidence.

## Scheduler registration

Register one full-run transaction only after deterministic and live Stage 0 gates pass.
Budget is enforced and receipted by `monitor-opportunities`; the scheduler does not claim
a budget capability it lacks.

```bash
skills/scheduler/run.sh register \
  --name monitor-opportunities-nightly \
  --cron "0 2 * * *" \
  --command "/absolute/path/to/skills/monitor-opportunities/run.sh run" \
  --workdir "/absolute/path/to/agent-skills" \
  --description "Nightly Stage 0 opportunity report"

skills/scheduler/run.sh list
```

Registration success is not proof until name, command, working directory, cron, and
enabled state are read back exactly.

Scheduler failure self-repair may emit an operational notification through
`ops-discord`, but only when explicitly enabled:

```bash
export MONITOR_OPPORTUNITIES_SELF_REPAIR_NOTIFY=1
export MONITOR_OPPORTUNITIES_SELF_REPAIR_WEBHOOK=slack
```

`MONITOR_OPPORTUNITIES_SELF_REPAIR_NOTIFY_DRY_RUN=1` resolves the webhook and
writes the notification receipt without posting. Notification is not an outreach,
LinkedIn, ATS, Gmail, Meetup, or application effect; it only tells Graham that a
required nightly step entered the repair branch. The scheduler receipt must still
record whether notification was `DISABLED`, `DRY_RUN`, `SENT`, `FAILED`, or
`SKIPPED`.

## Runtime self-improvement boundary

The substantial runtime may record feed failures, parser regressions, false positives,
ranking errors, and proposed improvements. It may not silently change the immutable goal,
Buffalo geography, capability authority, target registry, source allowlist, claim facts,
human attestations, ranking thresholds, caps, or external-effect policy. Such changes
become maintainer tickets or human-reviewed versioned configuration.

## References

- `references/report-format.md` — source-of-truth morning report and visibility invariant
- `references/tailoring-contract.md` — claim authority and permitted presentation deltas
- `references/safety-stage-contract.md` — capability promotion, human authorization, effects
- `references/source-integrity-contract.md` — research-first sources and feed truth
- `schemas/report.schema.json` — Stage 0 report schema
- `fixtures/reports/stage0_mixed_lanes.json` — expected mixed-lane Stage 0 product fixture
- `docs/PROJECT_KNOWLEDGE.md` — current implementation state, decisions, and next slices
