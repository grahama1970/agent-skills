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
  - brave-search
  - mailbox-mining
  - ops-linkedin
  - gmail
  - ask
  - scheduler
  - task-monitor
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-arangodb
  - best-practices-roundtable
  - best-practices-security
taxonomy:
  - operations
  - retrieval
  - precision
  - human-in-the-loop
  - composition
---

# monitor-opportunities

## Immutable goal

> **Daily top opportunities that are highly targeted, delivered in an interactive
> report/interview, with auto-apply using a custom targeted resume given the algorithm
> likely employed by the employer or client.**

Operationally, “algorithm likely employed” means an evidence-backed
`screening_interface_profile`: observed ATS/provider host, observed form fields and file
constraints, job-description conventions, bounded presentation inferences, confidence,
evidence references, limitations, and explicit unknowns. It does **not** mean knowledge
of proprietary ranking weights, knockout logic, recruiter workflow, or a hidden scoring
algorithm.

Each morning the candidate opens **one entry point** backed by one source-of-truth report
manifest. It exposes a small ranked set of real opportunities, every associated artifact,
every blocker, and every available decision. Every message to another human is
transmitted **by the candidate**.

## The interactive report is the product

Not a byproduct. One report manifest and one human entry point per completed run cover:

| Section | Contents | Candidate action |
|---|---|---|
| Opportunities | ranked, ≤8, dossier, eligibility, fit, source evidence, why this candidate | keep / reject / defer |
| Tailored resume | claim-bound variant, artifacts, and presentation-only diff | accept / propose claim amendment |
| InMail | verbatim local handoff text, claim keys, roundtable state, human steps | candidate transmits |
| Gmail | verbatim text and, only after separate promotion, mailbox draft location | candidate transmits |
| ATS application | inspect/prefill/submit state, exact payload binding, blockers | authorize / withhold |
| Interview prep | source- and claim-bound talking points | read |
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

Federal notices and commercial signals are not forced into an employment-posting schema.

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

LinkedIn is never automated. Only human-saved or human-supplied content may be used, then
the workflow leaves the platform.

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

An empty shortlist is a valid successful result. Never relax threshold, geography, or
eligibility policy to manufacture volume.

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
```

`RESUME.md` is the human-edited baseline presentation. The PDF is generated by
`.github/workflows/resume-pdf.yml` on pushes to `main`, or manually with:

```bash
uv run --with markdown-pdf==1.13.2 python scripts/build_markdown_pdf.py \
  RESUME.md \
  docs/resume/graham-anderson-resume.pdf \
  --title "Graham Anderson Resume" \
  --author "Graham Anderson"
```

That Markdown file is a presentation baseline, not the fact ledger. The canonical fact
authority remains the approved `career_profile` claim snapshot. A per-opportunity variant
must start from approved claims, bind every factual assertion to `claim_key` values,
produce the requested ATS-safe formats, emit a semantic diff against the canonical
presentation, and appear in the morning report before use. The public workflow renders
only the public canonical resume; the tailoring runtime owns per-opportunity rendering
after claim validation passes.

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
./run.sh decision ...                          # append-only human decision event
./run.sh replay --run <run-id>                 # rebuild projection from events
./run.sh apply --posting <key>                 # separately gated ATS effect only
./run.sh status --json                         # readiness, stage, feeds, blockers
./run.sh verify --out <dir>                    # machine-readable verification receipt
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

Capability promotion is explicit, capability-specific, scoped, receipt-bearing,
revocable, and never granted by elapsed time, exit zero, agent agreement, or prior
success. It does not authorize future unknown application payloads.

Every ATS submission additionally requires a per-application human authorization bound
to the exact posting, form schema, resume, attachments, answer set, policy, and payload
digest. Any change invalidates authorization.

External ATS effects use:

```text
PREPARED -> HUMAN_AUTHORIZED -> COMMITTING -> COMMITTED | BLOCKED | INDETERMINATE
```

`INDETERMINATE` blocks automatic retry until reconciliation proves whether the effect
occurred.

## Who transmits

**The human. Always.** Gmail is draft-only after a separate promotion; Gmail send,
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
