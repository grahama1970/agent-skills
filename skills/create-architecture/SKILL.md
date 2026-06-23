---
name: create-architecture
description: >
  Drive a WebGPT clarification-then-creation loop. The project agent supplies a
  HANDOFF.md, GOAL.md, rendered HTML/CSS progress report (required brownfield), and scoped creation brief,
  answers WebGPT clarifying questions until WebGPT decides it has enough
  information, then receives a finished-file zip bundle for isolated sanity
  check and port into the real tree. Use for a new project, module, or single
  function/harness rung in an existing repo.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
metadata:
  short-description: Handoff/goal plus WebGPT Q&A until ready, then solution zip
---

# create-architecture

> **Not Excalidraw / UX Lab.** This skill does **not** generate Excalidraw diagrams,
> `pipeline.yaml` UX Lab boards, or `localhost:3002/#architecture` views. If you only
> see that shorter diagram workflow, you have a **stale skill attachment** — read the
> canonical `skills/create-architecture/SKILL.md` in the repo.
>
> **Human verification surface:** the rendered HTML/CSS progress report (path in `GOAL.md`). That is where the human checks your work — engagement log, gaps table, sanity table, diagrams. Chat summaries do not count.
>
> **This skill:** WebGPT **creates** a scoped missing implementation slice as a
> **solution zip**; the project agent ports it and proves it with tests/sanity.

## Document map (read order)

| Section | Purpose |
|---------|---------|
| Creation transport / Invocation | Create vs review; `$ask` composes `$surf` |
| Runnable entrypoint | Exact commands when no `run.sh` exists |
| Round terminology | Clarification round vs engagement round |
| Creation bundle packaging | How to pack HANDOFF/GOAL for the browser tab |
| Handoff / GOAL / Rendered goal | What to author before WebGPT |
| **Report enforcement** | `REPORT_ENFORCEMENT.md` — **blocking** closure checklist; HTML before gap-report |
| Rendered goal page (HTML/CSS) | `RENDERED_GOAL_PAGE.md` — where the living report lives; `GOAL_PAGE.html` in zip |
| Per-round rendered progress | HTML/CSS progress update + CDP proof after each slice |
| Multi-round engagement | One slice default; combined zip when GOAL scopes a cluster |
| Solution zip layout + download | What WebGPT returns; how to capture it |
| Multipart file-body recovery | `CONTINUE_FOR_PART_N` sentinel handling |
| Port and apply | Brownfield integration rules |
| Required WebGPT Request Shape | Copy-paste template (same content as packaging) |

Older duplicate headings (`## Report enforcement (blocking)

Full checklist: **`REPORT_ENFORCEMENT.md`**.

The HTML/CSS progress report answers two questions for the human and the next
WebGPT round:

1. **What was fixed** (this slice, port deltas, proof commands + exit codes)
2. **What is still outstanding** (gaps table, roadmap, diagram truth)

**Closure order (non-negotiable):**

```text
proof on real stack → update HTML report → gap-report.md → HANDOFF → say "closed"
```

Reject the round if:

- only `gap-report.md` or chat was updated,
- gaps table says LIVE but engagement log has no row,
- diagrams still show NOT BUILT for LIVE paths,
- LIVE claimed without recorded live commands in the report.

## Clarification loop until WebGPT is ready` and
`## WebGPT Clarification And Creation Loop`) describe the same loop; prefer the
**Runnable entrypoint** + **WebGPT Clarification And Creation Loop** sections.

## Skill Metadata

Triggers:

- create architecture
- architecture before coding
- webgpt clarification loop
- finished-file zip bundle
- soup to nuts module
- design this harness rung
- implementation contract before coding
- webgpt build the solution

Runtime self-improvement: basic.

Provides:

- task-planning
- webgpt-creation-artifacts (ask/surf transport receipts; not review verdicts)
- skill-scaffolding

Composes:

- ask
- handoff

Complies:

- best-practices-skills
- best-practices-plan
- best-practices-python

Taxonomy:

- precision
- resilience

Use this skill when the missing deliverable is the architecture artifact and a
finished-file solution bundle. The job is to run a `$ask WebGPT` clarification loop: send `/handoff` plus a
scoped creation brief, answer clarifying questions until WebGPT decides it has
enough information, then receive a zip bundle containing the entire proposed
solution as finished files.
The project agent uses that bundle as greenfield sanity-check input, then
implements locally, fixes mechanical bugs, tests, and reports integration gaps.

This skill exists because project agents are weak at greenfield architecture and
greenfield code invention, but comparatively good at running code, applying
concrete files, fixing light mechanical bugs, and producing deterministic proof.
A project agent using this skill is not allowed to bespoke the greenfield code
or invent the architecture locally.

Do not return a review verdict. Do not lead with critique. Do not produce
`PASS`, `NEEDS_CHANGES`, `BLOCKED`, or `INSUFFICIENT_EVIDENCE`. The output is an
implementation contract and code solution that can later be reviewed.

## Creation transport vs review transport

`$create-architecture` asks WebGPT to **create** the scoped solution (questions
first, then a finished-file zip). It is **not** a review gate.

### Bundle terminology (in vs out)

Do not call both artifacts "the zip bundle" without naming direction.

| Artifact | Direction | Who builds it | Contents |
|----------|-----------|---------------|----------|
| **Creation bundle** | Project agent → WebGPT | Project agent | `HANDOFF.md`, `GOAL.md`, rendered goal page, code snippets, constraints, acceptance gates |
| **Solution zip** | WebGPT → project agent | WebGPT | Finished source files, tests, manifest, `prompt_improvements` |

**Creation bundle in; solution zip out.**

### Invocation (`$ask` composes `$surf`)

| Layer | Entrypoint | Role |
|-------|------------|------|
| **Skill contract** | `$create-architecture` | HANDOFF + GOAL + creation brief; never invent greenfield locally |
| **Orchestration** | `$ask webgpt` — `skills/ask/run.sh ask "webgpt …"` | Submits creation bundle, binds tab/project, attaches files, preserves ask artifacts |
| **Transport** | `$surf` — `skills/surf/run.sh webgpt.submit` | Controlled-tab submit, sentinel proof, raw/clean/meta outputs |

**Preferred path:** `$create-architecture` → `$ask webgpt` → `$surf webgpt.submit`.

The `$ask` skill defaults to orchestration over raw `$surf`. Under
`$create-architecture`, calling `$ask webgpt` is the normal path — not a
violation of that rule. Use raw `$surf webgpt.submit` only for transport
debugging when ask artifacts or attach behavior need isolation.

Direct `surf webgpt.submit` is acceptable for transport debugging only. Normal
rounds should go through `$ask` so tab binding, zip attach, and artifact
directories stay consistent.

| Transport | Use for create-architecture? | Why |
|-----------|------------------------------|-----|
| `$ask webgpt` + creation bundle | **Yes (preferred)** | Composes `$surf`; preserves artifacts; creation framing |
| `surf webgpt.submit` + creation bundle | **Yes (debug)** | Same transport leaf; use when diagnosing tab/sentinel issues |
| `./run.sh webgpt-review` | **No** | Review gate — injects verdict JSON (`PASS` / `BLOCKED` / etc.) |

Judge round success by **response shape**, not by any `verdict` field:

- **Round 1..N success**: numbered clarifying questions, or explicit
  "I have enough information to build"
- **Final round success**: downloadable/capturable finished-file zip + manifest
- **Routing failure**: review verdict JSON, `INSUFFICIENT_EVIDENCE` review mode,
  prose description of a zip without the zip, **two or more finished files pasted
  inline without a zip**, **generic or unscoped zip filename**, or partial design
  with open choices

If a creation round is submitted through `webgpt-review` by mistake, ignore the
parsed `verdict` field. Re-submit through `$ask webgpt` (preferred) or
`surf webgpt.submit` before trusting the exchange for implementation.

## Runnable entrypoint (no `run.sh`)

This skill has **no** `./run.sh`. One creation round is assembled manually:

```bash
# 0. Preflight tab (required)
cd skills/surf
./run.sh webgpt.preflight --tab-id <id> --expect-url "<conversation-url>" --no-activate --json

# 1. Build creation bundle on disk (see ## Creation bundle packaging)
# 2. Submit (preferred)
cd skills/ask
./run.sh ask "webgpt Clarify then create scoped solution per attached bundle" \
  --webgpt-project <name> \
  --webgpt-tab-id <id> \
  --webgpt-url "<conversation-url>" \
  --json

# 3. Save artifacts under create-architecture/<run-id>/
# 4. Download/capture {project}-{slice-id}-solution.zip (keep name), sanity, port, test, gap report
```

`$create-architecture` = **skill contract** + **handoff/goal artifacts** + **`$ask webgpt`**
+ **`$surf` leaf transport**. There is no fourth wrapper script.

## Round terminology (do not conflate)

| Term | Scope | Ends when |
|------|-------|-----------|
| **Clarification round** | Inside one engagement / one `GOAL.md` slice | WebGPT says it has enough information to build |
| **Engagement round** | One full slice lifecycle | Proof **LIVE**, **HTML report updated** (`REPORT_ENFORCEMENT.md`), `gap-report.md` written |

Multiple **clarification rounds** may happen inside a single engagement. Multiple
**engagement rounds** happen when P0 → prove → P1 → prove until the gaps table
is green.

## Creation bundle packaging (browser-readable)

ChatGPT cannot read bare repo paths. The creation bundle must be **inlined text**
or an attachment ChatGPT can open.

### Preferred: one concatenated markdown file

Build `creation-bundle.md` with labeled sections:

```markdown
# Clarify, Then Create Scoped Solution
## Objective
## HANDOFF.md
(paste full handoff)
## GOAL.md
(paste full goal)
## Rendered goal reference
(paste HTML excerpt, screenshot path description, or attach HTML separately)
## Current local evidence
## Relevant snippets
## Constraints / Non-goals / Required output
```

Pass the path in the `$ask webgpt` question, or attach via `$surf --attach-file`
when using surf directly. `$ask` may also inline referenced files from the prompt.

### Alternate: zip attach (WebGPT only, ≤5 member files)

`surf webgpt.submit --attach-file` allows **one** zip with **≤5** files
(`SURF_WEBGPT_MAX_ZIP_FILES`, default 5). Pack logically, for example:

| # | File | Contents |
|---|------|----------|
| 1 | `CREATION_BRIEF.md` | Objective, constraints, required output framing |
| 2 | `HANDOFF.md` | Incoming state packet |
| 3 | `GOAL.md` | Target slice contract |
| 4 | `GOAL_PAGE.html` | Rendered goal (or one screenshot `.png`) |
| 5 | `SNIPPETS.md` | Combined code excerpts for touched paths |

If you need more than five logical documents, **merge into fewer files** or use
the concatenated markdown approach. Do not exceed the zip member limit.

### WebGPT project tab binding

Persist tab identity per project with `--webgpt-project <name>` (stored under
`~/.pi/webgpt-projects/<name>.json`). Always preflight before submit.

**Example (memory project):**

```bash
./run.sh ask "webgpt …" \
  --webgpt-project memory \
  --webgpt-tab-id 837354858 \
  --webgpt-url "https://chatgpt.com/g/g-p-6a2421e493588191b3cdba22b035ed3d-memory/c/6a3a9e94-954c-83ea-a90c-e9b69993ca9c" \
  --json
```

Tab ids can change after browser restarts. **Preflight + `--expect-url` every
round.** Update the project json when the human rebinding a tab.


## Handoff, Goal, And Creation Brief

The project agent's first job is not to invent the solution. It is to give WebGPT
what a fresh incoming agent needs:

1. Run `/handoff` and attach `local/HANDOFF.md` (or project-equivalent handoff).
2. Create or refresh `GOAL.md` from the named skill, project knowledge, existing
   docs, current code, and the human's latest objective.
3. If the project has a non-trivial flow or an existing visual reference, create
   or attach a rendered HTML/CSS goal page that makes the operational target
   inspectable.
4. Add a **creation brief** on top of the handoff and goal:
   - scoped slice (module, function, harness rung, or project),
   - constraints and non-goals,
   - acceptance tests,
   - explicit instruction that round 1 should return **only clarifying questions**
     if anything material is still unclear.

Together, handoff + goal + optional rendered goal page + brief = clear
instructions plus structured project context. Do not send bare paths, vague
goals, or ad-hoc bullet lists when a handoff or project-knowledge source exists.

The `GOAL.md` plus rendered goal page is the primary creation target. Its job is
to let WebGPT see the desired operational system, compare that target against the
current local evidence, decide what is missing, and then create the finished
files needed to close that gap. The creation brief scopes the slice; it should
not replace the goal artifact.

For existing projects, a rendered HTML/CSS goal page should work like a
source-derived routing or evidence-flow document: it should make the desired
state machine, ownership model, acceptance gates, and missing behavior obvious
enough that WebGPT can return a concrete zip bundle instead of asking the project
agent to invent architecture locally.

### HANDOFF.md Requirement

`HANDOFF.md` is the incoming-agent state packet. It should answer:

- what exists now,
- what was recently changed,
- what commands or artifacts prove the current state,
- what is broken or missing,
- what files are likely in scope,
- what must not be disturbed, and
- what the next build step is.

If the `/handoff` skill cannot run in the current repo, synthesize a local
handoff from the named skill, project knowledge, git status, relevant files, and
recent proof artifacts. Mark it as synthesized.

### GOAL.md Requirement

`GOAL.md` is the target-state contract. It should answer:

- the primary product/system question,
- goals and non-goals,
- source-of-truth boundaries,
- implemented vs intended vs missing behavior,
- runtime invariants,
- acceptance gates,
- proof artifacts required before green,
- next smallest useful artifact, and
- the project-agent/WebGPT division of labor.

For an existing project, derive `GOAL.md` from the relevant `SKILL.md`,
`PROJECT_KNOWLEDGE.md`, existing docs, and current code. Do not let WebGPT infer
the goal from a vague chat transcript.

`GOAL.md` must state what WebGPT is expected to fix or create in the returned
zip bundle. If the goal document only describes the project but does not name the
missing scoped solution, the project agent must revise it before submitting the
creation round.

### Rendered goal page location

See **`RENDERED_GOAL_PAGE.md`** in this skill directory for:

- where the HTML/CSS report lives (per-project, not a fixed global path),
- how it maps to `GOAL_PAGE.html` in the ≤5-file creation zip,
- update cadence vs `gap-report.md`,
- memory/SPARTA example (`docs/SPARTA_ROUTING_EVIDENCE_CASE_FLOW.html`).

### Rendered Goal Page Requirement

> **Required for brownfield.** See `REPORT_ENFORCEMENT.md` for blocking closure rules.

When the project is not starting from scratch and has an operational workflow,
state machine, evidence route, or UI-facing artifact, include an HTML/CSS
rendering of the goal when feasible. It does not have to be production UI. Its
job is to make the source-derived target easy for WebGPT and the human to
inspect.

For a non-trivial existing system, the rendered goal page must be similar in
breadth to a source-derived routing or evidence-case flow reference. A single
summary chart is not enough. WebGPT needs enough breadth to infer the missing
solution files without asking the project agent to invent architecture.

Rules:

- Render the goal from the same source facts as `GOAL.md`.
- Label each major capability as implemented, partial, intended, or missing.
- Include clear workflow/state-machine charts when the target involves routing,
  persistence, evidence gates, turn state, or tool orchestration.
- Include a source-derived numbered step model before or alongside charts.
- Include at least one end-to-end master flow and, when applicable, separate
  lane diagrams for persona/social, compliance/security, persistence, and
  runtime execution.
- Include decision gates with explicit pass/fail exits, not only happy-path
  boxes.
- Include endpoint/tool roles, authority boundaries, and what each component is
  forbidden to decide.
- Include acceptance gates, known missing behavior, known partial behavior, and
  proof artifacts required later.
- Include concrete worked examples that exercise the important branches.
- Include a technical appendix with schemas, state names, event names,
  deterministic keys, and command/test references when the scoped slice needs
  those details.
- Link the markdown goal, handoff, project knowledge, and relevant docs.
- Use browser/CDP verification for the rendered page before citing it as
  evidence.
- Treat the rendered page as context for creation, not proof of implementation.

The rendered page should be included to help WebGPT create the solution. It is
not merely a human-facing report. When it exists, the creation prompt should
explicitly tell WebGPT to use `GOAL.md` and the rendered page to identify the
missing files, state machines, schemas, tests, and integration points, then
return those as a finished-file zip bundle.

If the rendered goal page is too thin to answer "what exactly should WebGPT fix
or create?", stop and expand the goal packet before submitting the
create-architecture round.

### Per-Round Rendered Progress Requirement (blocking)

For existing systems, the HTML/CSS progress report is **the** deliverable humans
and WebGPT use to see what was fixed and what remains. **`gap-report.md` alone
does not satisfy this requirement.**

After every solution zip and local sanity/port attempt — **before** telling the
human the round is closed or starting the next WebGPT engagement — the project
agent **must** complete `REPORT_ENFORCEMENT.md` checklist on the rendered page.

**Hard stop:** if the report does not answer "what changed this round?" and
"what is still outstanding?", the round is **open**. Tests passing in chat
without report update does **not** count as closure.

The rendered page must show:

- an **engagement log** table (one row per round: slice id, what was fixed, port delta, proof commands + exit codes, artifact paths),
- the current slice id and WebGPT solution zip checksum (`bundle_filename`, not `source.zip`),
- the latest local proof commands and exact pass/fail results,
- a gaps/sanity table with rows marked **LIVE**, **PARTIAL**, or **MISSING**,
- which rows are implemented, intended, or still missing,
- the next scoped slice WebGPT should create,
- links or labels for `HANDOFF.md`, `GOAL.md`, `gap-report.md`,
  `sanity-report.md`, the solution zip, and any raw receipts,
- a source-derived numbered step model plus charts when routing, persistence,
  state machines, or tool orchestration are involved.

The page must be browser/CDP verified before it is cited as progress or sent
back to WebGPT:

```bash
~/.codex/hooks/verify-ui-cdp.sh --url <target-url> --name <surface>
cp /tmp/codex-ui-verification/<project>/<surface>/<timestamp>.read.json \
  .codex/ui-verification/latest.json
```

If the project has a stable local review URL, reuse it across rounds so the
human and WebGPT can compare progress. Example:

```text
http://127.0.0.1:8771/reviews/personaplex-deepgram/compliance-memory-decision-tree.html
```

The next WebGPT creation bundle must include the updated rendered page URL,
screenshot/read-json artifact path, and a concise statement of what changed
since the previous round. A stale rendered page is a creation-bundle defect.

## Report enforcement (blocking)

Full checklist: **`REPORT_ENFORCEMENT.md`**.

The HTML/CSS progress report answers two questions for the human and the next
WebGPT round:

1. **What was fixed** (this slice, port deltas, proof commands + exit codes)
2. **What is still outstanding** (gaps table, roadmap, diagram truth)

**Closure order (non-negotiable):**

```text
proof on real stack → update HTML report → gap-report.md → HANDOFF → say "closed"
```

Reject the round if:

- only `gap-report.md` or chat was updated,
- gaps table says LIVE but engagement log has no row,
- diagrams still show NOT BUILT for LIVE paths,
- LIVE claimed without recorded live commands in the report.

## Clarification loop until WebGPT is ready

WebGPT owns the readiness decision. The project agent does **not** decide when
enough information exists and does **not** skip to implementation locally.

```text
round 1: handoff + goal + creation brief -> WebGPT clarifying questions OR ready-to-build
round 2..N: project agent answers from repo evidence; human answers scope choices
exit: WebGPT states it has enough information -> solution zip bundle
```

Rules:

- If WebGPT asks clarifying questions, answer them and send the next round.
- Keep answering until WebGPT explicitly says it has enough information to create
  the scoped solution zip bundle.
- Only after that readiness signal may WebGPT return the finished-file zip.
- If WebGPT returns a review verdict, partial design, or prose description of a
  zip instead of questions or the zip, treat it as a routing failure and reissue
  with creation framing.
- While clarifying questions remain open, the project agent must not bespoke the
  scoped architecture or core logic locally.


## Scope (read first)

This skill is not limited to empty-repo greenfield work. The scoped slice may be:

- a **new project** or service,
- a **new module** in an existing repository,
- a **single function**, adapter, harness rung, or viewer component in a
  pre-existing project,
- a **soup-to-nuts implementation of that slice only** — not the whole monorepo.

In all cases the workflow is the same:

```text
project agent runs /handoff + GOAL.md + creation brief
  -> project agent attaches optional rendered HTML/CSS goal page when useful
  -> WebGPT asks clarifying questions (round 1..N)
  -> project agent answers; human answers scope choices
  -> WebGPT decides it has enough information
  -> WebGPT returns finished files + sanity check for the scoped slice
  -> project agent runs isolated sanity check
  -> project agent ports into the real project (no longer inventing)
  -> project agent verifies live and patches mechanical bugs
```

"Greenfield" in this skill means **WebGPT authors the slice from scratch in the
bundle**. It does **not** mean the destination repository is empty. After the
sanity check passes, implementation in the real tree is **integration from a
known-working reference**, not local invention.

## Multi-round engagement (until gaps are closed)

### Default: one slice per engagement

The **safe default** is one scoped slice per solution zip (for example P0:
compliance `/answer` ← `evidence_case`). That keeps port, live proof, and HTML
progress updates honest slice-by-slice.

### Allowed: single combined zip (WebGPT context is sufficient)

WebGPT is a **large-context creation model**. When the human or `GOAL.md`
explicitly scopes **multiple related priorities in one cluster**, one engagement
may return **one solution zip** containing all finished files for that cluster.

Use a combined zip when:

- the gaps share schemas, adjudication code, or test harnesses (one port pass),
- `GOAL.md` lists every file path, acceptance test, and non-goal for **each**
  priority in the cluster,
- the creation brief says **"return one zip for P2+P3+P4"** (or similar), and
- WebGPT confirms readiness after clarifying questions.

After a **combined** zip, the project agent still must:

- verify **each** acceptance gate independently (unit + live per priority),
- update the rendered HTML gaps table **per row** (not "all LIVE" until all pass),
- write one `gap-report.md` with a subsection per priority.

Do **not** split slices only because of an assumed WebGPT context limit. Split
when proof risk, unrelated subsystems, or human deferral require it.

After each solution zip (single-slice or combined):

1. Download or capture the zip, record checksum, and verify the manifest.
2. Extract into an isolated sanity directory and run bundle-level checks.
3. Port into the real project; fix mechanical integration defects only.
4. Run deterministic tests and live sanity gates named in `GOAL.md`.
5. **Update the HTML/CSS progress report** (`REPORT_ENFORCEMENT.md` checklist):
   engagement log, gaps table, sanity table, roadmap, diagram styling, last-updated date.
6. Write `gap-report.md` (receipt — must match HTML; never HTML-only-in-markdown).
7. Update `HANDOFF.md` next-slice pointer.
8. Verify the rendered page (HTTP serve or CDP); refresh `.codex/ui-verification/latest.json` if used.
9. If any required row is still **MISSING**, refresh `GOAL.md` for the **next**
   slice and start a **new** creation round (same WebGPT tab is fine).

Repeat until the goal document's acceptance gates are satisfied or the human
explicitly defers a row.

WebGPT creates; the project agent proves. A solution zip is not proof — only
passing local tests and live sanity counts.

## Project agent responsibilities

The project agent knows the repository. Before WebGPT builds anything:

1. Run `/handoff` and include the handoff report in the WebGPT bundle.
2. Create or refresh `GOAL.md` and include it in the WebGPT bundle.
3. Include the rendered HTML/CSS goal page when the project has an existing
   workflow or state machine that benefits from visual inspection.
4. Attach **relevant file contents** (not bare paths) for the touched slice.
5. Attach **live evidence** when it exists: receipts, test output, screenshots,
   failing commands, current PASS/FAIL rungs.
6. Write the **creation brief**: scoped slice, constraints, non-goals, acceptance
   tests, and round-1 questions-only instruction.
7. Answer every WebGPT clarifying question from repository evidence; escalate
   scope and acceptance choices to the human.
8. Repeat rounds until **WebGPT** decides it has enough information to create the
   solution zip bundle.
9. After the zip arrives: run the bundle **sanity check first**, then port,
   then **live verify** (`mocked: yes|no`, `live: yes|no`).

The project agent must **not** bespoke the scoped architecture or core logic
locally while WebGPT still has open clarifying questions or has not declared
readiness to build.

## Position In The Workflow

Use this sequence for early-stage architecture work:

```text
create-architecture
  -> $ask webgpt (composes $surf webgpt.submit) clarification loop
  -> WebGPT returns solution zip (finished files)
  -> Surf/download proof for zip bundle (solution zip)
  -> extract into isolated sanity directory
  -> greenfield sanity check
  -> local project agent applies/fixes code
  -> deterministic tests/probes
  -> report remaining gaps (MISSING / LIVE table)
  -> optional LOCAL review-plan / review-code (not WebGPT)
```

Use **local** `review-code` / `review-plan` only after the ported code exists
and live proof is recorded — never as a substitute for WebGPT creation, and never
by routing creation bundles through `webgpt-review`. If a user asks for an
architectural approach, do not send the request to a reviewer as though an
artifact already exists.

## WebGPT Clarification And Creation Loop

The project agent should not invent the greenfield architecture alone. Use
`$ask` to let WebGPT remove ambiguity first, then create the missing full
solution package as a zip bundle of finished files. The project agent must not
fill remaining greenfield gaps that WebGPT did not resolve; it should re-enter
the clarification loop.

Non-negotiable rationale:

```text
WebGPT owns greenfield solution creation.
Project agent owns execution, light bug fixes, local integration, and proof.
```

If the project agent is about to author new greenfield modules, schemas,
state machines, or UI/application code from scratch, stop and re-enter the
WebGPT clarification/creation loop.

Loop:

1. Build a browser-readable creation bundle from local facts:
   - `HANDOFF.md`,
   - `GOAL.md`,
   - optional rendered HTML/CSS goal page or screenshot reference,
   - user goal,
   - relevant files and current code snippets,
   - constraints and non-goals,
   - known failing evidence or missing behavior,
   - required acceptance tests,
   - explicit request for WebGPT to ask clarifying questions if anything is
     ambiguous,
   - explicit request that round 1 return **only clarifying questions**
     if any material ambiguity remains,
   - explicit request for the entire scoped solution only after ambiguity is gone.
2. Submit through a **creation** transport, not a review transport:
   - **Do NOT use** `./run.sh webgpt-review` for `$create-architecture`. That
     command injects review system prompts and requires
     `PASS|NEEDS_CHANGES|BLOCKED|INSUFFICIENT_EVIDENCE` JSON verdicts.
   - **Preferred:** `skills/ask/run.sh ask "webgpt …" --webgpt-tab-id <id>
     --webgpt-url <conversation-url> --webgpt-project <name> --json` with the
     creation bundle from `Required WebGPT Request Shape` below. `$ask` composes
     `$surf webgpt.submit` and preserves ask artifacts.
   - **Fallback/debug:** `skills/surf/run.sh webgpt.submit` with the same bundle
     (browser-safe markdown or small zip). Pass `--project <name>`, `--tab-id` /
     `--url`, and `--no-activate` when appropriate. Attach large files with
     `--attach-file`.
   - Also preserve a `create-architecture/<run-id>/` directory with handoff,
     goal, bundle hash, download proof, and gap report after porting.
3. If WebGPT asks clarifying questions, answer them from repository evidence,
   handoff facts, user-provided constraints, and memory. Do not guess missing
   external policy.
4. Repeat clarification rounds until **WebGPT** states it has enough information
   to create the scoped solution zip bundle.
5. Only after that readiness signal, require WebGPT to create the entire scoped
   solution as a zip bundle of finished files.
6. If WebGPT returns a verdict-first review instead of clarifying questions or
   the entire solution, treat the round as a routing failure and reissue the
   request with the clarification/creation framing.
7. If WebGPT returns a partial solution with unresolved architecture choices,
   re-enter the clarification loop. Do not let the project agent complete the
   greenfield design locally.
8. Save the returned zip bundle and inspect it as a greenfield candidate.
   Prove the bundle was actually downloaded or captured from the controlled
   WebGPT tab. A prose description of a zip is not enough.
9. Extract the bundle into a new isolated sanity directory outside the real
   project target path.
10. Run only sanity checks appropriate to a greenfield proposed approach, such as
   schema validation, static checks, smoke tests, rendered artifact checks, or a
   small local harness.
11. Once greenfield sanity checks pass, apply or port the finished files into
   the real project.
12. Fix mechanical integration bugs the project agent can fix.
13. Run deterministic project tests/probes.
14. Report exactly where the WebGPT solution falls short in local execution.

Do not claim project implementation success from WebGPT output. WebGPT resolves
the architecture ambiguity and creates a finished-file bundle. The bundle can
establish only greenfield sanity-check confidence, not production correctness.
Local project commands prove or disprove the real implementation.

## Ambiguity Exit Gate

Before accepting a solution round, WebGPT must have enough information to make
all material choices. The prompt must require one of two outputs:

```text
1. Clarifying questions required before solution.
2. No material ambiguity remains; here is the entire solution zip bundle.
```

If the answer contains unresolved choices such as "choose one," "consider,"
"maybe," "one option is," or missing target files/schemas/tests, do not treat it
as the final solution. Answer the ambiguity or ask WebGPT to make the choice
from the stated constraints.

The final WebGPT solution must include all code-level choices needed for the
project agent to implement mechanically, packaged as finished files. Diffs are
acceptable only when the target repository files were included in the bundle and
the patch applies mechanically.

## Required Output

Produce or obtain from WebGPT a complete implementation-ready solution with
these sections:

1. Goal
2. Non-goals
3. System boundaries
4. Authority boundaries
5. Canonical data ownership
6. Derived projections and rebuild rules
7. Schemas or API contracts
8. State machine
9. Lifecycle flow
10. Error handling and fail-closed behavior
11. Rollback/rebuild plan
12. Security, privacy, and retention constraints
13. Deterministic acceptance tests
14. Evidence required for a later review gate
15. Implementation sequence
16. File-by-file patch plan
17. Full code or precise diffs for every changed file
18. Migration/backfill steps, if persistence changes
19. Test fixtures and expected outputs
20. Exact commands to run
21. Known limitations and local bug-fix targets
22. Zip bundle manifest with every finished file, path, purpose, and checksum
23. Prompt improvements for the next project-agent turn

If the contract concerns persistent data, include deterministic keys, write
ownership, idempotency, conflict behavior, deletion behavior, and rebuild path.

If the contract concerns tools or agents, include the authority boundary:
which component may recommend, validate, execute, persist, or summarize.

If the contract concerns memory/retrieval, include retrieval text, structured
anchors, dense/vector lifecycle, graph edges, filters, and recall tests.

If the contract concerns UI, include the primary user decision, source of truth,
fail-closed missing-data behavior, and visual verification evidence required
later. Do not create dashboard theater.

## Hard Rules

- Make concrete choices.
- Preserve known constraints from the prompt.
- Mark speculative or policy-dependent choices explicitly.
- Ask for clarification only when the artifact cannot be created safely without
  missing external authority.
- Separate canonical source-of-truth data from derived projections.
- Include rollback or rebuild behavior for every persistent write.
- Include acceptance tests before coding.
- Include non-goals to prevent scope creep.
- Include evidence required for later review, but do not claim that evidence
  already exists unless it is supplied.
- Keep historical tool recommendations non-authoritative unless the active
  contract explicitly makes them current authority.
- For greenfield architecture, get clarification and the full solution from
  WebGPT first. The project agent's role is to apply, repair, test, and report
  gaps.
- Do not bespoke greenfield code under this skill. Do not locally invent modules,
  schemas, state machines, APIs, or UI flows that WebGPT did not supply.
- Require finished files before implementation: target paths, file contents,
  schemas, migrations, tests, fixtures, command lines, and a bundle manifest.
- Require download/capture proof before implementation: downloaded zip path or
  captured bundle path, checksum, extraction directory, and manifest check.
- If WebGPT omits code, schemas, tests, or material choices, run another
  clarification/creation loop rather than filling the greenfield gap locally.
- Require WebGPT to include a `prompt_improvements` section in every final
  solution bundle. The project agent must read it before the next WebGPT round
  or next implementation turn and must use it to make the next creation,
  clarification, sanity, or review request more specific.
- **Multi-file zip required:** when WebGPT produces **more than one**
  finished file (source, tests, patches, manifests, configs, etc.), it **must**
  return them as a **single downloadable solution zip** with `MANIFEST.json`.
  Inline paste of multiple files, sequential file attachments without a zip, or
  prose file listings are **routing failures** — reissue with this rule.
- **Report before closure:** no round is closed until the HTML/CSS progress
  report is updated per `REPORT_ENFORCEMENT.md`. Chat + `gap-report.md` alone fail.
- **Diagram truth:** LIVE capabilities must not use NOT BUILT / `gap` styling in diagrams.
- **Never `source.zip`:** do not rename downloads to `source.zip` locally;
  keep `{project}-{slice-id}-solution.zip` in the run dir.
- **Project-scoped zip name:** downloadable solution zip must be named
  `{project}-{slice-id}-solution.zip` and `MANIFEST.json` must include
  `bundle_filename` with the same value.

## Anti-Patterns

Do not produce gate-review language as the primary answer:

- "This looks good."
- "Needs changes."
- "PASS."
- "More evidence is needed."
- "The project should consider..."

Instead produce exact artifacts:

- exact schemas
- exact deterministic keys
- exact ownership rules
- exact states and transitions
- exact lifecycle steps
- exact acceptance tests
- exact rollback/rebuild rules
- exact failure behavior
- exact later review evidence
- exact file-by-file code changes
- exact finished-file bundle contents
- exact tests and expected command outputs
- exact prompt improvements for the next project-agent turn

WebGPT anti-patterns under this skill:

- returning two or more finished files without a single solution zip,
- listing file paths and contents in prose instead of a capturable zip,
- separate download buttons per file when one manifest zip is possible,
- generic zip names (`solution.zip`, `files.zip`, `bundle.zip`, `source.zip`)
  instead of `{project}-{slice-id}-solution.zip`,
- renaming the WebGPT download to `source.zip` in the run directory.

Project-agent anti-patterns under this skill:

- creating a greenfield implementation from local intuition,
- filling omitted WebGPT design choices with local guesses,
- turning a missing WebGPT bundle into a hand-written scaffold,
- writing the main architecture and then asking WebGPT to review it,
- claiming the project agent can finish the architecture because it is "simple.",
- updating `gap-report.md` or chat while leaving the HTML progress report stale,
- marking LIVE in a table cell without engagement-log narrative and proof commands,
- leaving master-flow diagrams styled as NOT BUILT for paths proven LIVE.

## WebGPT And Reviewer Routing

When escalating to WebGPT through `$ask`, frame the bundle as a clarification
and creation task:

```text
First ask any clarifying questions required to remove material ambiguity.
Once no material ambiguity remains, create an implementation-ready architecture
contract and complete code solution for this goal as a zip bundle of finished
files.
Do not review an existing implementation.
Do not return a verdict.
Return schemas, state machines, lifecycle, rollback, a zip bundle manifest,
finished files, tests, fixtures, commands, and known limitations.
If you produce more than one finished file, deliver **one solution zip** named
`{project}-{slice-id}-solution.zip` — do not paste multiple files inline, use
generic names (`solution.zip`), or separate attachments without a zip.
```

Use review framing only after the contract exists and the user asks for a gate,
plan review, or code review.

If WebGPT or another reviewer returns a verdict for an architecture-creation
request, treat that as a routing failure. Reissue the request with the
clarification/creation framing instead of accepting review output as the missing
artifact.

## Required WebGPT Request Shape

Copy-paste template for `creation-bundle.md`. Packaging rules (concat vs ≤5-file
zip, tab binding) are in **## Creation bundle packaging** above.

Before calling `$ask`, create a bundle with:

```markdown
# Clarify, Then Create Full Architecture And Code Solution

## Objective

## HANDOFF.md

## GOAL.md

## Rendered Goal Page Or Visual Reference

Explain that this goal page is the source-derived target model WebGPT should use
to decide what to fix or create. Include its verified URL, screenshot path, or
attached HTML. Ask WebGPT to compare the target model against the current local
evidence and return the missing scoped solution as files.

## Current Local Evidence

## Relevant Files And Snippets

## Constraints

## Non-Goals

## Required Output

If any material ambiguity remains, return only numbered clarifying questions.

If no material ambiguity remains, return a complete **solution zip bundle**
(not inline multi-file paste), not a review:

**If more than one finished file:** one zip + `MANIFEST.json` is mandatory.
**Zip download name:** `{project}-{slice-id}-solution.zip` (also set
`bundle_filename` in the manifest).

- architecture contract
- state machine
- schemas/API contracts
- file-by-file implementation as finished files
- zip bundle manifest with paths and checksums
- tests/fixtures
- commands
- rollback/rebuild steps
- known gaps
- prompt_improvements: what the project agent should include, remove, clarify,
  or phrase differently in the next turn so WebGPT can be more useful

Do not return PASS/NEEDS_CHANGES/BLOCKED.
Do not leave choices for the project agent when the stated constraints are
sufficient for WebGPT to choose.
```

The bundle must include enough file content for WebGPT to write useful code.
Bare local paths are not enough because the browser cannot inspect them.

## Artifact directories (per engagement)

Standard layout for one engagement round (`<slice-id>` = `GOAL.md` slice name):

```text
create-architecture/<slice-id>/<timestamp>/
  creation-bundle.md       # what you sent (or creation-bundle.zip)
  creation-bundle.sha256
  ask-artifacts/             # copy or symlink from .ask_artifacts/runs/<ask_id>/
  02_response.raw.md         # WebGPT raw response (from surf meta paths)
  {project}-{slice-id}-solution.zip   # same name as WebGPT download — never source.zip
  {project}-{slice-id}-solution.sha256
  extracted/                 # isolated sanity tree
  sanity-report.md
  gap-report.md              # MISSING / LIVE table after port + tests
```

## Solution zip layout (required)

WebGPT's **solution zip** should use **repo-relative paths** from the target
project root. Minimum contents:

```text
MANIFEST.json          # file list, sha256 per file, slice id, created_at
ARCHITECTURE.md        # contract: boundaries, state machine, schemas (for this slice)
prompt_improvements.md # required — feed the next engagement round
<paths from GOAL.md>   # finished source, tests, fixtures
```

`MANIFEST.json` minimum fields:

```json
{
  "slice_id": "sparta-routing-P0",
  "project": "memory",
  "bundle_filename": "memory-sparta-routing-P0-solution.zip",
  "files": [
    {"path": "src/...", "sha256": "...", "role": "implementation"}
  ]
}
```

### Multi-file delivery rule (required)

| Files produced | Required WebGPT delivery |
|----------------|--------------------------|
| **0** (questions only) | Numbered clarifying questions — no zip |
| **1** finished file | May be a single attachment **or** one-file zip |
| **2+** finished files | **Must** be one **solution zip** + `MANIFEST.json` |

Never accept multiple finished files scattered across chat prose, separate
download buttons, or inline code fences when a zip could bundle them. The
project agent captures **one** zip per engagement round.

### Solution zip filename (required — WebGPT download name)

The **downloadable zip filename** WebGPT attaches must be **project-scoped** so
humans and the project agent can identify it in Downloads without opening it:

```text
{project}-{slice-id}-solution.zip
```

Rules:

- **`project`** — short repo/project slug from `GOAL.md` or `--webgpt-project`
  (e.g. `memory`, `personaplex-deepgram`).
- **`slice-id`** — kebab-case slice from `GOAL.md` / engagement dir
  (e.g. `sparta-routing-P0`, `sparta-routing-P2-P4-combined`).
- Lowercase, ASCII, hyphens only; no spaces or generic names like `solution.zip`,
  `files.zip`, or `bundle.zip`.

Examples:

```text
memory-sparta-routing-P0-solution.zip
memory-sparta-routing-P2-P4-combined-solution.zip
```

`MANIFEST.json` must include `"bundle_filename"` matching the attached zip name.

**Do not rename the download to `source.zip`.** Keep the project-scoped filename
end-to-end in Downloads, the engagement run dir, receipts, and gap reports. A
generic local rename loses traceability and collides when multiple projects or
slices are in flight.

Generic download names (`solution.zip`, `source.zip`) are **routing failures** —
reissue with the naming rule.

Prose describing files without a zip is a **routing failure** — re-enter creation
with stricter output requirements.

## Solution zip download and capture

**There is no first-class `webgpt.download-zip` in Surf today.** The project agent
must capture a real zip artifact before porting.

```text
WebGPT controlled tab
  -> solution zip captured locally (ladder below)
  -> sha256 + MANIFEST.json verification
  -> extract to isolated sanity directory
  -> bundle-level sanity checks
  -> port into real repo only after sanity passes
```

### Capture ladder (try in order)

1. **ChatGPT file download in controlled tab** — if WebGPT attaches a `.zip` link
   or download button, capture via authenticated tab context (`surf js` fetch +
   browser download into `create-architecture/<run-id>/{project}-{slice-id}-solution.zip`). Record tab id
   and meta receipt.
2. **Response assembly** — if WebGPT returns a `MANIFEST.json` plus file bodies
   in the assistant response, write files under `create-architecture/<run-id>/assembled/`,
   run `zip -r {project}-{slice-id}-solution.zip .` (name from GOAL.md / manifest), and record sha256. This is acceptable only when the
   manifest matches written files.
3. **Human-assisted download** — human saves the zip from the ChatGPT UI; project
   agent records path, sha256, and screenshot of the download row in the thread.

Stop with `NEEDS_ATTENTION: missing_webgpt_zip_download_capability` only when all
three paths fail.

Do not port from prose-only descriptions. Do not paste generated files directly
into the production tree before the named solution zip exists, is checksummed, extracted,
and bundle-sanity-checked in isolation.

### Multipart file-body recovery

When the response-assembly capture path is used, WebGPT may need multiple
assistant turns to emit all file bodies. Treat continuation markers as artifact
sentinels distinct from Surf's browser transport sentinel:

| Marker | Layer | Meaning | Required project-agent action |
|--------|-------|---------|-------------------------------|
| `<<<WEBGPT_DONE:...>>>` | Surf transport | Browser response for this turn is finished | Save raw/clean/meta/receipt files |
| `CONTINUE_FOR_PART_N` | Solution artifact | File-body bundle is incomplete | Save partial response, inventory completed `FILE:` blocks, request part `N` |
| `END_OF_SOLUTION_BUNDLE` | Solution artifact | All file bodies have been emitted | Assemble files, zip, checksum, verify manifest |

Rules:

- Do not suppress Surf's `WEBGPT_DONE` marker for multipart responses. Surf must
  still receive its normal transport sentinel on every browser turn.
- Ask WebGPT to print `CONTINUE_FOR_PART_N` **before** the final Surf marker when
  more file bodies remain.
- On `CONTINUE_FOR_PART_N`, do not assemble or port yet. The bundle is incomplete.
- Save each part under the engagement directory, for example
  `06_response.visible_part1.md`, `08_response.visible_part2.md`.
- Parse completed file sections by repo-relative path and compare them with
  `MANIFEST.json` or WebGPT's declared file list.
- The next request must be narrow: "Continue with part N from the next missing
  file; do not repeat files already emitted."
- When all files are present, write them under `assembled/`, create `{project}-{slice-id}-solution.zip`,
  compute matching `.sha256`, and run manifest checksum verification before
  isolated sanity.
- If WebGPT repeatedly returns only a filename or non-reconstructable prose,
  classify the round as `missing_webgpt_solution_artifact`; do not invent the
  files locally.

Recommended artifact prompt for response assembly:

Use this wording:

    Return file bodies in this format:

    ## FILE: <repo-relative-path>
    ```<language>
    <full file body>
    ```

    If the response is too long, stop after a complete file block and print:
    CONTINUE_FOR_PART_2

    Then still print the normal browser completion marker requested by Surf.

Suggested artifact convention:

```text
reviews/<project>/greenfield-sanity/<run-id>/
  {project}-{slice-id}-solution.zip
  {project}-{slice-id}-solution.sha256
  manifest.json
  extracted/
  sanity-report.json
  sanity-report.md
```

## Port and apply into the real repo (brownfield)

After isolated bundle sanity passes:

0. **Confirm delivery shape** — if WebGPT produced 2+ files, the named solution
   zip (`{project}-{slice-id}-solution.zip`) must exist with matching
   `MANIFEST.json` / `bundle_filename`. Never accept `source.zip`. Otherwise stop
   and reissue creation.
1. **Map paths** — use `MANIFEST.json` paths; they must match `GOAL.md` scope.
2. **Apply mode** — copy new files; for existing files, apply as a focused patch
   (do not wholesale overwrite unrelated modules).
3. **Forbidden without new engagement** — inventing modules, APIs, or state machines
   not present in the solution zip.
4. **Mechanical fixes allowed** — imports, docker restart, env wiring, path prefixes,
   test harness glue, typing/format fixes that do not change architecture.
5. **Proof** — run `GOAL.md` acceptance commands; record commands + exit codes.
6. **HTML report (blocking)** — `REPORT_ENFORCEMENT.md` checklist on the rendered
   page **before** claiming closure.
7. **Gap report** — `gap-report.md` must match HTML; list **MISSING** rows for next engagement.
8. **HANDOFF** — update next-slice pointer.

## Runtime learnings (port loop — self-improvement)

After each engagement round, the project agent **must** fold port deltas into the
next creation bundle and into this section when the lesson generalizes.

### When to skip a WebGPT round

If live probing on the real daemon proves the capability already works and the
only gap is a **missing health test or script wiring**, the project agent may
close the slice locally (add test, **update HTML report first**, then gap-report). Do **not** force a solution
zip for test-only work. Record `Engagement type: local test-only` in `gap-report.md`.

### Port gotchas (memory / SPARTA — 2026-06-23)

| Symptom | Root cause | Fix |
|---------|------------|-----|
| Apply script says `AnswerRequest` "already patched" but field missing | False positive matched `ClarifyRequest.evidence_case` | Grep exact class after apply; patch manually if needed |
| Live P0 test: answer text OK but `sources: []` | Live direct-lookup packets are **glossary-only** under `evidence_case`; zip fixtures used QRA/crosswalk | Extend `_sources_from_context()` for glossary + nested `answer_payload` / `evidence_card` |
| Live probe shows empty clarify questions | Wrong JSON key in probe (`text` vs `question`) | Assert `clarify_questions[].question` in tests |
| Claiming LIVE after unit tests only | Docker not restarted; pytest used mocks | `docker restart embry-memory` then `tests/health/test_domain_recall_live_sanity.py` |

### Required gap-report fields (every round)

```markdown
**Engagement type:** WebGPT solution zip | local test-only
**Port delta vs zip:** bullets of semantic fixes not in WebGPT bundle
**Proof:** commands + exit codes + mocked/live honesty
**Next slice:** P(n+1) with explicit GOAL or "test-only" note
```

### Feeding `prompt_improvements` forward

Before the next WebGPT creation bundle, paste into **Current Local Evidence**:

- live response shapes that differ from zip fixtures,
- apply-script false positives,
- acceptance commands that actually proved the gate,
- any "do not claim LIVE until …" guard discovered in port.

WebGPT should update the next solution zip and `prompt_improvements.md` to prevent
repeat failures.

## Isolated Sanity Check Boundary

The returned zip bundle is not proof that the real project is integrated. It is
an **isolated candidate** for the scoped slice (module, function, harness rung,
or project) that must pass sanity checks before porting into the existing tree.

The returned zip bundle is not proof that the real project is implemented. It is
a greenfield candidate that can be sanity-checked before local integration.

Appropriate greenfield sanity checks:

- unzip succeeds and manifest paths match files,
- schema files parse,
- tests included by WebGPT run in the isolated bundle when dependencies permit,
- static syntax checks pass,
- generated HTML/visual artifacts render and can be inspected,
- expected fixture outputs match the included tests,
- no forbidden placeholders such as `TODO implement` remain in core files.

Example: a generated decision-tree HTML like
`/reviews/personaplex-deepgram/compliance-memory-decision-tree.html` can prove
the approach is inspectable and internally coherent, but it does not prove the
live PersonaPlex/memory wrapper is implemented.

After greenfield sanity passes, the project agent ports or applies the bundle
into the actual project, fixes mechanical integration defects, and runs local
project proof.

## Minimal Contract Template

```markdown
# Architecture And Code Solution: <name>

## Goal

## Non-Goals

## System Boundaries

## Authority Boundaries

## Canonical Data Ownership

## Derived Projections And Rebuild Rules

## Schemas / API Contracts

## State Machine

## Lifecycle Flow

## Error Handling And Fail-Closed Behavior

## Rollback / Rebuild Plan

## Security, Privacy, And Retention

## Deterministic Acceptance Tests

## Evidence Required For Later Review Gate

## Implementation Sequence

## Finished-File Zip Bundle Manifest

## File-By-File Code Changes Or Finished Files

## Test Fixtures And Expected Outputs

## Exact Commands

## Known Limitations / Local Bug-Fix Targets

## Prompt Improvements For Next Turn

Include:

- missing context WebGPT needed but did not receive,
- ambiguous wording in the project-agent prompt,
- exact facts/files/evidence the next prompt should include,
- instructions that should be removed because they caused review-mode or
  ambiguity,
- a revised prompt skeleton for the next WebGPT round if another round is
  needed.
```

The project agent must read this section before continuing the WebGPT loop,
porting the bundle, or preparing a later review request. If the section is
missing from the final bundle, treat the bundle as incomplete and re-enter the
creation loop rather than silently proceeding.

## Handoff Rule

End with the next build step, not a verdict. Good endings:

- "Next build step: unzip the returned bundle and run greenfield sanity checks."
- "Next build step: port the sanity-checked bundle into the real project."
- "Next local task: fix mechanical integration errors from the WebGPT patch."
- "Next review step: run `review-plan` after this contract is accepted."

Bad endings:

- "Verdict: PASS."
- "Verdict: NEEDS_CHANGES."
- "Ready to implement" without naming the first implementation artifact.
