# Project State: monitor-opportunities

**Generated 2026-08-11T14:38:09.583334+00:00** from `/home/graham/workspace/experiments/agent-skills/skills/monitor-opportunities`.
A dated assessment artifact, not rolling context — see `PROJECT_KNOWLEDGE.md`
for current understanding. Claims below are `not established` unless a receipt
is named.

## Executive Summary

- Gaps: 3 (1 critical)
- Best-practice findings: 1 ({"critical": 1, "high": 0, "medium": 0, "low": 0})
- Doc drift items: 2
- `sanity.sh` present: True; `SKILL.md` present: True

## Evidence Receipts

- `project_state.json` in this directory (full machine-readable report)
- `/memory` collection `project_states`, schema `project_state.snapshot.v1`

## Outstanding Gaps

- **critical** (security): 1 critical best-practice violations (possible hardcoded secrets) — action: Run /security-scan and fix immediately
- **low** (documentation): 2 aspirational/TODO items in docs — action: Implement or remove aspirational claims
- **low** (skills): 33 skill dirs without SKILL.md — action: Run /skills-ci to audit and fix

## Risks And Unknowns

- Phases skipped by the selected profile are `not established`, not passing.
- Findings under generated/backup directories are not live-source defects;
  check the path before treating a count as a security result.

## Recommended Next Actions

- Compare against the previous snapshot in `project_states` to see direction of travel.
