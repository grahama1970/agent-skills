---
name: goal-helper
description: >
  Turn vague, drifting, long-running, overnight, or repeatedly failing work into
  a proof-driven Codex goal with one primary proof command or artifact, explicit
  completion criteria, a bounded retry limit, operational status snapshots, and
  fail-closed stop conditions. Use when the user asks for goal help,
  anti-spiral controls, overnight goal reliability, measurable Definition of
  Done, blocker reports, or when an agent is drifting from the real task.
triggers:
  - goal helper
  - help me set a goal
  - anti spiral goal
  - overnight goal
  - stop error spiraling
  - define proof command
  - measurable definition of done
  - blocker report
provides:
  - task-planning
  - progress-tracking
  - goal-definition
  - blocker-reporting
composes: []
taxonomy:
  - precision
  - resilience
  - validation
---

# Goal Helper

## Purpose

Use this skill to convert messy work into an executable goal that cannot quietly drift. The output may be a `/goal` prompt, a goal checklist, or a blocker report, but it must center on concrete proof.

This skill is stricter than general planning: it identifies the proof surface that demonstrates the requested outcome. The proof surface changes by domain, but the control loop stays the same.

## Core Rule

Define success by observed behavior, not by activity.

Every goal must name:

1. **Primary proof**: one command or artifact that proves the task works.
2. **Completion criteria**: objective checks the agent can evaluate.
3. **Retry budget**: usually two focused implementation attempts per blocker.
4. **Stop condition**: what to report when proof still fails.
5. **Allowed scope**: work directly needed to make the proof pass.
6. **Forbidden drift**: adjacent architecture, dashboards, reviews, cleanup, or refactors that do not serve the proof.

## Workflow

1. **Name the real outcome**
   - Write the user-visible behavior in one sentence.
   - Prefer the exact command, query, UI flow, API call, or file artifact the user expects.
   - If there are many possible proofs, choose the one closest to the user's actual workflow.

2. **Choose the primary proof**
   - Use a command when possible.
   - Use a database query for persistence work.
   - Use a screenshot/CDP check for UI work.
   - Use a real endpoint response for backend work.
   - Use an artifact schema check for extraction or generation work.
   - Use a benchmark/result comparison for performance work.
   - Use a test fixture and expected output for prompt/extraction work.

3. **Add secondary proofs only when needed**
   - Secondary proofs should support the primary proof, not replace it.
   - Keep them few: usually one direct lower-level proof and one regression test.

4. **Bound the loop**
   - Set a maximum of two focused attempts for the same blocker.
   - A focused attempt means: inspect evidence, make a targeted change, rerun the proof.
   - If the same blocker remains after two attempts, stop implementation and write a blocker report.

5. **Write the blocker report contract**
   - Include the exact failed command.
   - Include the exact error or relevant output.
   - Include files changed.
   - Include artifact paths.
   - Include the current hypothesis.
   - Include one recommended next action.

6. **Prevent shortcut success**
   - Ban weakening tests, hiding errors, bypassing auth, deleting checks, fabricating data, or claiming success from a reviewer opinion alone.
   - For memory, extraction, security, persistence, and compliance work, require raw proof artifacts or live query output.

## Proof Surface Guide

Select the proof closest to the user's real job:

| Goal type | Primary proof |
|-----------|---------------|
| CLI/tooling | Exact command exits successfully with expected output |
| Backend/API | Real request/response, status code, and persisted side effect if applicable |
| Database/memory | Query result showing expected record, edge, count, or provenance |
| UI/frontend | Fresh screenshot or CDP/browser proof of the visible user flow |
| Extraction | Fixture input plus validated output artifact/schema |
| Prompt/model contract | Concrete fixture, expected response, validator result |
| Performance | Before/after measurement from comparable commands or runs |
| Security/compliance | Failing exploit/control before, passing verified fix after |
| Runtime/config | Redacted reachability check and restarted process proof |
| Refactor | Existing behavior parity tests plus focused regression coverage |

## Goal Prompt Shape

Use this shape for ready-to-run goals:

```text
/goal <Outcome>.

Primary proof:
- <exact command/query/artifact and expected observable behavior>

Completion criteria:
- <criterion 1>
- <criterion 2>
- <criterion 3>

Allowed scope:
- <files/systems/work that may be changed>

Forbidden drift:
- <adjacent work to avoid>

Retry/stop rule:
- If the same blocker survives 2 focused attempts, stop and write a blocker report with the failed proof, error/output, changed files, artifact paths, hypothesis, and one recommended next action.

Final report:
- Report proof commands and results, skipped checks, and residual risk. Do not claim completion without the primary proof.
```

## Operational Status Snapshot

For status requests during a goal, answer in this shape:

```text
Status/Phase: <one line>
Now: <current file, command, or artifact>
Evidence: <counts, command result, failing output, or artifact paths>
Next/Stop: <next command and stop condition>
```

Do not answer status with only "working", "done", "fixed", "checking", or a general narrative.

## Anti-Spiral Rules

- If the primary proof still fails, fix that path first.
- Do not switch to a broader architecture task unless it is required by the failed proof.
- Do not add polished reports, dashboards, charts, or review bundles before the operational proof exists.
- Do not run unrelated cleanup while the proof path is broken.
- Do not keep trying new approaches overnight without recording attempts and blocker evidence.
- If a human corrects the goal, immediately rewrite the primary proof and discard stale success criteria.

## Examples

Use examples as patterns only. Replace the proof with the current user's actual workflow.

### CLI/API Example

```text
/goal Make the export command produce a valid JSON report for the sample project.

Primary proof:
- `./run.sh export --input fixtures/sample --output /tmp/sample-report.json` exits 0 and `/tmp/sample-report.json` validates against `schemas/report.schema.json`.

Completion criteria:
- The command works from a clean checkout.
- Invalid input fails with a clear error.
- Existing export tests still pass.

Forbidden drift:
- Do not redesign the report format or add a dashboard unless required for the proof command.
```

### UI Example

```text
/goal Make the settings save flow visibly persist the selected timezone.

Primary proof:
- Browser/CDP run changes timezone, clicks Save, reloads the page, and a fresh screenshot shows the selected timezone still visible.

Completion criteria:
- The backend persistence call succeeds.
- The reloaded UI displays the saved value.
- Empty/invalid timezone is rejected with visible feedback.

Forbidden drift:
- Do not restyle unrelated settings panels or replace the page layout.
```

### Persona-Memory Example

```text
/goal Make persona lore queryable through `$ask embry -q "<question>"` and `$ask horus -q "<question>"` from source-grounded `persona_memory`.

Primary proof:
- `./skills/ask/run.sh ask embry -q "Where did you grow up?"` runs without CLI error and answers from persona memory, citing uncertainty when the fact is absent.

Secondary proofs:
- `./skills/memory/run.sh recall --q "Embry Where did you grow up" --collection persona_memory --scope persona-dream --k 8`
- `./skills/memory/run.sh recall --q "Embry knowledge software" --collection persona_memory --scope persona-dream --tags tom:knowledge --k 8`
- `./skills/memory/run.sh recall --q "Horus Emperor" --collection persona_memory --scope persona-dream --k 8`

Completion criteria:
- Embry and Horus records are retrievable from `persona_memory`.
- ToM-tag retrieval works for at least one tag.
- `$ask` persona syntax routes to persona memory.
- Missing facts are reported as missing, not invented.

Forbidden drift:
- Do not continue lore extraction, Qdrant migration, dashboards, or review bundles unless required to make the proof commands pass.
```

## When To Use `/plan` First

Recommend `/plan` before `/goal` only when the primary proof cannot be selected yet because the user has not decided the product behavior, target system, or source of truth.

If the proof can be inferred, create the goal and label assumptions instead of asking open-ended questions.
