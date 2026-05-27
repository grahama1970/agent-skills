---
name: review-design
description: >
  Multi-provider AI design review of UI screenshots and design tokens for UX audits.
triggers:
  - review design
  - design review
  - UX audit
  - audit this UI
  - review this UI
  - review the design
  - critique this design
  - compare to raycast
  - design comparison
  - visual review
  - UI review
  - check the UX
  - assess the design
  - design feedback
  - review-design with webgpt
  - webgpt design review
  - webgpt visual review
  - design review over 2 rounds
allowed-tools:
  - Bash
  - Python
metadata:
  short-description: Vision-driven UX design review

provides:
  - review-design
composes: [task-monitor, memory, scillm, ask, project-knowledge, surf, test-interactions]
---

## Standard Review Iteration Parameters

This `review-*` skill follows the shared contract in
`skills/.system/review-iteration-contract.md`.

Canonical parameters:

- `--max-rounds N`
- `--output-dir PATH`
- `--ask-gate`
- `--ask-model MODEL` (default `gpt-5.5`)
- `--ask-reasoning LEVEL` (default `high`)
- `--ask-timeout SECONDS`
- `--ask-focus LABELS`

When `--max-rounds > 1` is supplied, the skill must behave as a bounded
gate-producing controller or fail closed if that mode is not implemented. The
canonical gate artifact is `review_result.json` with verdict
`PASS`, `NEEDS_CHANGES`, `BLOCKED`, or `INSUFFICIENT_EVIDENCE`.

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# review-design

Multi-provider AI design review skill. Submits UI screenshots + design tokens to vision-capable LLMs for structured UX audits.

## PERSONA REQUIREMENT (NON-NEGOTIABLE)

**Every review MUST specify `--persona`.** A review without a persona is a failure — it produces generic, unfocused feedback that wastes everyone's time.

The `--persona` flag:
1. Loads the persona's AGENTS.md (identity, domain expertise, review dimensions)
2. Runs `/memory recall` for the persona's scope (prior reviews, QRA corpus, relationships)
3. Injects all context into the system prompt so the LLM reviews AS that persona

```bash
# CORRECT — persona-driven review
./run.sh review --persona brandon-bailey --screenshots ./screenshots/ --tokens ./tokens.json

# WRONG — will fail with validation error
./run.sh review --screenshots ./screenshots/ --tokens ./tokens.json
```

Available personas for design review:
- `brandon-bailey` — CMMC/compliance reviewer (4,017 controls, 77,528 relationships)
- `rob-armstrong` — Formal verification reviewer (Lean4 proof obligations)
- `margaret-chen` — Quality assurance reviewer
- `nico-bailon` — Extraction QA reviewer (PDF fidelity, tables, sections, quarantine triage)

## Triggers

- review design
- design review
- UX audit
- audit this UI
- review this UI
- review the design
- critique this design
- compare to raycast
- design comparison
- visual review
- UI review
- check the UX
- assess the design
- design feedback

## Description

Iterative 3-step design review pipeline inspired by `review-code`:

1. **Audit** - Analyze screenshots against design tokens + reference images, identify gaps
2. **Judge** - Critique the audit findings for accuracy and prioritization
3. **Finalize** - Produce actionable recommendations with specific token/layout changes

Supports multiple vision-capable providers:
- **Claude** (`claude`) - claude-sonnet-4-20250514 (vision)
- **OpenAI** (`openai`) - gpt-4o (vision)
- **Gemini** (`gemini`) - gemini-2.0-flash (vision)
- **scillm** (`scillm`, aliases: `vlm`, `subagent`) - `model: "vlm"` via
  `POST /v1/chat/completions`, using scillm's VLM fallback cascade.

## Relationship To Plan Iterate And Test Interactions

`$review-design` is the domain loop for UI/UX phases. `$plan-iterate` is the
parent evidence ledger and acceptance gate; it records phase state, validation
logs, reviewer receipts, blockers, and final acceptance. `$review-design` should
not mark a phase accepted by itself.

When the UI under review has live interactions, panes, graph states, keyboard
flows, or nested scroll containers, `$review-design` must drive
`$test-interactions` as its deterministic evidence backend:

```text
$plan-iterate phase
  -> project agent implements UI change
  -> $review-design loop
       -> $test-interactions run on the live DOM
       -> collect qid/COTS/DOM results and focused/container screenshots
       -> reviewer critiques fresh screenshots
       -> project agent patches valid blockers
       -> rerun relevant $test-interactions interactions
       -> rereview fresh screenshots
  -> $plan-iterate records receipts and accepts or blocks
```

`$test-interactions` owns deterministic pass/fail, live-DOM clicks, qid/COTS
checks, focused crop/zoom screenshots, and stitched container screenshots.
`$review-design` owns the visual critique, blocker synthesis, and bounded
reviewer backoff. A stale screenshot set or DOM-only assertion pass is not
enough for a `satisfied` design verdict.

When `$review-design` participates in a `$plan-iterate` phase, its primary
deliverable is a read-only visual/interaction review bundle or loop artifact set
for the phase-level `$scillm` aggregation gate. `$review-design` does not decide
whether the phase continues or completes.

Minimum aggregation input:

```text
review-design/
  context.md
  test-interactions-manifest.json
  test-interactions-results.json
  screenshots/
  code-context.md
  design-requirements.md
  aggregate_verdict.json
  DESIGN_REVIEW_ITERATE_MATRIX.md
```

The `$scillm` gate consumes this bundle alongside other applicable review
bundles and returns `PASS`, `NEEDS_CHANGES`, `BLOCKED`, or
`INSUFFICIENT_EVIDENCE`. A project-agent or reviewer statement of visual
satisfaction is inadmissible unless the screenshot bundle visibly proves the
target state.

If a human has caught obvious UX errors after a prior review-design PASS, treat
that as a false-green event. The next `$review-design` loop must harden the
evidence packet before another PASS is admissible:

- rerun `$test-interactions` with a manifest that covers every live `[data-qid]`
  interactive element and the semantic workflow under review;
- include focused/zoomed and container screenshots for the actual defect areas;
- run section-scoped reviews rather than one aggregate whole-page critique;
- include a Dogpile/web/GitHub/image-derived modern reference packet for
  serious workflow editors, graph editors, evidence panes, queues, and other
  high-judgment UI;
- include a concise list of design requirements derived from that reference
  packet, plus the source URLs/repos used to derive them;
- attach reference screenshots captured from the modern examples when visual
  comparison is part of the review question;
- use the same review persona for the Dogpile research packet and the
  `$review-design iterate` run when `--require-modern-reference` is set, so a
  generic benchmark cannot launder a persona-bound verdict;
- include the exact `$test-interactions` manifest and deterministic
  `results.json` summary in the reviewer context so screenshots are compared
  against the intended live DOM coverage, not judged as isolated images;
- require the reviewer to list `missing_evidence` instead of filling gaps with
  generic UX prose;
- record a matrix with persona, round, screenshot, verdict, finding count,
  missing evidence, model/proof, and end state.

A design PASS is inadmissible when the modern/reference packet is required but
missing, when the screenshots do not show the target state, or when
`$test-interactions` did not exercise the interaction path being judged.

## Requirements

**Screenshots are MANDATORY.** This skill will fail if no screenshots are provided. A design review without visual evidence is impossible — it would be pure speculation.

Capture screenshots before running a review:
- `/surf snap` — Browser screenshot via CDP
- `/surf-qml` — QML/Qt app screenshot via AT-SPI
- `flameshot full --path ./screenshots/current.png` — System screenshot

The `--screenshots` directory must contain at least one PNG/JPG image.

Prefer a screenshot set, not a single screenshot:
- one full-surface shot for layout and hierarchy
- cropped shots for local defects
- zoomed shots for typography, spacing, chips, badges, and dense evidence UI

If `/surf` is available, use its crop and zoom capabilities to capture the exact defect area instead of relying only on full-page screenshots.

## Bakeoff Board Contract

When `$review-design` is used for a bakeoff, the generated bakeoff board is a
review surface, not just a gallery. It must make the selection state obvious to
a human in the first viewport.

The board must answer these questions without requiring logs, screenshots
folder inspection, or tab-click discovery:

1. **Who won?** Show one and only one `Winner` label on the winning base
   candidate.
2. **Why did it win?** Put the winning rationale in a one-sentence
   first-viewport summary.
3. **What is being iterated now?** Show one and only one `Current iteration` or
   `Active iteration` label on the successor candidate.
4. **What changed in the iteration?** Summarize the active deltas in the same
   first-viewport band.
5. **How do I open it?** Candidate cards and the winner/iteration CTA must open
   the corresponding design by click and keyboard focus.

Required rendered elements:

- A top-level winner/iteration banner above the candidate grid.
- A distinct `Winner` badge on the original selected candidate.
- A distinct `Current iteration` or `Active iteration` badge on the patched
  successor.
- A visible CTA such as `Open Current Iteration`.
- Clickable/focusable candidate cards with tooltips or titles describing what
  will open.
- A fresh screenshot proving the first viewport shows the banner, badges, and
  clickable affordances.

Failure conditions:

- The winner appears only in prose, filenames, logs, or final response text.
- Multiple candidates look equally selected.
- The iteration card looks like another peer candidate.
- Navigation only works through tab buttons.
- The user has to infer that `v2`, `iterate`, or a score means active work.
- The screenshot shown to the human does not include the winner/iteration
  banner.

## Design Blockage Protocol

If the problem is genuinely design-driven rather than implementation-driven, do not improvise.

1. Check the current UI visually first (`/surf snap`, equivalent CDP capture, or system screenshot).
2. Before asking for a redesign, ask each candidate model to generate 3–4 UI kit directions on a new isolated page or mockup surface.
3. Compare the generated kits, select concrete patterns to keep, and state which patterns are rejected.
4. If the issue is still ambiguous after visual inspection and UI-kit exploration, stop coding.
5. Generate a complete external-review bundle for a web LLM reviewer.
6. Hand off the bundle with explicit design questions instead of guessing.

Use this protocol when the open question is about hierarchy, spacing, density, affordance,
interaction semantics, or visual weight rather than a code defect.

The isolated UI-kit page is intentional: it lets models explore visual systems without
damaging the production surface. Treat the kits as design options, not implementation
authority. The agent should pick and compose the strongest parts before touching the
real UI.

## External Web LLM Preference

For serious design adjudication, prefer generating a complete bundle for manual upload to a
web LLM reviewer instead of relying on an API call. Gemini AI Studio web is one good target,
but the packaging workflow should remain model-agnostic.

WebGPT is also an approved external design reviewer when prior project evidence
shows it gives stronger design judgment than Codex/scillm/API routes for the
surface class. Treat it as a reviewer, not as an implementation agent.

Use provider API review for:
- quick iterative critique
- broad screenshot audits
- low-risk comparison passes

Use `bundle` / `bundle-code` / `bundle-upload` for external web review when:
- the agent is blocked on design judgment
- the user asks for external design help
- the review needs full context, screenshots, code, constraints, and open questions together
- you need a durable handoff another human can inspect before sending

Use `webgpt-review` when:
- the target reviewer is WebGPT/ChatGPT web
- a stable ChatGPT tab id or conversation URL is available for the real `$ask`
  WebGPT route
- the review request needs the same artifact structure as `bundle-upload`
- the agent needs a durable `$ask` request/status/events record with
  controlled-tab metadata

Important limitation: automated `$ask` WebGPT text submission currently submits text. It
does not prove WebGPT inspected screenshot pixels unless screenshots were
manually uploaded or a future file-attachment path records that upload. A
text-only WebGPT response may critique design requirements and code context, but
it is not a visual review verdict.

### WebGPT Reviewer Loop Shorthand

When the user says a short prompt such as:

```text
per current changes and project knowledge, $review-design with webgpt over 2 rounds
```

expand it into a bounded design reviewer/project-agent loop:

1. Use `$project-knowledge` and current artifacts to recover product intent,
   accepted design direction, known visual failures, non-goals, and any
   previous reviewer findings.
2. Capture or reuse fresh screenshots that visibly prove the current state.
   Include cropped/zoomed screenshots for the exact defect area when relevant.
3. Build a `webgpt-review`, `bundle-upload`, or equivalent review package with
   screenshots, relevant React/QML/HTML/CSS, design tokens, constraints, known
   issues, and exact design questions.
4. Send the complete package through the real `$ask`/WebGPT route when the
   request is text-only, or prepare the upload package when screenshot pixels
   must be inspected manually. Preserve request, response, controlled-tab, and
   package artifacts.
5. The project agent applies or adapts valid design findings, re-renders the
   surface, and captures a fresh screenshot.
6. Build the round-2 package with round-1 findings, what changed since round 1,
   rejected findings with rationale, fresh screenshot evidence, and remaining
   questions.
7. Run exactly one more WebGPT review round unless round 1 blocks on a human
   product decision.
8. Final status includes screenshot artifact paths, package/reviewer artifacts,
   changed files, visual verification statement, unresolved risks, and whether
   human decision is required.

Preferred human prompt:

```text
per current changes and project knowledge, $review-design with webgpt over 2 rounds
```

Scoped variant:

```text
per current changes, $review-design with webgpt over 2 rounds for the QRA evidence pane
```

Do not make the human encode the workflow in a long prompt. The skill owns the
loop expansion; the human owns product intent, hard constraints, and acceptance
decisions.

### WebGPT Review Command

`webgpt-review` builds a WebGPT-oriented review package and can optionally submit
the text request through the real `$ask` WebGPT route. `$surf` remains the lower
level browser transport owned by `$ask`, not the review entrypoint.

```bash
# Create a WebGPT upload package for manual browser upload.
./run.sh webgpt-review \
  --persona brandon-bailey \
  --screenshots ./ui/ \
  --files src/components/sparta/explorer/QRAsView.tsx \
  --css src/styles/sparta.css \
  --context-file ./REVIEW_CONTEXT.md \
  --core-objective "Assess whether the QRA pane supports evidence-first correction without dashboard theater" \
  --audit-target "Right pane must expose answer, reasoning, evidence freshness, and review actions without hiding failures" \
  --known-issue "Prior dashboard-style layouts looked polished but did not explain the operator workflow" \
  --surface-role "Right pane: QRA evidence, correction, approval, and review history" \
  --clipboard-file
```

```bash
# Submit only the text request to an already-controlled ChatGPT tab via `$ask`.
# This is useful for prompt/design-contract critique, but not visual proof.
./run.sh webgpt-review \
  --persona brandon-bailey \
  --context-file ./REVIEW_CONTEXT.md \
  --core-objective "Review the design contract before rendering" \
  --tab-id 837343233 \
  --submit-text-only
```

Required artifacts:

```text
WEBGPT_REVIEW_REQUEST.md
REACT_COMPONENTS_BUNDLE.md
WEBGPT_REVIEW_UPLOAD_PACKAGE.zip
webgpt-review-result.json
ask-request.json            # only when --submit-text-only is used
ask-status.json             # only when --submit-text-only is used
ask-events.jsonl            # only when --submit-text-only is used
webgpt-response.md          # only when --submit-text-only is used
webgpt-response.meta.json   # only when --submit-text-only is used
```

Fail-closed rules:

- Do not claim visual satisfaction from `--submit-text-only`.
- Do not claim screenshot inspection unless the package was actually uploaded
  to WebGPT or the automation records file attachment proof.
- Do not let WebGPT copy generated-image or screenshot text as source truth.
- Preserve controlled tab id, conversation URL, sentinel metadata, and response
  source in `webgpt-review-result.json` for any automated submission.

## Async Review Backoff Loop

Use this workflow when a selected design direction needs iterative reviewer
backoff before implementation. This is common after `/create-mockup bakeoff`
selects a winning candidate and the human adds corrections.

The loop is deterministic and bounded. It does not require Pi or an interactive
session manager; Pi/boomerang may summarize context, but the durable state must
live in files and SSE/status artifacts.

### Ask-Backed OpenCode Kimi Reviews

When the human asks for `$ask oc kimi` with `$review-design`, treat that as a
clear request to run the review-design critique loop through `/ask` + `/scillm`
using the direct model `opencode-go/kimi-k2.6`. Do not route it through
`review-design --provider subagent`, because that provider selects the
subagent/default VLM lane rather than OpenCode Kimi.

`$ask oc kimi ... for $review-design with maximum 3 rounds` means:

1. Capture or use a fresh screenshot bundle for the target surface.
2. Ask `opencode-go/kimi-k2.6` to review the screenshot(s) with the
   review-design persona, constraints, and verdict schema.
3. Patch the UI yourself; the reviewer only critiques.
4. Re-render and capture a fresh screenshot before the next reviewer round.
5. Stop at the first `satisfied`/PASS verdict, a concrete blocker, or the
   requested maximum round count.

The round limit is binding. If the user says "maximum 3 rounds", run at most
three reviewer verdict rounds. If the user says "maximum 5 tries", run at most
five. Each round must write artifacts under a durable loop directory and record
the screenshot, reviewer response, verdict, patch summary, and next action.

Use direct `/scillm` when the `/ask` CLI cannot attach images for the current
surface, but preserve the `/ask` semantics: model shorthand resolution,
streaming liveness, bounded rounds, and artifact-backed verdicts.

### Section-Scoped Review Bundles

When the human asks to review each section of a complex surface, do **not** send
the whole page screenshot set to one reviewer call. Run one reviewer call per
section, or at most a very small batch when sections are tightly coupled.

Each section review call should include:

1. One rendered screenshot cropped to the section under review.
2. The section's purpose in the product workflow.
3. The focused React/JSX/HTML that renders that section.
4. The focused CSS affecting that section, plus shared design variables when
   relevant.
5. Short global context and non-negotiables that apply to every section.
6. A strict verdict schema: `satisfied | needs_changes | blocked`.

For React applications, include the relevant component code directly. Kimi and
other strong multimodal reviewers can reason over the rendered screenshot and
the React/CSS implementation together. Prefer focused code over whole-file dumps:
send the section component, helper functions used by that section, and the CSS
selectors that affect it. Include whole-file context only as a secondary
reference and tell the reviewer to focus on the section.

Correct section prompt shape:

```text
Review section: TOC Audit / Document Map

Global context:
- PDF Lab Coverage must avoid dashboard theater.
- Evidence must be human-inspectable.
- Provenance keys are not Memory/Qdrant recall proof.
- Final confidence depends on real artifacts and recall QA.

Section purpose:
- Show whether TOC entries resolve to extracted document anchors.

Attached:
1. Section screenshot
2. Section React/JSX
3. Section CSS
4. Relevant artifact field definitions

Return:
VERDICT: satisfied | needs_changes | blocked
BLOCKING_CHANGES:
- ...
FIRST_PATCH:
- ...
```

Wrong section review shape:

```text
Here are 12 screenshots of the whole page. Review every section.
```

That overloads the reviewer, encourages reasoning-only timeouts, and produces
ambiguous aggregate feedback. If a section fails, patch only that section and
re-review only that section before synthesizing the overall result.

```text
for round in 1..N:
  1. project agent renders the current candidate and captures screenshots
  2. reviewer model critiques screenshots + constraints + previous deltas
  3. reviewer returns a structured verdict
  4. project agent patches the design, never the reviewer model
  5. project agent verifies with CDP and records artifacts
  6. stop early if verdict is satisfied or if blocking ambiguity remains
```

For interaction-driven browser surfaces, step 1 and step 5 should normally be
implemented by `$test-interactions run`, not manual screenshot capture. The
manifest must target `[data-qid]` selectors and capture focused/zoomed evidence
for the exact graph, pane, control, or nested scroll area under review.

### Roles

- **Project agent** owns file changes, implementation judgment, CDP
  verification, artifact paths, and final integration.
- **Reviewer model** owns critique only. It must return findings, deltas, and a
  verdict; it must not edit files or claim implementation is complete.
- **Human** owns product constraints and may interrupt with new hard
  requirements. New human constraints must be fed into the next reviewer round
  before patching unless they are purely mechanical.

### Required State Artifacts

For each loop, create a stable directory such as:

```text
reviews/<surface>/loop/
  state.json
  events.jsonl
  rounds/
    001/
      prompt.md
      screenshot.png
      read.json
      reviewer.md
      verdict.json
      patch_summary.md
      cdp.json
    002/
      ...
  final/
    approved_screenshot.png
    implementation_handoff.md
```

`state.json` must include:

```json
{
  "state": "running | needs_patch | waiting_review | satisfied | blocked | failed",
  "round": 2,
  "surface": "sparta-chat-kimi-v2",
  "latest_screenshot": "rounds/002/screenshot.png",
  "latest_verdict": "rounds/002/verdict.json",
  "next_action": "patch | review | ask_human | implement"
}
```

### SSE Event Contract

Long-running review loops should expose or record SSE-shaped events so the human
and project agent can work on other tasks while the loop progresses.

```text
event: round_started
data: {"round":2,"surface":"sparta-chat-kimi-v2"}

event: reviewer_progress
data: {"round":2,"model":"opencode-go/kimi-k2.6","content_chars":3192}

event: reviewer_verdict
data: {"round":2,"verdict":"needs_changes","blocking_changes":[...]}

event: patch_started
data: {"round":2}

event: cdp_verified
data: {"round":2,"screenshot":"rounds/002/screenshot.png"}

event: satisfied
data: {"round":4,"handoff":"final/implementation_handoff.md"}
```

If the backing reviewer route is `/ask`, preserve its runtime artifacts and
map `oracle_scillm_call_started`, `oracle_scillm_stream_progress`,
`oracle_scillm_call_finished`, and failures into the loop `events.jsonl`.

When this loop is embedded in `$plan-iterate`, the project agent records the
loop as a read-only `domain_review_loops[]` entry with the review persona,
immutable UI/UX goal, context artifact, relevant `best-practices-*` skills,
state/events/aggregate artifacts, and the screenshot-to-finding matrix. Each
round also has exactly three project-agent-owned plan artifacts:
implementation/patch, validation/evidence, and review/escalation.

### Reviewer Verdict Schema

Every reviewer round must return this shape, either as JSON or as Markdown with
the same headings:

```json
{
  "verdict": "satisfied | needs_changes | blocked | insufficient_evidence",
  "blocking_changes": [],
  "non_blocking_changes": [],
  "implementation_notes": [],
  "screenshot_checks": [],
  "do_not_do": [],
  "aggregation_ready": false,
  "missing_evidence": []
}
```

`satisfied` is only valid when the reviewer has inspected a fresh rendered
screenshot. A reviewer may not mark a design satisfied from source files alone.
If screenshots, interaction results, or the exact target state are missing,
return `insufficient_evidence` and list `missing_evidence`.

### Bakeoff Winner Iteration

After a design bakeoff:

1. Select the winning structural candidate from rendered screenshots.
2. Apply the **Bakeoff Board Contract** before reporting results to the human.
   The rendered board must show the winner, rationale, current iteration,
   active deltas, and open action in the first viewport.
3. Verify the bakeoff board screenshot itself. Do not rely only on screenshots
   of the candidate design.
4. Make overview cards open the corresponding design when clicked or focused;
   the board must not require guessing that only the tab bar is navigational.
5. Preserve both the winning base candidate and the active iteration so the
   lineage is clear.
6. Start a bounded backoff loop on that candidate only.
7. Feed human corrections and known failure examples into reviewer prompts.
8. Patch the winning design in place or in a versioned copy such as `kimi-v2`.
9. Run persona-based `/review-design` on the converged screenshot before React,
   Tailwind, QML, or production implementation.

Do not run another broad bakeoff unless the selected direction itself is no
longer valid.

The bakeoff board is itself a design artifact. A human should be able to answer
these questions in the first viewport without reading logs: Who won? What is the
active iteration? Why is it being iterated? How do I open it?

### SPARTA / Compliance UI Rules

For SPARTA, PDF Lab, QRA, CAE, CMMC, or compliance-review surfaces, the loop
must explicitly test:

- evidence cases are readable by a compliance officer
- evidence cases are visually separate from final agent responses
- controls, techniques, artifacts, and domain terms have hover/focus
  explanations, not only color
- source context never replaces citable evidence receipts
- uploads are explicit when the workflow requires PDFs or source documents
- no model picker is added unless the product requirement explicitly asks for
  model selection
- no dashboard, raw context pane, or metrics wall displaces the chat/evidence
  task flow

### Implementation Handoff

When the reviewer is satisfied, the project agent writes
`final/implementation_handoff.md` with:

- approved screenshot path
- approved mockup/source path
- required components and states
- animation requirements
- accessibility and keyboard requirements
- blocked/deferred items
- exact screenshot checks to rerun after implementation

Only then should the project agent implement the design in React/Tailwind,
QML, or the target application.

## Usage

```bash
# Basic design review (single round) — persona is REQUIRED
./run.sh review --persona brandon-bailey --screenshots ./screenshots/ --tokens ./design-tokens.json

# With reference images (compare to target design)
./run.sh review --persona rob-armstrong --screenshots ./current/ --reference ./raycast/ --tokens ./tokens.json

# Multi-round iterative review (recommended)
./run.sh review --persona brandon-bailey --screenshots ./current/ --reference ./target/ --tokens ./tokens.json --rounds 2

# Specific provider
./run.sh review --persona margaret-chen --provider claude --screenshots ./ui/

# Animation review with burst filmstrip + source code context
./run.sh review --persona rob-armstrong --screenshots ./screenshots/s6-sentinelhud/ \
  --tokens ./tokens/s6-sentinelhud.design-tokens.json \
  --code-context ./src/components/EmbryThinkingIcon.tsx \
  --code-context ./src/styles/distance.css \
  --rounds 2

# Generate review request bundle (for manual submission)
./run.sh bundle --screenshots ./ui/ --tokens ./tokens.json --output review_request.md

# Generate low-file-count upload zip for external web LLMs
./run.sh bundle-upload \
  --screenshots ./ui/ \
  --files src/components/sparta/shared/EvidenceCaseTrace.tsx \
  --files src/components/sparta/explorer/QRAsView.tsx \
  --context-file ./REVIEW_CONTEXT.md \
  --core-objective "Audit whether the interface supports decision-first human correction of failed evidence cases" \
  --audit-target "EvidenceView.tsx currently merges question, answer, and reasoning into one extraction blob; assess the impact on question-vs-answer grounding clarity" \
  --audit-target "EvidenceCaseTrace.tsx uses a 3-column verification grid; predict failure in narrow chat layouts" \
  --focus "hierarchy,density,inline entity emphasis" \
  --surface-role "Middle pane: question, status, and agent response" \
  --surface-role "Right pane: evidence explanation and optional details" \
  --known-issue "Inline entities previously rendered as oversized chips in prose" \
  --known-issue "Crosswalk chain counts leaked implementation detail into the primary UX" \
  --request-mockup \
  --target "Gemini web" \
  --clipboard-file
```

## Burst Filmstrip Mode

For reviewing animations (particle systems, state transitions, force rings), use
burst capture to generate filmstrip frames that show the animation over time:

```bash
# 1. Capture burst filmstrips (10 frames over 2s per state transition)
python scripts/capture_matrix.py --burst

# 2. Frames saved to docs/screenshots/{surface}/burst/{persona}_{state}_f01..f10.png
#    Regular resting-frame screenshots still captured alongside

# 3. Run review — burst/ subdirectory auto-included
./run.sh review --screenshots ./docs/screenshots/s6-sentinelhud/ \
  --code-context ./src/components/EmbryThinkingIcon.tsx \
  --tokens ./tokens.json
```

The reviewer sees the animation code AND the frame-by-frame filmstrip, enabling
verification of force ring emergence, dash rotation, ripple expansion, and color
transitions that are invisible in single static screenshots.

With Gemini's 1M context window, 50+ screenshots + full source files fit easily.

## Input Format

### Design Tokens (JSON)
```json
{
  "meta": { "name": "...", "description": "..." },
  "colors": { ... },
  "typography": { ... },
  "layout": { ... },
  "animation": { ... },
  "effects": { ... },
  "interactions": { ... }
}
```

### Screenshots
- PNG/JPG files in a directory
- Named descriptively: `full-launcher-empty.png`, `result-list-hover.png`
- Include both current UI and reference/target UI if comparing

## Output Format

### Per-Round Files (in `review_output/`)
```
roundN_step1.md      # Initial audit findings
roundN_step2.md      # Judge critique
roundN_final.md      # Finalized recommendations
roundN_audit.json    # Structured findings (machine-readable)
```

### Audit JSON Structure
```json
{
  "summary": "Overall assessment",
  "findings": [
    {
      "severity": "high|medium|low",
      "category": "color|typography|layout|spacing|animation|interaction",
      "element": "search-bar",
      "issue": "Description of the gap",
      "current": "Current value or behavior",
      "recommended": "Suggested fix",
      "token_change": { "path": "colors.text.primary", "from": "#fff", "to": "#f5f5f5" }
    }
  ],
  "token_changes": [ ... ],
  "praise": [ "Things done well" ]
}
```

## Provider Capabilities

| Provider | Model | Vision | Codebase Access | Default |
|----------|-------|--------|----------------|---------|
| **scillm** | `vlm` via `localhost:4001` | Yes | Screenshots + explicit `--code-context` | **DEFAULT** |
| claude | claude-sonnet-4-20250514 | Yes | No — screenshots only | |
| openai | gpt-4o | Yes | No — screenshots only | |
| gemini | gemini-2.0-flash | Yes | No — screenshots only | |

### Why scillm is Default

The scillm provider routes through the local proxy:

- It uses the public `vlm` model alias, not a hardcoded provider model.
- scillm owns the VLM fallback cascade: Gemini free -> Gemini paid -> Claude OAuth -> Codex OAuth.
- Calls include `Authorization: Bearer sk-dev-proxy-123` and `X-Caller-Skill: review-design`
  for logging, budget tracking, and actionable provider errors.
- Direct providers only see the screenshots and whatever code context you manually pass via
  `--code-context`; scillm is the default path for model routing and fallback.

`--provider vlm` and `--provider subagent` are accepted as compatibility aliases for
`--provider scillm`. Do not add direct Chutes or Gemini model names as review-design
providers; use scillm model aliases through the scillm route.

## Commands

### `review` - Single-round design audit
Basic audit with optional reference comparison.

### `review-full` - Multi-round iterative audit (recommended)
Runs the 3-step pipeline for N rounds, each round refining findings.

### `iterate` - Design backoff loop with deterministic evidence
Recommended target behavior for implementation-backed UI review loops. The loop
should accept a `$test-interactions` manifest, run deterministic interactions,
review the fresh selected screenshots, let the project agent patch blockers, and
repeat until `satisfied`, `blocked`, or the configured round limit.

The CLI implements the parallelizable part of the loop as a bounded scillm batch:

- deterministic `$test-interactions run` stays sequential because later DOM
  states depend on earlier clicks, edits, waits, and screenshots
- independent screenshot/section reviewer calls run concurrently through
  `POST /v1/chat/completions` using `asyncio.create_task` +
  `asyncio.as_completed`
- each section writes a reviewer response, verdict JSON, and discrete end state
- the main project agent reads `state.json`, `events.jsonl`,
  `aggregate_verdict.json`, and `DESIGN_REVIEW_ITERATE_MATRIX.md`

```bash
./run.sh iterate \
  --manifest ./manifest.json \
  --persona nico-bailon \
  --provider scillm \
  --output-dir ./reviews/dag-editor/loop \
  --max-sections 8 \
  --max-concurrency 3
```

Use `--screenshots ./captures` instead of `--manifest` when deterministic
captures already exist. Use `--sections sections.json` for explicit
section-scoped review bundles; otherwise the command auto-selects focused and
container screenshots first.

For serious or repeatedly false-green surfaces, run `$dogpile` first and pass
the report or partial-results file as a modern reference packet:

```bash
/home/graham/workspace/experiments/agent-skills/skills/dogpile/run.sh search \
  "2026 modern DAG graph workflow editor UX node inspector evidence panel review queue React" \
  --persona margaret-chen \
  --rationale "Repeated false-green review-design results missed obvious workflow errors" \
  --context "Benchmark a node graph editor with evidence/provenance panels and approval queues" \
  --html-report

./run.sh iterate \
  --manifest ./manifest.json \
  --persona margaret-chen \
  --provider scillm \
  --modern-reference /home/graham/workspace/experiments/agent-skills/skills/dogpile/dogpile_partial_results.json \
  --reference-screenshots ./reference-screenshots/dag-editor \
  --require-modern-reference \
  --output-dir ./reviews/dag-editor/loop
```

`--require-modern-reference` fails closed unless the reference file exists.
When the reference file is Dogpile partial-results JSON, it must include a
`request_context.persona` matching `--persona`; otherwise the run fails closed.
Reviewers must compare screenshots to the provided reference packet and to the
`$test-interactions` manifest/results packet, then list missing benchmark or
interaction evidence under `missing_evidence`.

`--reference-screenshots` attaches captured benchmark screenshots to every
section review. Dogpile itself returns source URLs/reports, not guaranteed
screenshot pixels; if no reference screenshot directory is supplied for a
visual benchmark review, reviewers must treat the missing reference screenshots
as `missing_evidence` rather than guessing from URLs alone.

The durable loop directory has this shape:

```text
reviews/<surface>/loop/
  context.md
  state.json
  events.jsonl
  rounds/
    001/
      implementation-plan.md
      validation-plan.md
      review-plan.md
      interaction-results.json
      interaction-report.md
      screenshots/
      reviewer.md
      verdict.json
      patch_summary.md
    002/
      ...
  aggregate_verdict.json
  DESIGN_REVIEW_ITERATE_MATRIX.md
```

The matrix must be human-readable and include at least: round, persona,
screenshot path, section id, verdict, highest severity, end state, finding
count, missing evidence, model/proof fields, and verdict artifact path.

### `bundle` - Generate review request
Creates a markdown file with embedded images (base64) for manual submission to any LLM.

When blocked on design, this is the default escalation path.

### `bundle-upload` - Generate model-agnostic web-upload package
Creates a low-file-count zip for upload to web LLM interfaces with strict file-count limits.

Use this when:
- the web UI rejects larger zips with too many files
- you need a single upload artifact plus screenshots
- you want model-agnostic packaging rather than provider-specific formatting

The zip contains:
- `REVIEW_REQUEST.md`
- `REACT_COMPONENTS_BUNDLE.md`
- `DIFF.md`
- screenshot files (up to `--max-files`)

For good results, populate the request with:
- `--core-objective` stating the actual operator decision the UI must support
- `--audit-target` entries naming exact requirement-vs-implementation tensions
- `--surface-role` entries explaining what each pane or tab is supposed to do
- `--known-issue` entries naming the exact UX failures already observed
- a strong `--context` / `--context-file` describing the product workflow and constraints
- a screenshot set that includes full context plus cropped/zoomed defect views

This is the preferred path for Gemini web, Claude web, and similar browser upload flows.

### `webgpt-review` - Generate and optionally submit WebGPT design review package
Creates the same kind of compact external-review bundle as `bundle-upload`, but
adds a WebGPT-specific request and optional `$ask` WebGPT submission.

Use this command when WebGPT is the intended reviewer and you want the design
handoff to be reproducible. Use manual upload for actual screenshot-based review.
Use `--submit-text-only` only for design-contract critique, source/context
review, or WebGPT routing smoke tests.

#### KDE Plasma clipboard file handoff

When copying the generated zip to the clipboard on KDE Plasma/X11, prefer the
Qt-compatible `text/uri-list` target. The GNOME-specific
`x-special/gnome-copied-files` target may advertise successfully in `xclip` but
not paste as a file in KDE/browser upload surfaces.

Use this fallback after generating a review zip:

```bash
zip=/tmp/pdf-lab-review-design-bundle/pdf-lab-current-mockups-review.zip
printf 'file://%s\r\n' "$(realpath "$zip")" | xclip -selection clipboard -t text/uri-list
xclip -selection clipboard -t TARGETS -o | tr '\0' '\n'
xclip -selection clipboard -t text/uri-list -o
```

Expected clipboard payload:

```text
file:///tmp/pdf-lab-review-design-bundle/pdf-lab-current-mockups-review.zip
```

If file-paste still fails in a browser, use the file picker with the zip path
directly. The clipboard payload is still useful for Dolphin and KDE-aware paste
targets.

### `bundle-code` - Generate COMPLETE code review bundle for external LLMs
Creates a comprehensive markdown bundle with ALL code for honest external review.
**No truncation** - the reviewer sees everything needed to give real feedback.

**Required:** Use `--context` or `--context-file` to explain what you're building and why.
Without context, the reviewer is guessing.

```bash
# Full bundle with context (RECOMMENDED)
./run.sh bundle-code \
  -f src/components/SpartaExplorer.tsx \
  -f src/components/EvidenceCaseCard.tsx \
  -f src/components/MatrixCell.tsx \
  --css src/styles/nvis.css \
  --test-results /tmp/results.json \
  --context "SPARTA Explorer 2026: React UI for CAE evidence visualization.
    Requirements: COTS C02 (44px touch targets), WCAG 2.1 AA, prefers-reduced-motion.
    This session fixed: card disappearing on rebuild, focus-visible styles, ghost mode opacity." \
  --focus "COTS compliance, accessibility, React patterns" \
  -o REVIEW_BUNDLE.md

# Or use a context file for longer explanations
./run.sh bundle-code \
  -f src/**/*.tsx \
  --css src/**/*.css \
  --context-file ./REVIEW_CONTEXT.md \
  -o REVIEW_BUNDLE.md

# Copy directly to clipboard for Gemini web
./run.sh bundle-code -f src/*.tsx --context "..." --clipboard
```

Output includes (NO TRUNCATION):
- Full project context and rationale
- Complete test results with ALL failures
- Full source files (every line)
- Full CSS files
- Structured review questions asking for specific, actionable feedback

When preparing an external web LLM handoff, include:
- what the user is trying to accomplish
- what currently looks wrong, with screenshots
- what has already been changed
- the relevant components/files
- constraints and non-goals
- the exact design decisions that are still unresolved

### `compare` - Side-by-side comparison
Generates a visual comparison report between current and target design.

### `check` - Verify provider access
Tests that the selected provider has vision capability and valid credentials.

## Example Workflow

```bash
# 1. Capture screenshots of your UI
flameshot full --path ./screenshots/current.png

# 2. Gather reference screenshots (e.g., Raycast)
cp ~/raycast-ref/*.png ./screenshots/reference/

# 3. Create/update design tokens
cat > design-tokens.json << 'EOF'
{ "colors": { ... }, "typography": { ... } }
EOF

# 4. Run iterative design review (PERSONA IS REQUIRED)
./run.sh review \
  --persona brandon-bailey \
  --screenshots ./screenshots/ \
  --reference ./screenshots/reference/ \
  --tokens ./design-tokens.json \
  --rounds 2 \
  --provider claude

# 5. Apply recommendations
# Read review_output/round2_final.md for actionable changes
```

## Integration with review-code

After design review produces token changes, you can:
1. Update your style files (QML, CSS, etc.) based on recommendations
2. Run `review-code` to validate the implementation changes
3. Iterate until both design and code reviews pass

## Allowed Tools

- Bash (for provider CLI invocation)
- Read (for loading tokens and configs)
- WebFetch (for fetching remote design specs)

## Notes

- Screenshots should be captured at 1x scale for consistent analysis
- Include the full UI context (not just cropped elements) for better spatial reasoning
- Also include cropped and zoomed screenshots for localized issues when available; broad context alone is usually not enough for strong UI critique
- Reference images help but aren't required. However, screenshots ARE required — the skill will fail without them.
- Large images are automatically resized to fit provider limits
- Do not treat internal metrics, decorative pipeline graphics, or implementation details as user-facing UX value without visual justification.
- If a design call cannot be defended after visual inspection, stop and escalate with an external web LLM bundle instead of pushing through.
- Prefer packaging only the relevant components for the UX under review; do not dump the whole repo unless the review genuinely requires it.
- For browser upload flows with zip limits, use `bundle-upload` so the final archive stays within a small file-count budget.

## Common Mistakes

### WRONG: Running a review without specifying --persona
```bash
./run.sh review --screenshots ./screenshots/  # fails validation, generic feedback
```

### RIGHT: Always specify persona for focused, domain-expert review
```bash
./run.sh review --persona brandon-bailey --screenshots ./screenshots/
```

### WRONG: Running review without screenshots (impossible)
```bash
./run.sh review --persona brandon-bailey --tokens ./tokens.json  # no screenshots!
```

### RIGHT: Capture screenshots first, then review
```bash
flameshot full --path ./screenshots/current.png
./run.sh review --persona brandon-bailey --screenshots ./screenshots/
```

### WRONG: Adding direct model aliases as review-design providers
```bash
./run.sh review --persona brandon-bailey --provider gemini-2.5-flash --screenshots ./ui/
# review-design providers are not raw model IDs
```

### RIGHT: Use scillm/default VLM routing
```bash
./run.sh review --persona brandon-bailey --screenshots ./ui/
./run.sh review --persona brandon-bailey --provider vlm --screenshots ./ui/
# both route through scillm model: "vlm"
```
