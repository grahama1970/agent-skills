---
name: review-page
description: >
  Build a fail-closed, WebGPT-centered page review package for product/UI pages.
  Use when a project agent needs to review a page, dashboard, chat surface,
  evidence workspace, workflow screen, or Explorer page with screenshots,
  deterministic interactions, external benchmark research, persona-specific
  judgment, and human-readable HTML reporting. This skill prevents page-review
  theater: no screenshot-less pass, no cached-state-as-truth, no persona
  subagent timeout loops as final adjudication, and no hidden degraded states.
triggers:
  - review page
  - page review
  - review-page
  - WebGPT page review
  - Explorer page review
  - screenshot review
  - UI evidence review
  - dashboard review
  - page contract review
  - visual workflow review
provides:
  - page-review-packet
  - webgpt-page-review
  - html-human-report
  - screenshot-evidence-gallery
  - interaction-manifest
  - benchmark-research-brief
taxonomy:
  - review
  - design
  - ux
  - evidence
  - validation
composes:
  - test-interactions

consumers:
  - ask  # $ask webgpt owns WebGPT adjudication
disciplines:
  - evaluation-quality
  - browser-automation
  - ui-design-engineering
---

# review-page

Use this skill to produce a repeatable, fail-closed review workflow for one UI page at a time.

The output is three artifacts:

1. `REVIEW_PACKET.md` — WebGPT/model input packet.
2. `report.html` — human-facing report with inline screenshot gallery.
3. `review.json` — machine-readable verdict, blockers, and code-runner actions.

## North star

Every page review must justify the page against a **real-world cybersecurity task**
and minimize **dashboard theater**.

Before visual adjudication, the review must answer:

1. **Cyber task** — What concrete security job does an operator/analyst perform on
   this page, with what primary object, under what failure mode?
2. **Why this tab exists** — Why is this not redundant with Chat, Coverage, or
   another Explorer page?
3. **Comparator landscape** — What do adjacent products/tools do for that task,
   from the **lead persona's** vantage (usually captured once in a page contract
   from `$dogpile`; not re-run every review round)?
4. **Theater risks** — What would look healthy but mislead (aggregate greens,
   hidden caveats, unproven ready/approved labels, matrix color without evidence)?

Research informs obligations; it does **not** prove the SPARTA UI is correct.
Deterministic `$test-interactions` + attached screenshots + `$ask webgpt`
adjudication prove implementation.

Hand completed page reviews to `$create-report` with explicit non-claims for
missing persona receipts, degraded dogpile providers, or unproven predicates.

## Research vs review iteration

These are **separate loops**:

| Phase | Tool | Frequency |
|---|---|---|
| **Cyber task + comparator research** | `$dogpile` (explicit only) | Usually **once per page family**; rerun only when stale, missing, or scope changed |
| **Implementation proof + adjudication** | `review-page` + `$test-interactions` + `$ask webgpt` | **Many rounds** until PASS or blocked |

**Default review iteration** (no new dogpile):

```text
fix UI/code → run-ti → build/package → $ask webgpt → read CODE_RUNNER_ACTIONS → repeat
```

Do **not** invoke `$dogpile` inside every `review-page` or WebGPT round. The packet
should **reuse** an existing `page-contracts/*.md` or `research/<page-id>.md` that
already distills dogpile output (cyber task, comparators, theater risks).

Run `$dogpile` only when a human or plan explicitly requests it — e.g. first-time
page justification, new page family, competitor landscape refresh, or contract dispute.

This skill deliberately separates:

- deterministic UI proof from reviewer judgment
- external web research from project evidence
- screenshots from text summaries
- human product decisions from agent-fixable defects

## Hard rule

Review **one page per run**.

Do not batch multiple pages into one WebGPT review. Do not accept screenshot-less page pass. Do not treat page-contract prose, cached API payloads, subagent persona text, or green dashboard labels as visual proof.

## Required inputs

A page review run needs:

```text
review-page/
  REVIEW_REQUEST.md
  evidence/
    page-contract.json
    test-interactions-results.json
    api-or-monitor-state.json
    derived-page-state.json              # if applicable
  screenshots/
    01-full-page.png
    02-primary-workflow.png
    03-evidence-state.png
    04-after-refresh.png                 # if persistence matters
    05-after-navigation.png              # if navigation persistence matters
```

Minimum evidence:

| Evidence | Required? | Notes |
|---|---:|---|
| Current page screenshot | yes | Full visible page, not generic browser proof |
| Primary workflow screenshot | yes | State after the main interaction |
| Deterministic interaction results | yes | `test-interactions` or equivalent |
| Page contract/state JSON | yes | Current, not stale/cached unless labeled |
| Page contract (cyber task + comparators) | yes for product/design review | Reuse distilled contract; fresh `$dogpile` only when explicitly requested |
| Persona lens | yes | One lead persona per page |
| Failure/degraded screenshot | yes if applicable | If missing/degraded state exists, it must be visible |
| Refresh/navigation proof | yes if required by page contract | Required for chat/evidence/citation state |

## Workflow

### 1. Freeze the page scope

Write `REVIEW_REQUEST.md` with:

```markdown
# Page Review Request

Page: <page name>
Route: <route/hash>
Lead persona: <persona>

## Cyber task justification
- Operator:
- Trigger (when opened):
- Primary object:
- Authoritative source:
- Valid actions:
- Failure/degraded mode that must be visible:

## Comparator / theater audit
- Named comparators ($dogpile):
- Dashboard-theater risks for this task:
- What this page must NOT imply:

Review focus: task fit, evidence clarity, comparator alignment, failure visibility
Known non-claims:
- <what this page review does not prove>
Required verdict enum:
- page_verdict: pass | degraded | fail | insufficient_evidence
- overall_verdict: PASS | NEEDS_CHANGES | BLOCKED | HUMAN_REQUIRED
```

### 2. Run deterministic interactions

Use real `[data-qid]` selectors only. The manifest must prove the page’s actual workflow, not just that DOM elements exist.

For each interaction, capture:

- qid
- action
- expected result
- actual result
- verdict
- screenshot label
- caveat or failure

### 3. Capture screenshots

Use individual screenshots as proof. Also create an HTML grid/contact sheet in `report.html`.

Do not merge all screenshots into one giant image as the only visual proof. One contact-sheet overview is useful, but the review must keep individual images.

Recommended screenshot count:

| Page complexity | Screenshot count |
|---|---:|
| Simple status page | 4–6 |
| Normal workflow page | 6–10 |
| Complex table/graph/chat page | 10–16 |
| More than 16 states | split into another review round |

### 4. Attach page contract (reuse research; `$dogpile` only if specified)

**Default:** reuse an existing page contract. Do **not** run `$dogpile` automatically.

The packet must include cyber-task justification and comparator/theater obligations from:

- `page-contracts/<page-family>.md`, or
- `research/<page-id>.md`

Those files are normally produced **once** from an explicit `$dogpile` run (see
optional step 4b). On later review rounds, only refresh TI captures, screenshots,
and WebGPT adjudication.

**Optional 4b — run `$dogpile` only when explicitly requested**

Use when: new page, missing contract, stale comparators, or human/plan says so.

```bash
cd ${HOME}/workspace/experiments/agent-skills/skills/dogpile
./run.sh search \
  "<task-specific query: cyber workflow + competitor/product patterns>" \
  --persona <lead-persona-slug> \
  --rationale "Justify Explorer page against real cyber tasks; minimize dashboard theater" \
  --context "Page: <page-id>. Primary object: <artifact>. Fail-closed if stale/unproven." \
  --html-report \
  --report-file <phase-root>/dogpile/<page-family>/dogpile-report.html
```

Distill into `page-contracts/<page>.md` once. Record provider caveats as non-claims.

Contract fields (required in the markdown, whether or not dogpile just ran):

| Field | Required |
|---|---|
| Operator / persona | Who performs this cyber task |
| Trigger | When they open this page |
| Primary object | Row, case, relationship, source, monitor dimension |
| Authoritative source | API, graph, monitor artifact — not UI copy |
| Valid actions | Inspectable actions that change or prove truth |
| Comparator set | Named products/tools/workflows (persona-voiced) |
| Theater risks | Misleading greens, hidden caveats, unproven labels |
| Promotion evidence | What TI + screenshots must show |

Research informs obligations; it does **not** prove the UI. It also does **not**
need to be regenerated on every WebGPT resend.

### 5. Build the WebGPT packet (repeatable each round)

Create or refresh `REVIEW_PACKET.md` using `templates/WEBGPT_REVIEW_PACKET.md`.

The packet must inline summaries of JSON artifacts and list screenshot paths. If WebGPT cannot view a screenshot, the review must be `insufficient_evidence` for visual claims.

### 6. Build the human HTML report

Create `report.html` using `templates/HUMAN_REPORT.html`.

The report must show:

- verdict bar
- executive summary
- benchmark research findings
- persona evaluation
- deterministic interactions table
- image-by-image gallery
- dashboard-theater audit
- blockers
- next code-runner actions

### 7. Produce review.json

Create `review.json` with:

```json
{
  "schema": "review_page.v1",
  "page": "",
  "page_verdict": "pass|degraded|fail|insufficient_evidence",
  "overall_verdict": "PASS|NEEDS_CHANGES|BLOCKED|HUMAN_REQUIRED",
  "lead_persona": "",
  "research_sources": [],
  "evidence": {
    "screenshots": [],
    "test_interactions": "",
    "page_contract": "",
    "api_state": ""
  },
  "blocking_findings": [],
  "conditions": [],
  "non_blocking_findings": [],
  "code_runner_actions": []
}
```

## Verdict policy

| Condition | Page verdict | Overall verdict |
|---|---|---|
| All deterministic proof passes, screenshots prove workflow, no hidden failures | pass | PASS |
| Agent-fixable defects remain | fail or degraded | NEEDS_CHANGES |
| Required artifacts/screenshots are missing | insufficient_evidence | BLOCKED |
| Human scope/policy/signoff required | degraded or fail | HUMAN_REQUIRED |

Use `NOT_SAFE` language in prose when a page hides degraded state, claims green without evidence, or presents unsupported compliance/security certainty.

## Persona assignment guidance

| Page type | Lead persona | Cyber task / review focus |
|---|---|---|
| Coverage / monitor status | Nico Bailon + Rob Armstrong | Corpus/monitor readiness truth; closure vs raw caveats |
| Chat / evidence workspace | Brandon Bailey + Nico Bailon | Evidence-gated Q&A; audit trail; fail-closed deflection |
| Controls / QRAs / Sources / URLs | Nico Bailon | Corpus provenance, trust state, lineage, freshness |
| Threat matrix | Nico Bailon (+ Brandon for signoff claims) | Technique–control–evidence triage vs matrix theater |
| Posture | Brandon Bailey | Posture/signoff claims vs evidence-backed assurance |
| Supply chain | Brandon Bailey + Nico Bailon | Vendor/component risk, provenance, workflow integration |
| Explorer nav / shell | Margaret Chen | Operator orientation under degraded pages; no false confidence |

## Pass blockers

A page cannot pass if any of these are true:

- no current full-page screenshot
- no deterministic interaction proof
- no current page contract/state JSON
- status claims are green but caveats are hidden
- screenshots do not show the claimed state
- evidence links/citations are labels only and do not resolve
- refresh/navigation persistence is required but unproven
- unsupported/missing-evidence states are hidden
- page contract with cyber-task + comparator obligations is missing for a product review
- page exists mainly as aggregate status without drilldown to authoritative source
- explicit `$dogpile` was requested but not run/distilled into a contract
- WebGPT was asked to infer missing visual proof
- accepted ledger status is used as product readiness proof

## Code-runner action rules

Return at most five actions, preferably three.

Good action:

```text
Persist the selected evidence-case id, citations, caveats, and artifact links in page state so they survive refresh and tab navigation.
```

Bad action:

```text
Improve the page and make it better.
```

Actions must be page-scoped, testable, and tied to a failing screenshot or interaction.

## Files to generate

For each run:

```text
<page>-review-rN/
  REVIEW_REQUEST.md
  REVIEW_PACKET.md
  report.html
  review.json
  web-research-request.md
  evidence/
  screenshots/
```

Optional:

```text
  screenshots/index.html       # screenshot contact sheet if not embedded in report
  artifacts.zip                # upload bundle
```

## Sanity check

Before asking WebGPT:

- [ ] One page only
- [ ] One lead persona
- [ ] Page contract with cyber-task + comparators attached (fresh `$dogpile` only if explicitly requested)
- [ ] Screenshots exist
- [ ] Deterministic interaction table exists
- [ ] Every screenshot has expected/observed/verdict
- [ ] Every pass claim has source artifact
- [ ] Failure/degraded states are visible or explicitly missing
- [ ] `review.json` is valid JSON
- [ ] `report.html` opens locally

### WebGPT tab binding (CLI parity)

Prefer **zero-flag** invocation from a registered working directory. `/ask` and `/surf` compose `$browser-oracle` automatically.

| Flag | When to use |
|------|-------------|
| *(none)* | cwd has walk-up registry + binding — preferred |
| `--browser-oracle-from <dir>` | Override walk-up root (monorepo subdir) |
| `--webgpt-project <name>` | Explicit project; skips yaml walk-up |
| `--webgpt-tab-id <id>` | One-off override; skips walk-up |
| `--webgpt-url <url>` | Resolve by conversation URL; skips walk-up |

Setup: `$browser-oracle register` + `bind` + `doctor --from <dir>`. See `$browser-oracle` and `$ask` SKILL.md **WebGPT tab binding** sections.

## CLI (installed skill)

Run from any directory (defaults `SPARTA_ROOT=${HOME}/workspace/experiments/sparta`):

```bash
${HOME}/workspace/experiments/agent-skills/skills/review-page/run.sh list-pages
${HOME}/workspace/experiments/agent-skills/skills/review-page/run.sh run-ti --page coverage --capture-suffix -r2
${HOME}/workspace/experiments/agent-skills/skills/review-page/run.sh build --page coverage --capture-dir <captures-dir>
${HOME}/workspace/experiments/agent-skills/skills/review-page/run.sh preflight --page coverage --capture-dir <captures-dir>
${HOME}/workspace/experiments/agent-skills/skills/review-page/run.sh package --page coverage --round-label 2
```

**Per-interaction step bundles (optional, for attach-limit-friendly review):**

```bash
./run.sh prepare-webgpt-steps --page coverage --out-dir <packet-dir>
```

**WebGPT adjudication (owned by `$ask`, not this skill):**

Full packet:

```bash
cd ${HOME}/workspace/experiments/agent-skills/skills/ask
./run.sh ask webgpt "/review-page coverage round 2" \
  --browser-oracle-from <repo-subdir> \
  # or explicit: --webgpt-project sparta-explorer-review --webgpt-tab-id <tab> \
  --once --oracle-iterations 1
```

Per-interaction loop (interaction id + element + expected + screenshot zip each round):

```bash
./run.sh ask webgpt "/review-page coverage --step-loop round r3 max-steps 11" \
  --browser-oracle-from <repo-subdir> \
  # or explicit: --webgpt-project sparta-explorer-review --webgpt-tab-id <tab> \
  --once --oracle-iterations 1
```

SPARTA shim (packet build only):

```bash
uv run python scripts/review_page_bundle.py build --page coverage
```

Artifacts per run:

```text
<phase63>/webgpt-page-reviews/<page>/
  REVIEW_PACKET.md
  review.json            # populate after WebGPT; template in examples/
  report.html            # build via scripts/build_page_report.py when review.json is complete
  review_page.gate.v1.json
  review-bundle.zip
  evidence/
  screenshots/
```

After WebGPT returns `NEEDS_CHANGES` and `CODE_RUNNER_ACTIONS`, implement fixes,
rerun `$test-interactions`, rebuild the packet (`build` / `package`), and resend to WebGPT
— **without** rerunning `$dogpile` unless the contract itself is wrong or stale.

Hand `review-bundle.zip` or `REVIEW_PACKET.md` to `$ask webgpt` (see `references/WEBGPT_DELIVERY.md`).
