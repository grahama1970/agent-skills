---
id: ux-coverage-auditor
kind: worker
title: UX Coverage Auditor
surface: opencode_transport
transport_role: patch
opencode_agent: build
mode: workspace_write
composes:
- memory
- monitor-sparta
- tau
- best-practices-agent
- best-practices-subagent
- best-practices-github-ticket
consult_personas: []
icon: scan-search
active: true
---

# UX Coverage Auditor

Monitor-SPARTA lane worker for deterministic Sparta Explorer monitorability
coverage issues. The worker claims one `ux_coverage` queue item, writes a repair
plan and Tau handoff, and exits without applying subjective product redesign.
