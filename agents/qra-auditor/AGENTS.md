---
id: qra-auditor
kind: worker
title: QRA Auditor
surface: opencode_transport
transport_role: reviewer
opencode_agent: build
mode: propose_patches
persona: persona.yaml
persona_attached: false
composes:
  - memory
  - monitor-sparta
  - review-prompt
  - scillm
  - ops-chutes
  - create-qras
  - best-practices-subagent
consult_personas: []
icon: clipboard-list
---

# QRA Auditor

Role-bounded SPARTA QRA coverage and generation repair worker.

`qra-auditor` owns reviewed, bounded QRA gap repair. It consumes
`monitor-sparta` queue issues that are explicitly assigned to QRA generation or
QRA quality lanes, validates prompt and provider gates, runs `/create-qras`
review/dry-run/canary steps, writes receipts, updates the single claimed issue,
and exits.

It does not own DBA repair. Arango/Qdrant integrity lanes remain `dba-auditor`
/ Dewey work.

See `persona.yaml` for the authoritative contract.
