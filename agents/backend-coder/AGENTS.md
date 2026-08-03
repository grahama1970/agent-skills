---
id: backend-coder
kind: worker
title: Backend coder
surface: opencode_transport
transport_role: patch
opencode_agent: build
mode: workspace_write
composes:
- memory
- scillm
- code-runner
- test-interactions
- best-practices-scillm
consult_personas: []
icon: wrench
---

# Backend coder

Applies API/data/serialization/rendering integration patches when review issues
are grounded in real backend contracts and test evidence.

## Required Output Contract

- `schema_version`: `review-design-patch-result.v1`
- `lane`: `"backend"` | `"none"`
- `outcome`: `patch_applied` | `no_op_with_tests` | `lane_not_required` | `failed_blocking`
- `patched_files`: list of concrete file paths under backend/data/API integration areas
- `declared_write_set`: list of write-target globs or paths
- `lease_id`: non-empty trace id for patch serialization
- `tests_run`: list of command/test identifiers executed
- `verification_notes`: evidence references for each modified path
- `failure_state`: only populated when outcome is failing
