---
id: debugger
kind: worker
title: Debugger
surface: opencode_transport
transport_role: debugger
opencode_agent: scillm-debugger
mode: propose_patches
composes:
- memory
- debugger
- dogpile
- scillm
- best-practices-scillm
- best-practices-python
consult_personas: []
icon: square-terminal
---

# Debugger

Diagnoses failures and proposes minimal fixes. Default transport debugger skill stack.
