# Project Knowledge: plan

**Last updated:** 2026-05-09 09:26 by agent
**Status:** Active development

## Current Understanding

- Project initialized, knowledge tracking started
- 2026-05-09: /plan now has an explicit opt-in deterministic goal-closure mode. Normal /plan remains plan-only: create/validate/review YAML and ask before execution. When the user explicitly asks to execute until done, /plan --execute-closure <plan.yaml> runs validate -> /review-plan -> /orchestrate -> /plan --assess-result. /orchestrate produces session evidence and dispatches /code-runner/local tasks; /code-runner remains a bounded worker inside /orchestrate.

## Recent Decisions

| Date | Decision | Why |
|------|----------|-----|
| 2026-05-09 | Initialize project knowledge | Enable shared human/agent context |
| 2026-05-09 | Keep /plan goal closure explicit and bounded | Plan-only requests must not trigger execution. The deterministic loop runs only via --execute-closure or equivalent explicit user intent; it stops on goal_achieved, max_replans exhausted, blocked/wrong_plan/insufficient_evidence, and writes follow-up or interview-request artifacts rather than silently expanding authority. |

## Open Questions

- [ ] What are the key architectural decisions?
- [ ] What are the known issues?

## Key Files

| File | Purpose |
|------|---------|
| skills/plan/docs/PROJECT_KNOWLEDGE.md | Shared project knowledge |
| skills/plan/src/plan_skill/code_runner_contract.py | Code-runner routing and DoD contract checks kept out of the CLI so /plan validation stays maintainable. |
| skills/plan/src/plan_skill/dag.py | DAG visualization helpers for text and legacy Mermaid output. |
| skills/plan/src/plan_skill/goal_closure.py | Deterministic goal-closure assessor and explicit execute loop helper; consumes /orchestrate status/report artifacts and writes closure/follow-up/interview artifacts. |
| skills/plan/src/plan_skill/mutations.py | Structured plan add/remove helpers that preserve validation after CLI edits. |
| skills/plan/docs/PLAN_GOAL_CLOSURE_INFOGRAPHIC.html | Editable HTML/CSS visual chart for the /plan outer loop with nested /orchestrate and /code-runner execution layers. |
| skills/plan/docs/PLAN_GOAL_CLOSURE_INFOGRAPHIC_DESIGN_BRIEF.md | Source-grounded design brief for the /plan loop infographic. |
| skills/plan/docs/PLAN_GOAL_CLOSURE_INFOGRAPHIC_IMAGE_SPEC.md | Updateable visual contract for the /plan goal-closure infographic. |
| skills/plan/docs/PLAN_GOAL_CLOSURE_INFOGRAPHIC_VERIFICATION.md | Browser-render verification notes for the infographic artifact. |
| skills/plan/docs/PLAN_GOAL_CLOSURE_INFOGRAPHIC.png | Browser-rendered infographic proof artifact; no Mermaid. |

## Infrastructure State

<!-- Auto-populated from /project-state --quick -->
