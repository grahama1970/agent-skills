---
name: anvil
description: >
  Heavy-duty "No-Vibes" debugging and hardening orchestrator. Use this for complex, stubborn bugs
  where `review-code` has failed, or for "Red Teaming" (hardening) a codebase.
  Runs multiple agents in parallel (Thunderdome) using git worktree isolation.
triggers:
  - anvil
  - debug this (hard)
  - run thunderdome
  - harden this
  - red team this
  - deep debug
metadata:
  short-description: Multi-agent Thunderdome for judging and fixing complex bugs
provides:
  - hardening
composes: [task-monitor]

taxonomy:
  - hardening
  - validation
  - resilience
disciplines:
  - developer-tooling
  - evaluation-quality
  - compliance-security
---

# Anvil Skill

Anvil is the "Heavy Artillery" of debugging. It spawns a "Thunderdome" where multiple agents compete to fix a bug in isolated git worktrees.

## Commands
- **Debug:** \`./run.sh debug run --issue "..."\`
- **Harden:** \`./run.sh harden run\`
- **Cleanup:** \`./run.sh cleanup run --run-id ...\`
