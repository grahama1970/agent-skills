---
id: dba-auditor
kind: worker
title: DBA Auditor
surface: opencode_transport
transport_role: reviewer
opencode_agent: build
mode: propose_patches
model_policy: data_reasoning
persona: persona.yaml
composes:
- review-db
- memory
- ops-arango
- project-knowledge
- monitor-memory
- monitor-sparta
- create-report
- create-figure
- best-practices-report
- best-practices-d3
- best-practices-github-ticket
- brave-search
- data-audit
- analytics
- scillm
consult_personas: []
icon: database-zap
---

# DBA Auditor

Transport wrapper for the `dba-auditor` subagent.

See `persona.yaml` for the authoritative role, state, helper, model-policy, and output contract.
