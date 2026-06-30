# /plan Goal-Closure Infographic Image Spec

## Current Authoritative Artifact

`skills/plan/docs/PLAN_GOAL_CLOSURE_INFOGRAPHIC.html`

## Optional Preview Image

`skills/plan/docs/PLAN_GOAL_CLOSURE_INFOGRAPHIC.png`

## Accepted Design Brief

`skills/plan/docs/PLAN_GOAL_CLOSURE_INFOGRAPHIC_DESIGN_BRIEF.md`

## HTML/CSS Source

`skills/plan/docs/PLAN_GOAL_CLOSURE_INFOGRAPHIC.html`

## Visual Style

Fixed technical poster, white panels on a pale gray background, restrained
color-coded section borders, readable selectable text, and minimal arrows.
No Mermaid syntax or Mermaid-rendered chart is allowed.

## Legend

| Color | Meaning |
|---|---|
| Blue | `/plan` control, validation, closure decisions |
| Navy | `/review-plan` contract gate |
| Orange | `/orchestrate` execution, retry, evidence |
| Purple | `/code-runner` bounded worker |
| Green | success/stop/result |
| Red | blocked/interview/failure path |

## Required Title And Subtitle

Title: `/plan Goal-Closure Loop`

Subtitle: `Explicit opt-in execution loop: plan-only stays plan-only unless the user asks to execute until done.`

## Required Regions

1. User intent split.
2. `/plan` outer deterministic loop.
3. `/orchestrate` runs inside `/plan`.
4. `/code-runner` runs inside `/orchestrate`.
5. `/plan` stop, replan, or interview.

## Required Nodes And Edges

- Plan-only request -> `0N_TASKS.yaml`.
- Explicit goal-closure request -> `--execute-closure --max-replans N`.
- `/plan` validate -> `/review-plan` review -> `/orchestrate` run -> closure assessment -> goal achieved decision.
- `/orchestrate` evidence artifacts feed `/plan` closure assessment.
- `/code-runner` result artifacts feed `/orchestrate`, not `/plan` directly.
- Non-closed outcomes route to follow-up plan or interview request artifacts.

## Required Artifact Labels

- `0N_TASKS.yaml`
- `plan.py --validate`
- `/review-plan review`
- `status.json`
- `report.txt`
- `events.jsonl`
- `code-runner-spec.json`
- `rounds.jsonl`
- `verifier.log`
- `{task_id}.result.json`
- `{task_id}.failure-bundle.json`
- `{task_id}.interview-request.json`
- `<plan>.goal-closure.json`
- `<plan>.followup-N.yaml`
- `<plan>.interview-request.json`

## Browser Verification Command

```bash
chromium --headless --no-sandbox --disable-gpu \
  --window-size=1440,2000 \
  --screenshot=/tmp/plan-goal-closure-browser-verification.png \
  file://${HOME}/workspace/experiments/agent-skills/skills/plan/docs/PLAN_GOAL_CLOSURE_INFOGRAPHIC.html
```

## Source Image Prompt

Render the local HTML/CSS source as a deterministic browser screenshot. Do not
use a generated image model. Do not use Mermaid. Preserve readable text and the
fixed poster geometry.

## Export Command

```bash
chromium --headless --no-sandbox --disable-gpu \
  --hide-scrollbars --force-device-scale-factor=1 \
  --window-size=1440,2000 \
  --screenshot=skills/plan/docs/PLAN_GOAL_CLOSURE_INFOGRAPHIC.png \
  file://${HOME}/workspace/experiments/agent-skills/skills/plan/docs/PLAN_GOAL_CLOSURE_INFOGRAPHIC.html
```

## Update Rules

- Update the design brief first when the `/plan` workflow changes.
- Keep the HTML/CSS as the editable source of truth.
- Regenerate the PNG after every HTML/CSS change.
- Verify the PNG visually before reporting completion.
- Do not add dashboard-style metric cards or fake operational status.

## Change Log

- 2026-05-09: Added image spec for the `/plan` goal-closure infographic and pinned no-Mermaid browser-rendered workflow.
- 2026-05-09: Rebuilt the artifact as a fixed 1440x2000 browser-rendered poster with inline SVG connectors; HTML/CSS/SVG is authoritative and PNG is a preview.
