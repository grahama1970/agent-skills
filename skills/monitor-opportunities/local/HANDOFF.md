# Handoff Report: monitor-opportunities

**Timestamp**: 2026-08-03T12:20Z
**Active Agent**: Claude Opus 5 (1M context), session 262c2c5e
**Target**: `agent-skills/skills/monitor-opportunities` (branch `main`)

> Every state claim below was read back in the session that wrote this file. Claims
> that were NOT verified are labeled INFERENCE. Do not promote an INFERENCE to a
> fact without running the command named beside it.

---

## 0. Read this first — the skill does not exist yet

`find skills/monitor-opportunities -type f` returns **exactly one file: `SKILL.md`**
(plus this handoff). There is no `run.sh`, no Python package, no `sanity.sh`, no
fixtures, no references. **Every command documented in SKILL.md is unimplemented.**

`git status --porcelain skills/monitor-opportunities` → `?? skills/monitor-opportunities/`
and `git log -- skills/monitor-opportunities` is **empty**. The directory has never
been committed. Per the standing operator directive, an untracked file is lost work
waiting to happen — `sparta_metrics.py` was swept into `.cleanup/` exactly this way.
**Committing SKILL.md is the first action for the next agent, before any new code.**

SKILL.md is a *specification*, and a good one — treat it as the contract to build
against, not as a description of working software.

---

## 1. Project Overview

- **Ecosystem**: Python (per spec: Typer CLI, stdlib-only where copy-safe). Nothing
  built yet, so no `pyproject.toml` exists here.
- **Core purpose — the immutable goal, verbatim and registered**:

  > Daily top opportunities that are highly targeted, delivered in an interactive
  > report/interview, with auto-apply using a custom targeted resume given the
  > algorithm likely employed by the employer or client.

- **The interactive report IS the product**, not a byproduct. One artifact per night
  covering opportunities, tailored resume + diff, InMail drafts, Gmail drafts,
  auto-apply status, and interview prep. Staging without presenting is a defect.
- **Three co-equal lanes**: A employment (**Buffalo/WNY hybrid is a hard constraint —
  relocation roles are rejected, never shortlisted**; credible remote acceptable),
  B federal/defense subcontract (SAM.gov Sources Sought, SBIR awardees),
  C commercial contract for grahamaco (document extraction, agent pipelines, agentic
  integration, applied R&D — usually no apply button; find the need and propose).

**VERIFIED — the goal is registered in the goal-drift registry**
(`~/.local/state/agent-skills/goal-drift/goals/monitor-opportunities.json`):
`source: human_prompt`, registered `2026-08-03T00:07:57Z`, scoped to both
`agent-skills` and `resume` repos, with four acceptance criteria:

| key | text |
|---|---|
| `interactive_report` | daily interactive report covering InMail, Gmail, auto-apply and resume updates |
| `tailored_resume` | per-opportunity tailored resume variant bound to the claim ledger |
| `opportunity_discovery` | opportunities discovered across employment, federal and contract lanes |
| `auto_apply` | auto-apply on employer ATS forms with pre-submit gate |

Note: `goal_hash` in that record reads `None` — the hash is computed at handoff/tau
time, not stored at registration. If you expect a stored hash, that is a gap to close.

---

## 2. Current State (Doc–Code Alignment)

This is the whole of the drift, and it is total: **SKILL.md documents six commands;
zero exist.**

| Documented in SKILL.md | Implemented? |
|---|---|
| `./run.sh sweep --lane A,B,C` | **NO** |
| `./run.sh rank --limit 8` | **NO** |
| `./run.sh tailor --posting <key>` | **NO** |
| `./run.sh report` | **NO** |
| `./run.sh apply --posting <key>` | **NO** |
| `./run.sh status` | **NO** |
| `./run.sh schedule` | **NO** |
| `./sanity.sh` | **NO** |
| `references/tailoring-contract.md` | **NO** |
| `references/report-format.md` | **NO** |
| `docs/PROJECT_KNOWLEDGE.md` | **NO** |
| `fixtures/agentic_eval.json` | **NO** |

SKILL.md also instructs `/scheduler add monitor-opportunities --cron "0 2 * * *"`.
**VERIFIED NOT REGISTERED**: `scheduler run.sh list | grep -c monitor-opportunities`
→ `0`. There is no nightly run. The skill's own frontmatter declares
`runtime_self_improvement: substantial`, which per best-practices-skills requires
`./run.sh verify` + receipt + a maintainer ticket + an agent post-run section — none
of which exist. Expect validator rules RSI001–RSI004 to fail the moment it is linted.

---

## 3. What Is Working Well

Real, verified assets — mostly in the **`resume` repo**, not here. The next agent
should wire to these rather than rebuild them.

- **`resume/agents/opportunity-scout.yaml`** (63k, `main`, staged as `AM`) — the
  subagent contract. Lints PASS, `kind: curator` (required for memory-write
  endpoints). Contains the quality policy (8 shortlist / 3 per run / 5 per week;
  `applications_sent` is a **FORBIDDEN metric**), the `STAGE_0_RESEARCH_ONLY` maturity
  gate with 8 exit criteria, `who_transmits` (**THE HUMAN TRANSMITS**, `--mode draft`
  only), a 12-field presentation contract, the outbound roundtable requirement,
  contact routing, and mailbox mining policy.
- **`resume/src/resume/job_search/inmail-draft.schema.json`** (19k) —
  `grahamaco.inmail_draft.v1`, draft 2020-12, `additionalProperties: false`. Proven
  to reject: no claims, fit_score < 0.8, forbidden phrases, `APPROVED_FOR_SEND`
  without a reviewer, body > 1900 chars, missing roundtable, `DO_NOT_SEND` verdict,
  < 3 seats, < 2 passing seats, sequential topology, rounds > 3, and a synthesis
  missing `attributed_dissent`.
- **ATS-native discovery, verified reachable 2026-08-02** — returns the full JD *and
  the employer's own apply URL*, so discovery never needs an aggregator:
  - `boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true`
  - `api.lever.co/v0/postings/{slug}?mode=json`
  - `api.ashbyhq.com/posting-api/job-board/{slug}`
  - Workday CxS: `POST https://{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{SITE}/jobs`
    with `{"appliedFacets":{},"limit":20,"offset":0,"searchText":""}`.
    **422 ≠ 404** — a 422 means the endpoint routes but the tenant/site pair is wrong.
  - Tenant discovery: scrape `{employer}.com/careers`, regex
    `([a-z0-9-]+)\.(wd\d)\.myworkdayjobs\.com/([A-Za-z0-9_-]+)`.
  - ~4,700 postings were reachable across 8 ATS vendors via tenant discovery.
- **`resume/docs/roundtable-receipts/`** — stage-1 receipts from webgpt, webclaude,
  webgemini, webgrok, webkimi, plus the shared packet and derived slices. Staged, `main`.
- **`resume/src/resume/job_search/`** — resume/LinkedIn source of truth: `resume.json`,
  `resume-version.schema.json`, `linkedin-profile.schema.json`, ATS and recruiter
  resume variants, `BUFFALO_SOURCES.md`, `HUMAN_AGENT_FLOW.md`, `TASKS.md`.

---

## 4. What Is Currently Broken

- **The skill itself** — one spec file, zero implementation, never committed. §0.
- **No nightly run.** VERIFIED: zero scheduler jobs match `monitor-opportunities`.
  Nothing is happening automatically. The immutable goal says *daily*.
- **Lane B has no working feed.** As of 2026-08-02 the SAM.gov Opportunities API
  returns HTTP 404 with zero bytes from its own `istio-envoy` gateway on every
  documented path and both auth styles. Lane B must report `FEED_DOWN`, **never
  "no opportunities"** — a dead feed rendering as empty is the defect this skill
  exists to avoid.
- **`/gmail` OAuth is not authorized.** The Gmail skill landed as draft PR #1154; the
  mailbox-mining and Gmail-draft paths cannot run until a human authorizes OAuth.
  Agent cannot do this — it requires the human in the browser.
- **Human attestations missing**, and they block `auto_apply` entirely: clearance,
  phone, salary, work authorization, EEO/veteran/disability self-ID. Per spec these
  may **never** be auto-answered, and any field without an exact hit in the attested
  answer bank defaults to `human_required`.
- **goal-drift's last verdict on this project was `DRIFTED`** — 4 × `MISSING_EXPECTED`
  (including the interactive report and the tailored resume variant) plus 36 ×
  `UNGOALED_TICKET`. That verdict is correct and is the honest state of this skill.
- **`goal-drift` nightly job has never fired.** VERIFIED: scheduler shows
  `goal-drift │ 0 6 * * * │ enabled │ never`. Registered but never run, so no nightly
  drift report has ever been produced.

### Repository hygiene — read before you commit anything

**VERIFIED in `agent-skills` (branch `main`):**
- **360 staged files**, **462 unstaged modified**, **1,748 untracked entries**.
  Most of this is other lanes' work, not this project's.
- **`git log --oneline origin/main..HEAD` is NOT empty** — 10+ unpushed commits
  (`ask: …`, `best-practices-skills: …`, `Add Sparta Explorer README card`).

**Never run `git add -A` in this repo.** It previously staged 448 unrelated files and
~40 embedded git repositories. Stage only `skills/monitor-opportunities/` by explicit
path. The standing directive requires proving nothing is stranded before ending a turn
that touched a repo; that condition is currently **not met** in `agent-skills`, and the
next agent should confirm whether those unpushed commits belong to an active lane
before touching them.

**`resume` repo** is cleaner: branch `main`, `git log origin/main..HEAD` **empty**,
with staged additions (roundtable receipts, `LinkedIn-Update-2026-08.md`) and
`agents/opportunity-scout.yaml` staged-and-modified.

---

## 5. Next Steps

1. **Commit `SKILL.md`** by explicit path. It is untracked spec work and the single
   highest-value five-second action here.
   `git add skills/monitor-opportunities && git commit`
2. **Build `run.sh` + the Typer package + `sanity.sh`** against the spec. Follow
   `skills/goal-drift/` as the local reference implementation — it has the typed seam
   contracts, the behavioral gate suite, and the read-only AST gates already working.
3. **Implement `sweep` first, for lane C and lane A only**, using the three verified
   ATS endpoints. Research-first: identify which employers are worth targeting, then
   read only their boards. **Enumerate-and-filter is forbidden as a primary strategy.**
4. **Implement `status` early** — per-feed health, so lane B correctly reports
   `FEED_DOWN` from day one rather than silently reading as empty.
5. **Then `rank` → `tailor` → `report`.** The report is the product; do not defer it
   to last. Tailoring **reorders and selects approved claims and never mints one** —
   every assertion must resolve to a `claim_key` in the canonical `career_profile`
   ledger, and a variant that adds a factual assertion is a defect, not a variant.
6. **Register the nightly cron** (`0 2 * * *`) only after `sanity.sh` passes, and
   **read the registration back** — a scheduler success response is not proof.
7. **Leave `STAGE_0_RESEARCH_ONLY` in place.** Stage advances only on an explicit
   human promotion decision — never automatically, never by elapsed time, and never
   because a run exited zero.

---

## 6. Project Context for Success

### Key files

| Path | Role |
|---|---|
| `agent-skills/skills/monitor-opportunities/SKILL.md` | the contract to build against |
| `resume/agents/opportunity-scout.yaml` | subagent contract, quality policy, stage gate |
| `resume/src/resume/job_search/inmail-draft.schema.json` | outbound validation, proven rejections |
| `resume/src/resume/job_search/resume.json` | canonical claim ledger |
| `resume/docs/roundtable-receipts/` | stage-1 panel receipts |
| `agent-skills/skills/goal-drift/` | reference implementation for seams + gates |

### Non-negotiables — these are hard constraints, not preferences

- **The human transmits.** Always. Gmail is `--mode draft` only; `--mode send` is
  forbidden; `plan commit` creates a draft and does not transmit. Autonomous
  submission applies **only** to employer-hosted ATS forms — never to email, InMail,
  connection notes, comments, or posts.
- **LinkedIn is never automated** (UA §8.2). Human-saved HTML only, then leave the
  platform.
- **Every outbound message requires a completed `/ask` roundtable** per
  best-practices-roundtable: concurrent topology, shared packet with the immutable
  goal, ≥ 2 PASS seats, attributed synthesis, 3-round cap, verdict `SEND_AS_IS` or
  `SEND_WITH_REVISIONS`.
- **Quality over volume.** Caps: 8 shortlisted, 3 applications per run, 5 per week.
  `applications_sent`, `resumes_submitted` and `boards_enumerated` are **forbidden
  metrics**. An empty night is a valid outcome — say so and exit 0. Never lower the
  threshold, widen the geography, or add filler to make a night look productive.
- **Buffalo is a hard constraint.** Relocation roles are rejected, not shortlisted.
- **Writes go through the `/memory` skill**, never a direct ArangoDB client.
- **One branch — `main`.** No production/dev split until the project has earned it by
  being stable-reliable. Never enable branch protection on `main` here.
- **Never create a worktree.** The only valid work location is the primary checkout.

### Positioning — required to judge fit, and easy to get wrong

The candidate is **three co-equal pillars**, not a chronological ladder. Any resume
variant or InMail that presents pillars 1 and 2 as mere background is wrong:

1. **Creative composition** — commercial composer (Adidas, Pepsi, X-Games).
2. **Executive advertising/marketing** — Dentsu America LA interactive division
   (Disney, Toyota, Bandai, Cartoon Network, Scion); EP on the Webby-recognized
   *God of War: Ascension* for Sony; Director of Media Delivery (worldwide
   cross-platform CDN, DRM HD video for Nvidia, a 300,000+ concurrent-user stream
   with Intel/China Telecom).
3. **Deep technical R&D** — prime/lead researcher for CS Group on **DARPA ARCOS**,
   leading ACERT. Outcome: AI automation of complex Boeing engineering documentation
   into a queryable, accurate graph, across a 4-year project with collaborators
   including Honeywell, Lockheed Martin, MIT, GE Research and SRI. `pdf-oxide` is the
   next iteration of that work. The candidate **wrote code, presented, and project
   managed across the country with leading scientists** in the field.

**Pillars 1 and 2 were crucial to ARCOS's success, not background to it.** The
marketing pillar means coordinating multiple objectives and lanes of strategy for
highest-end clients — the Disney-scale coordination problem — which is the same skill
ARCOS required across the military-industrial collaborator set.

### Recent related changes (this session, outside this directory)

- `skills/goal-drift/SKILL.md` — corrected a **fabricated provenance claim**. An
  earlier version said the mechanism was "ported from" a `nicobailon/pi-subagents`
  watchdog citing specific files; **no watchdog exists in that repo and never has**
  (`git log --all --diff-filter=A -- '*watchdog*'` is empty; `grep -rn
  'everyNTools|stalemateRepeats'` → 0). The real prior art is one README line about a
  non-editing `oracle` agent. `sanity.sh` re-run after the edit: **PASS**.
  *If you cite prior art in this skill, verify it against the repo first.*
- `/ticket` amended so every issue AND PR must declare a `## Goal` line, fail-closed.
  Verified live. **Not yet done**: `sanity.sh` not re-run after that edit, SKILL.md
  does not document `--goal`, and `--goal` is not threaded through `fleet`/`triage`.
- Cleared a 2d15h-hung `ensure-surf-cli.sh`/`npm ci` that was blocking every browser
  handler. A stuck `npm ci` remains in uninterruptible `D` state (unkillable until its
  syscall returns or reboot) but is no longer in the path; `surf run.sh --help` exits 0.
- A webgpt roundtable on live goal-drift watch mode returned and was harvested. Its
  findings that bear on this skill: `asyncRewake` is **VERIFIED present in Claude Code
  2.1.220** (7 occurrences; the binary's own doc string confirms exit-code-2 → text
  appended to a system-reminder shown to the model), and a same-UID watcher is **not**
  a real authority boundary. Full text in the run's
  `node-artifacts/handler-webgpt/response.md`.
