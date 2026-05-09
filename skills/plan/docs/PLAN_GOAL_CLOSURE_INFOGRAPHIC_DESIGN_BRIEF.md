# /plan Goal-Closure Infographic Design Brief

## Purpose

Explain how `/plan` works when a user explicitly opts into the deterministic goal-closure loop, while making clear that ordinary `/plan` requests remain plan-only.

## Target Reader

A project agent or human operator checking whether the agent understands where `/plan`, `/review-plan`, `/orchestrate`, and `/code-runner` boundaries sit.

## Core Message

`/plan` is the outer goal-closure controller only when explicitly requested. `/orchestrate` runs one approved plan and writes evidence. `/code-runner` performs bounded implementation tasks inside `/orchestrate`.

## Source-Grounded Understanding

- Implemented: `skills/plan/SKILL.md` now documents explicit goal-closure triggers and the optional loop.
- Implemented: `skills/plan/plan.py` exposes `--assess-result`, `--execute-closure`, `--session`, and `--max-replans`.
- Implemented: `skills/plan/src/plan_skill/goal_closure.py` reads `/orchestrate` `status.json`, `report.txt`, and task artifacts, then emits closed-vocabulary results.
- Implemented: `skills/orchestrate/SKILL.md` defines `/orchestrate` as the execution engine and evidence/failure-bundle writer.
- Implemented: `skills/code-runner/SKILL.md` defines `/code-runner` as a bounded worker with isolated worktree, allowlist, DoD, artifacts, and optional source apply.
- Missing/intended: automatic generation of a fully corrected follow-up YAML is currently a stub; it records the closure evidence and requires agent/human completion before rerun.

## Required Visual

A single HTML/CSS chart with five readable horizontal regions:

1. User intent split: plan-only versus explicit goal closure.
2. `/plan` outer loop: validate, review, run orchestrate, assess result, decide stop/replan/interview.
3. Nested `/orchestrate` execution band: dispatch local/code-runner tasks, write session evidence, handle retries and failure bundles.
4. Nested `/code-runner` worker band: isolated worktree, LLM rounds, DoD, allowlist patch/source commit artifacts.
5. Stop/replan/interview band: closed-vocabulary outcomes and artifacts.

## Numbered Stage Contracts

| Stage | Input | Operation | Artifact | Decision | Success output | Failure path |
|---|---|---|---|---|---|---|
| 1. User intent split | User request | Classify plan-only versus explicit goal-closure intent | `0N_TASKS.yaml` or `--execute-closure` command | Was execution explicitly requested? | Plan-only path or closure loop path | Plan-only never executes tasks silently |
| 2. `/plan` outer deterministic loop | Approved YAML plan | Validate, review, invoke one `/orchestrate` session, assess session evidence | `<plan>.goal-closure.json` | Did the plan goal close? | Stop on `goal_achieved` | Follow-up plan or `/interview` request |
| 3. `/orchestrate` inside `/plan` | Validated/reviewed plan | Dispatch tasks, run retry policy, write execution evidence | `status.json`, `report.txt`, `events.jsonl`, failure/interview bundles | Did task execution produce sufficient evidence? | Session evidence for `/plan` assessment | Block downstream tasks, write failure bundle |
| 4. `/code-runner` inside `/orchestrate` | Fixed bounded task spec | Isolated worktree, repair rounds, deterministic DoD, result artifact | `code-runner-spec.json`, `rounds.jsonl`, `verifier.log`, `{task_id}.result.json` | Did visible DoD pass? | Patch/result or source commit when explicit | Return bounded failure artifact; no replanning |
| 5. Stop, replan, or interview | Closure assessment | Choose closed action | `<plan>.followup-N.yaml` or `<plan>.interview-request.json` | Is the next step deterministic? | Stop or bounded follow-up | Ask human rather than widening authority |

## Truth Labels

- Implemented: documented trigger behavior, CLI flags, closure assessment, interview request artifact, follow-up stub artifact.
- Implemented: `/orchestrate` session artifacts are the evidence source consumed by `/plan`.
- Implemented: `/code-runner` remains inside `/orchestrate`, not inside `/plan` directly.
- Missing/intended: complete automated plan rewriting from failed tasks into a ready-to-run corrected YAML.

## Required Artifact Names To Show

- `0N_TASKS.yaml`
- `status.json`
- `report.txt`
- `events.jsonl`
- `{task_id}.result.json`
- `{task_id}.failure-bundle.json`
- `{task_id}.interview-request.json`
- `<plan>.goal-closure.json`
- `<plan>.followup-N.yaml`

## Failure Criteria

Reject the visual if it:

- suggests `/plan` always executes tasks,
- hides that goal closure is explicit opt-in,
- shows `/code-runner` as replanning or interviewing,
- omits `/orchestrate` session evidence as the closure input,
- uses Mermaid or dense arrow syntax,
- turns intended follow-up rewriting into an implemented guarantee,
- lacks readable stop conditions.

## Render Plan

Use standalone HTML/CSS at `skills/plan/docs/PLAN_GOAL_CLOSURE_INFOGRAPHIC.html`.
The authoritative artifact is the browser-rendered HTML/CSS/SVG poster. Export
browser-rendered PNG to `skills/plan/docs/PLAN_GOAL_CLOSURE_INFOGRAPHIC.png`
only as a convenience preview or verification artifact.

The HTML/CSS source is the editable visual contract. It uses a fixed poster
canvas and a lightweight inline SVG connector layer for stage-to-stage handoffs;
all meaningful labels remain selectable HTML text. Mermaid is not used.

Target poster dimensions: `1440px` by `2000px`.
