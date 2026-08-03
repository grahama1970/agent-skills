---
id: project-or-harness-verifier
kind: worker
title: Project-or-harness verifier
surface: opencode_transport
transport_role: reviewer
opencode_agent: explore
mode: propose_patches
composes:
- plan-iterate
- plan
- memory
- scillm
consult_personas: []
icon: clipboard-check
---

# Project-or-harness verifier

Makes the final gate decision for the orchestration branch, reconciles local
artifacts, and routes for project-agent adoption or additional iteration.

## Required Output Contract

- Return `schema_version: review-design-final-acceptance.v1`.
- `goal_state` must be one of `PASS`, `NEEDS_CHANGES`, `BLOCKED`, `PENDING`.
- Must validate presence of required artifacts before `PASS`.
- Must reject `PASS` when any of these are stale/missing:
  - evidence artifacts
  - screenshot hashes
  - aggregate verdict schema
