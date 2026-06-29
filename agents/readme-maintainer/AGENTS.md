---
id: readme-maintainer
name: readme-maintainer
kind: worker
title: README Maintainer
surface: opencode_transport
transport_role: explore
opencode_agent: build
mode: propose_patches
model_policy: documentation_reasoning
persona: persona.yaml
composes:
- memory
- project-knowledge
- best-practices-readme
- best-practices-skills
- best-practices-report
- best-practices-agent
- best-practices-security
provides:
- readme-drafting
- readme-review
- documentation-proof-review
taxonomy:
- documentation
- validation
- developer-experience
consult_personas: []
icon: book-open
---

# README Maintainer

Transport wrapper for the `readme-maintainer` subagent.

See `persona.yaml` for the authoritative role, boundaries, tool policy, retry
budget, and output contract.
