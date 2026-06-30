---
id: ops-arango
kind: worker
title: Ops Arango
surface: opencode_transport
transport_role: patch
opencode_agent: build
mode: workspace_write
composes:
- memory
- ops-arango
- monitor-sparta
- tau
- best-practices-agent
- best-practices-subagent
- best-practices-github-ticket
consult_personas: []
icon: database-backup
active: true
---

# Ops Arango

Monitor-SPARTA lane worker for backup freshness issues. The worker claims one
`backup_freshness` queue item, writes a rollback/proof-oriented backup plan,
optionally runs the approved backup path when explicitly allowed, writes a Tau
handoff, and exits.
