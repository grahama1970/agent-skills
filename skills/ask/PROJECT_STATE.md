# Project State: pi-skill-ask

**Generated 2026-08-12T06:30:59.046091+00:00** from `/home/graham/workspace/experiments/agent-skills/skills/ask`.
A dated assessment artifact, not rolling context — see `PROJECT_KNOWLEDGE.md`
for current understanding. Claims below are `not established` unless a receipt
is named.

## Executive Summary

- Gaps: 3 (1 critical)
- Best-practice findings: 4 ({"critical": 2, "high": 0, "medium": 0, "low": 2})
- Doc drift items: 6
- `sanity.sh` present: True; `SKILL.md` present: True

## Evidence Receipts

- `project_state.json` in this directory (full machine-readable report)
- `/memory` collection `project_states`, schema `project_state.snapshot.v1`

## Outstanding Gaps

- **critical** (security): 2 critical best-practice violations (possible hardcoded secrets) — action: Run /security-scan and fix immediately
- **low** (documentation): 1 aspirational/TODO items in docs — action: Implement or remove aspirational claims
- **low** (skills): 33 skill dirs without SKILL.md — action: Run /skills-ci to audit and fix

## Risks And Unknowns

- Phases skipped by the selected profile are `not established`, not passing.
- Findings under generated/backup directories are not live-source defects;
  check the path before treating a count as a security result.

## Recommended Next Actions

- Compare against the previous snapshot in `project_states` to see direction of travel.
