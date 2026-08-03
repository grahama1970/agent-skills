---
id: code-reviewer
kind: worker
title: Code Reviewer
surface: opencode_transport
transport_role: reviewer
opencode_agent: explore
mode: propose_patches
model_policy: cheap_review
persona: persona.yaml
composes:
- memory
- review-code
- skills-ci
- eval-skills
- security-scan
- scillm
consult_personas:
- brandon-bailey
icon: shield-check
---

# Code Reviewer

Transport wrapper for the `code-reviewer` subagent.

See `persona.yaml` for the authoritative role, state, helper, model-policy, and output contract.
