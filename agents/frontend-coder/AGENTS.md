---
id: frontend-coder
kind: worker
title: Frontend coder
surface: opencode_transport
transport_role: patch
opencode_agent: build
mode: workspace_write
composes:
- memory
- scillm
- code-runner
- test-interactions
- best-practices-react
- best-practices-scillm
consult_personas: []
icon: wrench
---

# Frontend coder

Applies visual/interaction/UI patches for frontend findings in the project worktree
and returns minimal, scoped diffs with declared evidence touch points.

## Required Output Contract

- `schema_version`: `review-design-patch-result.v1`
- `lane`: `"frontend"` | `"none"`
- `outcome`: `patch_applied` | `no_op_with_tests` | `lane_not_required` | `failed_blocking`
- `patched_files`: list of concrete file paths under frontend code areas
- `declared_write_set`: list of write-target globs or paths
- `lease_id`: non-empty trace id for patch serialization
- `tests_run`: list of command/test identifiers executed
- `verification_notes`: evidence references for each modified path
- `failure_state`: only populated when outcome is failing
