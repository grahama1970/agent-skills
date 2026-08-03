---
name: monitor-opportunities
description: >
  Nightly opportunity monitor. Sweeps ATS-native job APIs and federal feeds, ranks a small
  set of high-fit opportunities across employment, federal subcontract and commercial
  contract lanes, generates a per-opportunity resume variant tuned to the screening stack
  that employer actually uses, and emits ONE interactive morning report covering LinkedIn
  InMail drafts, Gmail drafts, auto-apply status and resume updates. Use when the user asks
  for today's opportunities, the morning opportunity report, to tailor a resume for a
  posting, to check what needs sending, or to run or schedule the nightly opportunity
  sweep.
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
  short-description: Nightly opportunity sweep with algorithm-aware resume tailoring and one interactive report
  author: Graham
  version: "0.1.0"
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
  - scheduler
  - task-monitor
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-arangodb
  - best-practices-roundtable
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

Each morning the candidate opens **one** artifact, sees a small ranked set of real
opportunities across every lane, and can act on all of them from that one place. Every
message to a human is transmitted **by the human**.

## The interactive report is the product

Not a byproduct. One artifact per night, covering all four action types together:

| Section | Contents | Candidate action |
|---|---|---|
| Opportunities | ranked, ≤8, each with dossier, fit score and **why this candidate** | keep / reject / defer |
| Tailored resume | the variant generated for that posting + a diff against canonical | accept / amend a claim |
| InMail drafts | full verbatim text, claim keys, roundtable verdict, send steps | **candidate sends** |
| Gmail drafts | full verbatim text, draft location in the mailbox, send steps | **candidate sends** |
| Auto-apply | ATS form status per application, or why it is staged | authorize / withhold |
| Interview prep | JD-derived talking points bound to ledger claims | read |

Every candidate decision writes back to the ledger. Amending a claim regenerates the
affected resume variant. **Staging without presenting is a silent queue and is a defect.**

## Lanes (co-equal)

- **A — employment**: WNY hybrid/onsite preferred, credible remote acceptable.
  **Buffalo is a hard constraint — relocation roles are rejected, never shortlisted.**
- **B — federal/defense**: SAM.gov Sources Sought / RFI, SBIR awardees needing
  subcontractors.
- **C — commercial contract** for grahamaco: document extraction, agent pipelines,
  agentic integration, applied R&D. Usually has no "apply" button — find the NEED, propose.

## Discovery: research-first, never board enumeration

Enumerate-and-filter is a spray architecture and is **forbidden as a primary strategy**.
Identify which employers are worth targeting, then read only their boards.

Verified working (2026-08-02):

```
greenhouse  boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
lever       api.lever.co/v0/postings/{slug}?mode=json
ashby       api.ashbyhq.com/posting-api/job-board/{slug}
```

These return the full JD **and the employer's own apply URL**, so discovery never requires
scraping an aggregator. Aggregator/open-web search produces noise; ATS APIs produce facts.

**LinkedIn is never automated** (UA §8.2). Human-saved HTML only, then leave the platform.

## Algorithm-aware resume tailoring

Infer the screening stack from evidence available **before** applying — the ATS host on
the apply URL, form field shapes, JD phrasing conventions — and record the inference with
its basis. Then tailor **presentation only**:

**May change per opportunity**: section order, section headers, keyword surface and
density, title mirroring, bullet ordering, file format (single-column `.docx` for Workday),
which approved claims are surfaced or omitted.

**May never change**: facts, dates, employers, titles, metrics, or any assertion not bound
to a `claim_key` in the canonical `career_profile` ledger. Tailoring **reorders and
selects approved claims; it never mints one.**

Every variant is validated before use: schema-valid, every assertion resolves to a claim
key, and a diff against canonical shows only presentation deltas. A variant that adds a
factual assertion is a defect, not a variant.

## Canonical resume and PDF handoff

The public canonical resume artifact in this repository is:

```text
RESUME.md
docs/resume/graham-anderson-resume.pdf
```

`RESUME.md` is the human-edited baseline presentation. The PDF is a generated
artifact produced by `.github/workflows/resume-pdf.yml` on pushes to `main`, or
manually with:

```bash
uv run --with markdown-pdf==1.13.2 python scripts/build_markdown_pdf.py \
  RESUME.md \
  docs/resume/graham-anderson-resume.pdf \
  --title "Graham Anderson Resume" \
  --author "Graham Anderson"
```

`monitor-opportunities` must treat that Markdown file as the baseline resume
presentation, not as the fact ledger. The canonical fact source remains the
`career_profile` claim ledger. A tailored resume variant is valid only when it:

- starts from approved `career_profile` claims;
- selects, orders and labels those claims for one posting and inferred ATS stack;
- writes a per-posting Markdown variant and generated PDF;
- emits a diff against `RESUME.md`;
- proves every factual assertion in the variant resolves to a `claim_key`;
- appears in the interactive report before it is used anywhere.

The GitHub Actions PDF workflow renders only the public canonical resume. The
`./run.sh tailor --posting <key>` implementation is responsible for rendering
per-opportunity PDFs by calling `scripts/build_markdown_pdf.py` directly after
claim-binding validation passes.

## Commands

```bash
./run.sh sweep --lane A,B,C          # discovery only; writes job_postings
./run.sh rank --limit 8              # score + dossiers; no outbound
./run.sh tailor --posting <key>      # claim-bound Markdown/PDF variant + diff
./run.sh report                      # build the interactive morning report
./run.sh apply --posting <key>       # ATS form only; never email or LinkedIn
./run.sh status                      # readiness, stage, feed health
./run.sh schedule                    # register the nightly cron via /scheduler
./sanity.sh                          # behavioral gates
```

Register the nightly run:

```bash
/scheduler add monitor-opportunities --cron "0 2 * * *" --budget 10
```

## Stage gate — nothing is sendable until proven

Current stage: **`STAGE_0_RESEARCH_ONLY`**. In stage 0 the skill may sweep, rank, write
dossiers, tailor resumes and build the report; it may **not** create a Gmail draft in the
mailbox, mark an outbound LinkedIn packet ready, or submit any application. The report
labels these **"WOULD PRESENT (STAGE_0 — not sendable)"**.

Stage advances only on an explicit human promotion decision — never automatically, never
by elapsed time, and never because a run exited zero.

## Who transmits

**The human. Always.** Gmail is `--mode draft` only; `--mode send` is forbidden and
`plan commit` creates a draft, it does not transmit. LinkedIn has no automation at all.
Autonomous submission applies **only** to employer-hosted ATS application forms, and never
to email, InMail, connection notes, comments or posts.

Every outbound message additionally requires a completed `/ask` roundtable per
`best-practices-roundtable`: concurrent topology, immutable goal, ≥2 PASS seats, attributed
synthesis, 3-round cap, verdict `SEND_AS_IS` or `SEND_WITH_REVISIONS`.

## Never auto-answer

EEO / veteran / disability self-ID, clearance, work authorization, salary, legal,
background or criminal disclosures, ambiguous drop-downs, and **any free-text field** —
plus anything lacking an exact hit in the attested answer bank. Unknown form fields
default to `human_required`.

## Quality over volume

Caps: 8 shortlisted, 3 applications per run, 5 per week. `applications_sent`,
`resumes_submitted` and `boards_enumerated` are **forbidden metrics**. Success is *the
number of high-fit opportunities with defensible dossiers*.

**An empty night is a valid outcome.** If nothing clears the bar, say so and exit 0. Never
lower the threshold, widen the geography, or add filler to make a night look productive.

## Feed health must be loud

A dead feed must never render as "no opportunities". `status` reports per-feed health, and
the report states which lanes were actually searched. As of 2026-08-02 the **SAM.gov
Opportunities API returns HTTP 404 with zero bytes from its own `istio-envoy` gateway** on
every documented path and both auth styles, so **lane B has no working feed** and must be
reported `FEED_DOWN`, not empty.

## References

- `references/tailoring-contract.md` — what a variant may and may not change
- `references/report-format.md` — the interactive report contract
- `docs/PROJECT_KNOWLEDGE.md` — current state, gaps, defect history
- `fixtures/agentic_eval.json` — positive, negative, adversarial cases
