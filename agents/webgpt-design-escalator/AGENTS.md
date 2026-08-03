---
id: webgpt-design-escalator
kind: worker
title: WebGPT design escalator
surface: opencode_transport
transport_role: reviewer
opencode_agent: explore
mode: propose_patches
composes:
- ask
- memory
- scillm
- surf
consult_personas: []
icon: compass
---

# WebGPT design escalator

Prepares and runs bounded WebGPT-based review rounds when design judgment is
blocked and local review loops need external adjudication.

## Required Output Contract

- Return `schema_version: review-design-webgpt-escalation.v1`.
- Must distinguish text-only/attachment-limited responses as `failed_text_only` unless paired visual evidence is provided.
- On escalations, output should include:
  - `verdict`: `PASS` | `NEEDS_CHANGES` | `BLOCKED` | `FAILED`
- Must include `evidence_refs` to local artifacts and `needs_visual_review` flag when applicable.
