---
id: skill-maintainer
kind: worker
title: Agent Skill Maintainer
surface: opencode_transport
transport_role: explore
opencode_agent: explore
mode: propose_patches
model_policy: maintainer_reasoning
persona: persona.yaml
composes:
- memory
- skills-ci
- best-practices-skills
- best-practices-github-ticket
- scheduler
- task-monitor
- ask
- code-runner
- test
- review-code
- project-knowledge
- scillm
consult_personas: []
icon: workflow
---

# Agent Skill Maintainer

Transport wrapper for the `skill-maintainer` subagent. `agent-skill-maintainer`
is the routing name used by monitor-created tickets; the existing directory and
id remain for compatibility.

See `persona.yaml` for the authoritative role, state, helper, model-policy, and output contract.

Durable state tracking uses `$project-knowledge` in addition to `$memory`.
