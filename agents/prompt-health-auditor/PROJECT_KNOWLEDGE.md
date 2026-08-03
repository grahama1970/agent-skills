# Project Knowledge: prompt-health-auditor

**Last updated:** 2026-06-26 by agent
**Status:** Initial contract

## Current Understanding

- Petey owns `prompt_health` monitor-sparta queue issues.
- Petey must run before Qbert (`qra-auditor`) when both prompt-health and QRA issues are READY.
- Petey prepares prompt contract bundles, expected responses, validators, and review-prompt receipts.
- Petey does not run `/create-qras`, mutate Arango/Qdrant, or promote prompts to production without a reviewed receipt.

## Key Files

| File | Purpose |
|------|---------|
| `/home/graham/workspace/experiments/agent-skills/agents/prompt-health-auditor/persona.yaml` | Petey subagent contract. |
| `/home/graham/workspace/experiments/agent-skills/skills/monitor-sparta/SKILL.md` | Lane ownership and Petey-before-Qbert ordering contract. |
| `/home/graham/workspace/experiments/memory/scripts/validation/monitor_sparta_repair_queue.py` | Queue issue builder that prioritizes `prompt_health` before QRA lanes. |

