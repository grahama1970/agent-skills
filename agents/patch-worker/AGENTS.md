---
id: patch-worker
kind: worker
title: Patch worker
surface: opencode_transport
transport_role: patch
opencode_agent: build
mode: workspace_write
composes:
- memory
- scillm
- best-practices-python
- best-practices-scillm
- code-runner
consult_personas: []
icon: wrench
---

# Patch worker

Bounded implementation patches via harness gates. Composes ``/code-runner`` when delegated.
