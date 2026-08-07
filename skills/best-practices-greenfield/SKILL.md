---
name: best-practices-greenfield
description: >
  Use for greenfield collaboration where the final product, architecture,
  workflow, schema, prompt, memory representation, visual direction, evaluation
  method, or implementation path is not fully known. Forces one named artifact,
  one visible contract, one candidate, one inspection, one status, and one next
  legal move instead of issue-tracker drift or broad architecture theater.
triggers:
  - greenfield
  - greenfield project
  - artifact contract
  - artifact-first
  - artifact studio
  - not an issue tracker
  - not github issue tracker
  - I do not know how this should be solved
  - I don't know how this should be solved
  - next smallest artifact
  - define the next artifact
  - collaboration under uncertainty
  - stop turning this into issue tracking
metadata:
  short-description: Artifact-first greenfield collaboration protocol
provides:
  - greenfield-collaboration-protocol
  - artifact-contract
  - drift-prevention
  - artifact-inspection
composes: []
taxonomy:
  - collaboration
  - greenfield
  - validation
  - resilience
  - artifact
disciplines:
  - engineering-standards
  - human-collaboration
---

# Best Practices: Greenfield Collaboration

Use this skill when working with the user on greenfield projects where the final product, architecture, workflow, schema, prompt, memory representation, visual direction, evaluation method, or implementation path is not fully known.

This skill is for collaboration under uncertainty. It is not a SaaS app scaffold, GitHub issue generator, backlog manager, ticketing workflow, or maintenance-workflow skill.

The purpose of this skill is to prevent drift by forcing work into one named artifact, one visible contract, one candidate, one inspection, one status, and one next legal move.

---

## When to Use This Skill

Use this skill when the user is building, discovering, designing, or refining something new and the correct final form is not already obvious.

Examples:

- extraction pipelines
- prompt pipelines
- memory systems
- book or document processing workflows
- video, image, or scene generation workflows
- persona or identity systems
- UI concepts or new user workflows
- agent orchestration
- subagent protocols
- data models
- evaluation harnesses
- creative direction
- product concepts
- research prototypes
- any multi-step greenfield artifact process

Do not use this skill for simple maintenance work where the task is already bounded, such as:

- fixing a known bug
- applying a small patch
- updating a dependency
- writing a known function
- running a known test
- making a narrow code change with clear acceptance criteria

If a maintenance task becomes ambiguous, switch to this skill before continuing.

---

## Core Rule

Greenfield uncertainty is allowed.

Drift is not.

Resolve uncertainty by producing the next smallest inspectable artifact.

Do not work on “the whole project.” Work on the next artifact that reduces uncertainty and can be inspected.

---

## Primary Failure Modes This Skill Prevents

This skill exists to prevent these recurring failures:

- expanding from one artifact into the whole system
- mixing architecture diagnosis with execution
- switching projects mid-run
- switching runtimes mid-run
- producing prose instead of an inspectable artifact
- hiding prompts, inputs, outputs, schemas, or results
- treating unvalidated outputs as accepted inputs
- continuing after a hard violation
- patching forward from a contaminated run
- using tests as a substitute for inspecting creative, source, memory, prompt, or extraction artifacts
- creating GitHub issues, SaaS plans, or backlog theater when the user is doing greenfield artifact work
- relying on chat memory instead of a visible active contract
- claiming “done” from explanation rather than artifact inspection
- scaling before one case works

---

## Legal Modes

There are only two legal modes.

The agent must identify which mode applies before doing substantive work.

```text
MODE: EXPLORE_TO_CONTRACT
```

or:

```text
MODE: EXECUTE_ARTIFACT
```

---

## MODE: EXPLORE_TO_CONTRACT

Use this mode when the next artifact is unclear.

The output of this mode is an artifact contract, not implementation.

### Allowed

- clarify the user's intent
- identify the next smallest useful artifact
- state known constraints
- state unknowns
- propose an inspection method
- define failure conditions
- propose a default first candidate
- place adjacent ideas into the parking lot

### Forbidden

- implementation
- durable writes
- database writes
- memory writes
- multi-artifact execution
- scaling
- cross-project pivots
- broad architecture expansion beyond what is necessary to define the next artifact
- GitHub issue creation unless explicitly requested
- claiming progress on the project itself

### Required Output

```text
MODE: EXPLORE_TO_CONTRACT

Proposed next artifact:
Why this is the smallest useful artifact:
Artifact contract:
  Artifact:
  Input:
  Output shape:
  Must include:
  Must not include:
  Runtime/tooling:
  Inspection method:
  Failure conditions:
  Allowed writes:
  Forbidden writes:
  Report format:
Known unknowns:
Default first candidate:
Parking lot:
Stop conditions:
```

Do not execute the artifact until the user approves the contract or explicitly says to run it.

---

## MODE: EXECUTE_ARTIFACT

Use this mode when the artifact contract is already visible.

The output of this mode is one candidate artifact plus inspection.

### Allowed

- produce one candidate artifact
- show input, prompt, and output when applicable
- run mechanical checks
- create an inspection report
- assign one artifact status
- record adjacent ideas in the parking lot

### Forbidden

- changing the artifact without declaring `PIVOT`
- executing adjacent ideas
- scaling to the full project
- switching runtime or tooling mid-run
- performing writes not explicitly allowed by the contract
- using unaccepted artifacts as inputs
- continuing after a hard stop condition
- claiming system-level completion from one artifact
- hiding prompt, input, output, schema, validator result, or receipt

### Required Output

```text
MODE: EXECUTE_ARTIFACT

Artifact:
Candidate:
Inspection:
Status:
Next legal move:
```

The status must be exactly one of:

```text
ACCEPTED
REVISE
PIVOT
BLOCKED
```

---

## Required Artifact Contract

Before any execution, there must be a visible artifact contract.

```text
Artifact:
Input:
Output shape:
Must include:
Must not include:
Runtime/tooling:
Inspection method:
Failure conditions:
Allowed writes:
Forbidden writes:
Report format:
```

If this contract is missing, do not execute. Switch to `MODE: EXPLORE_TO_CONTRACT`.

If the user gives a broad request like “build the pipeline,” “move forward,” “fix the workflow,” or “make the system work,” translate it into the next smallest artifact contract before executing.

---

## Greenfield Artifact Loop

Use this loop for all greenfield work:

```text
1. Name the next artifact.
2. Write the visible artifact contract.
3. Generate one candidate.
4. Inspect the actual artifact.
5. Classify the result.
6. Lock accepted artifacts.
7. Compose upward only from accepted artifacts.
```

Do not skip from step 1 to “build the whole system.”

Do not scale until one artifact instance has passed inspection.

---

## Artifact Statuses

Only four statuses are allowed.

```text
ACCEPTED
REVISE
PIVOT
BLOCKED
```

### ACCEPTED

Use when the artifact is reusable as-is.

Required report:

```text
Status: ACCEPTED
Artifact:
Candidate:
Inspection result:
Reason accepted:
Can be used by:
Next legal move:
```

### REVISE

Use when the same artifact contract remains valid, but the candidate has specific defects.

Required report:

```text
Status: REVISE
Artifact:
Defects:
Unchanged contract:
Next revision target:
Next legal move:
```

Do not redesign the system. Revise the same artifact under the same contract.

### PIVOT

Use when the artifact contract itself was wrong.

Required report:

```text
Status: PIVOT
Artifact:
Why the contract failed:
Replacement contract:
Execution state:
Next legal move:
```

Do not execute the replacement contract until it is visible and approved or explicitly accepted by the user.

### BLOCKED

Use when the artifact cannot proceed.

Allowed causes:

- missing source
- missing tool
- missing auth
- missing human decision
- conflicting constraints
- unsafe or forbidden action
- unavailable validator
- inaccessible runtime
- insufficient input

Required report:

```text
Status: BLOCKED
Artifact:
Blocking cause:
Needed to unblock:
No-op confirmation:
Next legal move:
```

---

## Parking Lot

Greenfield work naturally creates adjacent ideas. Preserve them without executing them.

Use:

```text
PARKING_LOT.md
```

Rules:

- Adjacent ideas may be recorded.
- Adjacent ideas may not be executed during the current artifact run.
- A parking-lot item cannot become active until the current artifact is `ACCEPTED`, `BLOCKED`, or explicitly abandoned.
- Parking-lot items are not progress.
- Parking-lot items are not commitments.

Examples of parking-lot items:

- “Later, scale this from Chapter 02 to all chapters.”
- “Consider a different schema for identity facts.”
- “Potential UI visualization for validation report.”
- “Possible memory recall benchmark after upsert.”

---

## Required Run Artifacts

Each run should preserve these files when file writes are allowed:

```text
ACTIVE_CONTRACT.md
input_manifest.json
candidate_output.*
inspection.md or validation_report.json
status.md
PARKING_LOT.md
```

If file writes are not allowed, the same information must be shown directly in the response.

---

## Prompt or Model-Based Work

For prompt-based, LLM-based, extraction, classification, transformation, or generation work, also preserve:

```text
prompt_payload.json
schema.json
raw_result.json
parsed_result.json
```

Requirements:

- The prompt must be visible.
- The input must be identified.
- The schema must be visible for structured outputs.
- The raw result must be retained.
- The parsed result must be retained.
- The validator result must be shown when a validator exists.

Hidden prompts or hidden model outputs invalidate the run.

---

## Memory Work

For memory, persona memory, recall, upsert, or knowledge-ingest work, also preserve:

```text
upsert_manifest.json
write_receipt.json
recall_query.json
recall_result.json
recall_proof.md
```

Memory writes must not happen unless the artifact contract explicitly allows them.

A memory artifact is not accepted until there is recall proof.

---

## Visual, Image, or Video Work

For visual, image, video, scene, style, identity, or creative generation work, also preserve:

```text
identity_contract.md
scene_prompt.md
render_notes.md
visual_inspection.md
```

Inspection must consider the actual output, not just the prompt.

Typical inspection dimensions:

- identity consistency
- composition
- missing visual requirements
- incorrect visual requirements
- prompt-output mismatch
- style mismatch
- duration or scene-structure mismatch, if relevant

Do not treat a syntactically valid prompt as a successful visual artifact.

---

## UI or Workflow Work

For UI, interaction, browser, or workflow artifacts, also preserve:

```text
screenshot.png
workflow_trace.md
state_before.md
state_after.md
```

Inspection must use the actual workflow state, not DOM-only reasoning or speculative descriptions.

A UI artifact is not accepted unless the relevant state transition is observed or the limitation is explicitly documented.

---

## Structured Data Work

For JSON, schemas, extraction outputs, manifests, datasets, or structured records, inspection should include:

```text
schema validation
parse validation
record count
required-field coverage
empty/null-field report
source grounding check
quote or evidence coverage, if applicable
density check, if applicable
duplicate check, if applicable
domain-specific checks, if applicable
```

Do not accept structured data because it “looks plausible.” Accept it only after inspection.

---

## Source-Grounded Work

When an artifact depends on source material, inspection must verify grounding.

Examples:

- document extraction must cite or point to source spans
- QRA/fact extraction must preserve quote/evidence support when required
- memory upserts must trace back to accepted source artifacts
- UI claims must trace to screenshots or actual workflow traces
- generated summaries must identify input material and limitations

No source proof means the artifact cannot be accepted as source-grounded.

---

## Stop Conditions

Stop immediately if any of these occur:

```text
wrong runtime
wrong skill
missing contract
missing input
missing prompt artifact
missing schema for structured output
malformed output
validator failure
unauthorized write
cross-project pivot
architecture expansion during EXECUTE_ARTIFACT
attempt to use unaccepted artifact as input
hidden prompt
hidden output
hidden write
missing inspection
status not assigned
```

One hard violation invalidates the current run.

Do not patch forward from a contaminated run. Start a new run directory with a corrected contract.

---

## Runtime Discipline

If the contract names a runtime, tool, endpoint, skill, agent, or subagent, that runtime is binding.

Rules:

- Do not switch runtimes mid-run.
- Do not fall back to a raw or lower-level runtime when the contract requires a wrapped or skill-mediated runtime.
- Do not use an unapproved tool because it is convenient.
- If the runtime is unavailable, classify the artifact as `BLOCKED`.
- If the wrong runtime is used, the run is invalid.

---

## Composition Rule

Only accepted artifacts can become inputs to later artifacts.

Do not compose upward from:

```text
drafts
failed candidates
unvalidated JSON
unchecked prompts
unreviewed visual outputs
memory writes without recall proof
UI claims without workflow evidence
```

The next artifact must list which accepted artifact it depends on.

---

## User Role

The user's role is to:

- state intent in human terms
- reject artifacts that feel wrong
- provide domain judgment where deterministic tests are insufficient
- approve pivots when the artifact contract is wrong
- decide when an accepted artifact is good enough to compose upward

The user does not need to supply a full architecture before work can begin.

---

## Agent Role

The agent's role is to:

- turn intent into a concrete artifact contract
- produce one candidate artifact
- show prompt, input, output, and result when applicable
- run mechanical checks
- inspect the actual artifact
- classify the artifact honestly
- avoid scaling or reframing without permission
- stop when the artifact fails instead of narrating around it
- put adjacent ideas in the parking lot rather than executing them

The agent must not behave as if it can safely hold the entire evolving project in chat memory.

---

## User Turn Template

When the user does not know the exact solution, encourage this format:

```text
GREENFIELD

Intent:
What I’m trying to make:

Known constraints:
Must include:
Must avoid:

Unclear:
List unknowns.

Your job:
Propose the next smallest useful artifact contract.
Do not execute yet.
```

---

## Agent Contract Response Template

Respond with:

```text
MODE: EXPLORE_TO_CONTRACT

Proposed next artifact:
Why this is the smallest useful artifact:

Artifact contract:
  Artifact:
  Input:
  Output shape:
  Must include:
  Must not include:
  Runtime/tooling:
  Inspection method:
  Failure conditions:
  Allowed writes:
  Forbidden writes:
  Report format:

Known unknowns:
Default first candidate:
Parking lot:
Stop conditions:
```

---

## Execution Turn Template

When the contract is clear, the user may say:

```text
MODE: EXECUTE_ARTIFACT

Artifact:
Input:
Output:
Runtime:
Forbidden:
Success gate:
Stop conditions:
Report format:
```

Then execute exactly that artifact and nothing else.

---

## Agent Execution Report Template

After execution, report only artifact-scoped results:

```text
MODE: EXECUTE_ARTIFACT

Artifact:
Candidate:
Inspection:
Status:
Next legal move:
```

For file-based work:

```text
Artifact:
Paths:
  Contract:
  Input manifest:
  Prompt payload:
  Schema:
  Candidate:
  Inspection:
  Status:
Counts:
Validation:
Status:
Next legal move:
```

Avoid broad summaries unless the contract explicitly asks for them.

---

## Forbidden Report Language

Do not say:

```text
The system is working.
The pipeline is done.
We can scale now.
I also fixed another thing.
This should be fine.
Looks good.
Implemented the architecture.
```

Use artifact-scoped language instead:

```text
Artifact accepted.
Candidate failed validation.
Same contract, revise these defects.
Contract was wrong; pivot required.
Blocked on missing source/tool/auth/human decision.
Next legal move is...
```

---

## Greenfield Examples

### Document Extraction

Bad:

```text
Build the book extraction pipeline.
```

Good:

```text
Artifact:
Chapter 02 section extraction JSON.

Input:
Chapter 02 source text.

Output shape:
sections.jsonl with section id, heading, source span, text.

Inspection:
parse validation, section count, source coverage, missing spans.

Failure:
malformed JSONL, missing sections, unsupported source spans.
```

### QRA or Fact Extraction

Good:

```text
Artifact:
Chapter 02 doc-qra JSON candidate.

Input:
accepted Chapter 02 sections.jsonl.

Output shape:
dense QRA/facts plus ToM JSON.

Must include:
question, answer, evidence, source span, ToM fields if required.

Must not include:
generic summaries, one-fact-per-chapter records, memory writes.

Inspection:
schema validation, quote grounding, density, ToM coverage, no generic records.
```

### Memory Ingest

Good:

```text
Artifact:
persona_memory upsert manifest.

Input:
accepted QRA JSON candidate.

Output shape:
upsert_manifest.json.

Must include:
target collection, records, source artifact, write mode, rollback plan.

Inspection:
dry-run validation and recall query plan.

Failure:
wrong collection, missing source artifact, no recall proof plan.
```

### Visual or Video Prompt

Good:

```text
Artifact:
five-second scene prompt.

Input:
accepted identity contract and scene intent.

Output shape:
scene_prompt.md.

Must include:
identity anchors, camera, motion, setting, duration, negative constraints.

Inspection:
prompt completeness and render-output visual inspection after generation.

Failure:
missing identity anchors, ambiguous scene, impossible motion, prompt-output mismatch.
```

### UI Workflow

Good:

```text
Artifact:
login-to-dashboard workflow proof.

Input:
local app URL and test account.

Output shape:
workflow_trace.md plus screenshot.

Inspection:
actual browser path, state before/after, screenshot evidence.

Failure:
DOM-only proof, missing screenshot, no observed state transition.
```

---

## Relationship to Other Skills

This is a parent collaboration skill.

Use this skill first to define the artifact and contract. Then invoke narrower project skills only as needed.

Examples:

```text
best-practices-greenfield
  -> document extraction skill
  -> doc-qra skill
  -> persona-memory skill
  -> subagent/runtime skill
  -> visual-prompt skill
  -> UI-inspection skill
```

The narrower skill must obey the active artifact contract.

If a narrower skill conflicts with the active greenfield contract, stop and classify the run as `BLOCKED` or `PIVOT`.

---

## Final Rule

The agent is not allowed to hold the whole project in its head and improvise.

The agent must hold one artifact contract, produce one candidate, inspect it, classify it, and identify one next legal move.

Greenfield does not mean unconstrained.

It means the next artifact may be uncertain. When uncertain, produce the artifact contract first. Then produce one candidate. Then inspect. Then classify. Only accepted artifacts compose upward.
