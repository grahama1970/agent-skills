---
name: review-plan
description: >
  Validate task files before orchestration. Verifies codebase claims,
  skill overlap, task ordering, definition-of-done assertions, and
  skill chain validity. Use before /orchestrate to prevent wasted effort.
triggers:
  - review plan
  - validate tasks
  - check plan
  - review task file
  - plan review
  - validate plan
  - audit plan
  - check task file
allowed-tools: [Bash, Read, Glob, Grep, Task]
provides:
  - plan-validation
  - claim-verification
  - chain-validation
composes:
  - assess
  - memory
  - recommend-skill-chain
  - skills-ci
  - task-monitor
read_before_use:
  - review_plan.py
taxonomy:
  - precision
metadata:
  short-description: Validate task files before orchestration
  version: "1.0.0"
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# /review-plan

Validate task files before `/orchestrate` runs them. Catches errors that waste hours of agent time.

## Pipeline Position

```
/plan → /review-plan → /orchestrate
```

## Usage

```bash
# Review a task file
./run.sh review 01_MIGRATION_PLAN.md

# Review with JSON output
./run.sh review 01_MIGRATION_PLAN.md --json

# Review with auto-fix suggestions
./run.sh review 01_MIGRATION_PLAN.md --suggest-fixes

# Quick check (claims + DoD only, skip chain validation)
./run.sh check 01_MIGRATION_PLAN.md
```

## NON-NEGOTIABLE: Blind Adversarial Testing

Every implementation task MUST have a **blind test that the coding agent cannot see**. This is the #1 check. No exceptions.

The implementing agent sees ONLY pass/fail output — never the test source, assertions, or expected values. This prevents the agent from gaming or faking success.

- **GOOD**: `test-lab/run.sh verify-task 3.1 .pi/extensions/ --domain skills` — agent sees only pass/fail
- **GOOD**: `sanity.sh` exits 0 — pre-existing harness agent didn't write
- **GOOD**: `skills-ci scan` — external validator
- **WARN**: `uv run pytest tests/test_auth.py` — runnable but agent may have written the test (not blind)
- **BAD**: "verify it works"
- **BAD**: "Definition of Done: feature is implemented"

The test must be **adversarial** — the agent is blind to the test code and can only see output. `/plan` MUST specify `/test-lab` or `sanity.sh` tests. `/review-plan` MUST enforce blindness. `/orchestrate` MUST NOT run tasks without blind tests.

## What It Checks

### 0. Phase 0 Skill Discovery Enforcement (FAIL grade)
Every task file MUST have a `## Capability Overlap` section proving the planner ran Phase 0 before writing tasks. This section must document:

1. **`/memory recall` results** — what prior solutions exist for this problem domain
2. **`skills-manifest.json` scan** — which existing skills were checked for composability
3. **Decision matrix** — for each piece of functionality, whether the plan will CALL, IMPORT, EXTEND, GLUE, or CREATE (see `/plan` Composition Principle)
4. **Anti-silo justification** — for any CREATE-category task, why no existing skill covers it

**Grading:**
- **PASS**: Section exists with all 4 elements, CREATE tasks justified
- **WARN**: Section exists but missing anti-silo justification for CREATE tasks
- **FAIL**: Section missing entirely — plan was not properly vetted

**Catches**: Agent skips `/memory recall` and builds bespoke `quarantine.py` when `defer_pdf()` already exists. Agent creates new `QuarantineQuestion` dataclass when `/interview` Question is importable. Agent writes new screenshot renderer when `/pdf-screenshot` and `pdf_bridge.render_page_image()` already do this.

Without this section, `/orchestrate` MUST NOT proceed — the plan risks creating parallel infrastructure that duplicates existing skills.

### 1. Blind Adversarial Test Enforcement (FAIL grade)
Every implementation task must have a blind test the coding agent cannot see. Tasks using `/test-lab` or `sanity.sh` get PASS. Tasks with runnable tests the agent may have written get WARN. Tasks with no test get **FAIL**. This blocks `/orchestrate` from proceeding.

### 2. Claim Verification
Parse file paths, tool names, function names, and class names from task bodies. Verify they exist in the codebase.

**Catches**: "Edit `src/auth/handler.ts:45`" when the file doesn't exist, or tool names that don't exist in the target harness.

### 3. Skill Overlap Detection
Cross-reference task descriptions against `skills-manifest.json`. Flag tasks that propose building what an existing skill already does.

**Catches**: "Build a web scraper" when `/fetcher` + `/dogpile` already handle this.

### 4. Task Ordering Analysis
Build a dependency DAG from task references (`Task 3 depends on Task 1`). Detect cycles, missing dependencies, and parallelizable tasks not grouped.

**Catches**: Task 5 references output from Task 7 (ordering violation).

### 5. Definition of Done Audit
Parse DoD fields. Check if referenced test files/commands exist. Flag vague assertions.

**Catches**: `Definition of Done: "verify it works"` (vague), or `test_auth.py::test_login` when that test file doesn't exist.

### 6. Chain Validation
Extract `/skill-name` chains from task bodies. Run through `/recommend-skill-chain` to validate composition bonds.

**Catches**: `/create-stems /create-score` chain that has no logical bond (stems are audio separation, score is music generation — they compose but via `/create-music`, not directly).

### 7. Tool Name Audit
Check if tasks reference correct tool names for the target harness (Pi vs Claude Code).

**Catches**: Task says "use the Glob tool" but Pi's equivalent is `find`.

### 8. Prompt-Lab Enforcement (WARN grade)
Scan task descriptions for LLM prompt authoring (keywords: "prompt", "system message", "LLM instruction", "few-shot", "chain of thought"). Any task that writes or modifies LLM prompts MUST route through `/prompt-lab` for iterative evaluation. Hand-written prompts in code are banned.

- **PASS**: Task explicitly references `/prompt-lab` for prompt creation/iteration
- **WARN**: Task involves LLM prompts but doesn't mention `/prompt-lab`
- **N/A**: Task has no LLM prompt component

**Catches**: Agent hand-writes a system prompt in a Python string literal instead of using `/prompt-lab` to iterate and evaluate it. This produces untested prompts that silently degrade LLM output quality.

### 9. Convergence Loop Validation (FAIL grade)
Scan task descriptions for convergence/improvement loops (keywords: "convergence", "improvement loop", "iterate until", "max_rounds", "threshold", "remediation"). Any task that defines an iterative loop MUST satisfy ALL of:

1. **Dual rationale**: If the loop involves personas (client + designer, QA + developer), the plan MUST produce first-person rationale from BOTH personas. Plans with only one persona voice get **FAIL**.
2. **Active remediation**: The loop MUST specify what changes between rounds and who makes the change. A loop that reviews but never edits is fake. Plans missing a "who remediates" step get **FAIL**.
3. **Module separation**: Loop orchestrator and dialogue/remediation logic MUST be in separate files. Plans that put both in one file get **WARN** (will hit 800-line hook limits).
4. **Context isolation**: Per-component dialogues that involve large artifacts (HTML mockups, PDF pages) SHOULD use `/subagent-service` for protected context. Plans missing this get **WARN**.

- **PASS**: Loop has dual rationale, active remediation, separate modules, context isolation
- **WARN**: Loop exists but missing module separation or context isolation
- **FAIL**: Loop has no remediation step, or only one persona voice in a two-persona design

**Catches**: Agent builds a convergence loop that screenshots → reviews → checks threshold → loops — but nothing changes between rounds. The loop runs max_rounds and fails every time because no remediation step exists. Also catches design boards with only client rationale and no designer voice.

### 10. Design Board Clarity Enforcement (WARN/FAIL grade)
Scan task descriptions for design/UX tasks that reference `/create-design-board`. Any task producing a design board MUST satisfy ALL of:

1. **Per-pane mockups**: Every view requires N+1 images (1 composite + N per-pane mockups). A single composite screenshot per view is not sufficient — reviewers need to see each pane in isolation to give targeted feedback.
2. **Image-dialogue-pane structure**: Board content must follow the pattern: mockup image → persona dialogue about that pane → next pane. Walls of specification tables before any visual are banned.
3. **Specs in collapsed blocks**: Specification tables (dimensions, spacing, color tokens, typography) MUST live inside `<details>` blocks, not inline. Inline spec tables push mockups below the fold and break visual review flow.
4. **Line count cap**: Boards exceeding 800 lines likely contain duplicated rationale or inline specs that should be collapsed. This triggers WARN.
5. **No composite-only views**: Every view MUST have per-pane mockup images. A view with only a single composite screenshot and no per-pane breakdowns triggers FAIL.

**Grading:**
- **PASS**: All views have per-pane mockups, board follows image-dialogue-pane structure, specs in `<details>`
- **WARN**: Board exists but exceeds 800 lines, or some views lack per-pane mockups
- **FAIL**: Design tasks produce only ASCII wireframes or single composites with no per-pane images

**Catches**: Agent generates a 1400-line design board where every view has one composite screenshot, dialogue is buried after 50-line ASCII wireframes, and spec tables dominate — the human can't follow it pane-by-pane.

### 11. Feature Reality Check Enforcement (WARN grade)
Scan design board tasks for major UI features (new views, panels, workflows). Any feature with persona dialogue SHOULD have a preceding "Reality Check" subsection with `/dogpile` research findings.

- **PASS**: All major features have a reality check subsection citing `/dogpile` research
- **WARN**: Features exist without reality checks — risk of designing features nobody will use
- **N/A**: Plan has no design board or UI features

**Catches**: Agent designs an elaborate D3 provenance graph feature that `/dogpile` would have killed in 30 seconds — no compliance tool uses them. Hours of design and implementation effort wasted on a feature the practitioner persona would reject.

### 12. Shared Component Entry Point Audit (WARN grade)
Scan design boards for components referenced from multiple views (slide-overs, panels, modals). Each entry point must be documented in its respective view section.

- **PASS**: Shared components have entry points documented in every referencing view
- **WARN**: Component is referenced from multiple views but entry points not documented
- **N/A**: No shared components in the design

**Catches**: Agent builds an evidence case slide-over panel accessible from V8, V9, and V4, but only documents the trigger in V8. Other agents implementing V9 and V4 don't know the panel exists or how to trigger it.

### 13. Human Interjection Protocol (WARN grade)
If the plan includes persona dialogue boards, check that the "Persona Dialogue Protocol" is documented in the board's preamble (before View 1). This protocol enables human course correction mid-conversation.

- **PASS**: Dialogue protocol documented with `**Human** (interjection)` format
- **WARN**: Persona dialogues exist but no interjection protocol documented
- **N/A**: Plan has no persona dialogues

**Catches**: Agent runs persona dialogues as a closed loop — human can't interject domain knowledge or direct personas to `/dogpile` for research. Personas make assumptions that the human would have corrected if the protocol existed.

### 14. Visual Verification Enforcement for UX Tasks (FAIL grade)
Scan plan metadata for `plan_type: design` or `plan_type: hybrid`, or task descriptions containing UX keywords (TSX, component, view, tab, dashboard, React). Any plan with UX tasks MUST satisfy ALL of:

1. **Dev server launch**: The plan MUST include an early task (Wave 0 or pre-task) that starts the dev server (`npm run dev`) AND opens the browser (`xdg-open`). Without this, the agent builds blind.
2. **`/test-interactions` manifest**: The plan MUST include a concrete interaction manifest listing every design element to verify. Each view/component gets a manifest entry with: tab name, expected data (collection name + minimum row count), interactions to perform (click, filter, sort), and expected visual outcome. Plans without a manifest get **FAIL** — `/test-interactions` without a manifest is meaningless.
3. **Per-view `/test-interactions`**: Every task that creates or modifies a view/component MUST reference the manifest and run `/test-interactions` against its entries. This captures a screenshot proving the view renders real data — not just that TypeScript compiles.
4. **Data verification before CSS**: Every view task MUST verify the data endpoint returns real documents BEFORE writing component code. A `curl` to `/api/memory/list` or `/api/memory/recall` proving non-zero results must appear in the task's implementation steps or as a pre-condition.
5. **"npm run build succeeds" is NOT a valid DoD for UX**: Build success only proves types compile. It says nothing about whether the view renders, shows data, or is visually correct. DoD for UX tasks MUST reference `/test-interactions` manifest entries, a screenshot, or a visual assertion.

**Manifest example** (must be in the plan YAML or a referenced file):
```yaml
test_manifest:
  - tab: Controls
    collection: sparta_controls
    min_rows: 10
    interactions: [click_row, filter_framework, sort_column]
    visual: "Table shows 100 rows, framework pills colored, detail slide-over opens"
  - tab: QRAs
    collection: sparta_qra
    min_rows: 5
    interactions: [keyboard_A, keyboard_R, navigate_next]
    visual: "Card shows question/answer/reasoning, tier badges visible, grounding bar colored"
```

**Grading:**
- **PASS**: Dev server launch task exists, manifest covers every view, each view task references manifest, DoD includes visual assertions
- **WARN**: Dev server launch exists but manifest is incomplete (missing views)
- **FAIL**: No manifest, no dev server launch, DoD is only "build succeeds", or no `/test-interactions` anywhere in a design plan

**Catches**: Agent builds 8 React views, runs `npm run build`, declares success — but no dev server was running, no browser was open, no screenshots were taken, and every page is empty because the data hooks call endpoints that don't exist or return 0 results. Hours of CSS generation with zero visual verification. Also catches: agent runs `/test-interactions` without a manifest, so it screenshots blank pages and declares PASS because it has no expected outcomes to compare against.

**Manifest completeness check**: `/review-plan` MUST verify the manifest covers every view in the plan. For each task with `plan_type: design`, count the view/tab tasks and compare against `test_manifest` entries. If any view lacks a manifest entry, that's a FAIL. If a manifest entry lacks `interactions` or `visual`, that's a WARN. The manifest is the contract — it defines what "done" looks like BEFORE code is written. Incomplete manifests produce incomplete verification.

### 15. Code-Runner Worktree vs Live Server Mismatch (FAIL grade)
Scan every task with `runner: "code-runner"`. If the task's `definition_of_done.command` contains `curl`, `wget`, `http://localhost`, or any HTTP endpoint call, the task **MUST FAIL**.

**Why:** Code-runner executes in a git worktree — an isolated copy of the repo. The running dev server (Express, Vite, etc.) serves from the **main working directory**, not the worktree. Any DoD that curls a live endpoint will always hit the old code and fail, wasting all code-runner rounds.

**Detection:**
- Parse `definition_of_done.command` for each `code-runner` task
- If it contains `curl`, `wget`, `http://localhost`, `https://localhost`, or any URL pattern → **FAIL**
- Also check `tests` array entries for the same patterns

**Grading:**
- **PASS**: No code-runner task has a live-server DoD
- **FAIL**: Any code-runner task has `curl`/HTTP in its DoD command

**Fix:** Change the task to `runner: "scillm"` (one-shot edit to working directory) + a separate `runner: "local"` task that restarts the server and runs the curl verification. Or split into: (1) code-runner writes the file with a file-based DoD (`grep -q 'routeName' file.ts`), (2) local task restarts server and curls.

**Catches:** Agent writes Express endpoints via code-runner. Code-runner edits `server/index.ts` in a worktree. DoD runs `curl http://localhost:3001/api/posture/frameworks`. The running Express server doesn't see the worktree edits. Curl returns 404. Code-runner retries 5 rounds, fails every time. Hours of LLM tokens burned on an impossible DoD.

## Review Output

```
# Review: 01_MIGRATION_PLAN.md

## Summary
- Tasks: 24
- Phases: 11
- PASS: 18 | WARN: 4 | FAIL: 2

## FAIL

### Phase 0: Skill Discovery
- ISSUE: Missing `## Capability Overlap` section — no evidence /memory recall or skills-manifest.json was checked
- FIX: Run `/plan` Phase 0 gate before writing tasks

### Task 8.0: Line 416
- CLAIM: "packages/coding-agent/src/core/skills.ts" exists
- REALITY: File exists but function `parseFrontmatter<T>()` is at line 312, not as described
- FIX: Update line reference

### Task 5.3: Line 260
- CLAIM: "Edit a .pi/skills/**/*.py file"
- DOD: "Can't proceed past skill edits without CI scan"
- ISSUE: No test command specified — how do we verify the gate fires?

## WARN

### Task 9.2: Line 624
- OVERLAP: Task proposes building chain recall but /recommend-skill-chain already does this
- SUGGEST: Wire existing skill instead of rebuilding

### Phase 3: Line 145
- ORDERING: Task 3.1 (stop-gates.ts) depends on tool_call API but Task 5.1 (validate enforcement) comes after
- SUGGEST: Move validation before hook creation
```

## Grading

| Grade | Criteria |
|-------|----------|
| **PASS** | Phase 0 documented, all claims verified, DoD has runnable assertions, chains valid |
| **WARN** | Minor issues: stale line numbers, possible overlap, weak DoD, CREATE tasks missing justification |
| **FAIL** | Missing Phase 0 section, claim doesn't match codebase, missing DoD, broken dependency chain |

## Integration

- `/plan` should run `/review-plan` before marking a task file as ready
- `/orchestrate` should run `/review-plan` as a pre-hook (Task 10.2 in migration plan)
- `/best-practices-plan` provides the rule set this skill validates against

## Dependencies

- `skills-manifest.json` — for skill overlap detection
- `/memory recall` — for prior plan review patterns
- `/recommend-skill-chain` — for chain validation (optional, degrades gracefully)
