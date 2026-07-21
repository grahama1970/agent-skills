# Project Knowledge: monitor-herdr

**Last updated:** 2026-07-21 13:38 by agent
**Status:** Active development

## Current Understanding

- Project initialized, knowledge tracking started
- 2026-07-21 monitor-herdr is a fail-closed Herdr pane monitor for early-stopped agents. The current pushed implementation uses Herdr's documented pane-run submit path for live restart prompts instead of relying on paste-plus-Enter. The monitor still requires post-submit evidence before recording submit_confirmed:true, and it leaves blocked, unknown, fallback-idle, approval-like, no-goal, and already-achieved panes alone.
- 2026-07-21 production cron is installed from /home/graham/workspace/experiments/agent-skills-cron-main with MONITOR_HERDR_INVOCATION_SOURCE=cron. Cron health is tracked separately from manual/plugin runs through latest_cron_receipt so manual live evals cannot hide a stale or broken scheduler.
- 2026-07-21 live cron-sourced proof receipt: /home/graham/.local/state/monitor-herdr/receipts/monitor-herdr-20260721T172249320422Z/receipt.json reports invocation_source=cron, status=RESTART_PROMPTS_SUBMITTED, ok=true, prompts=1, submit_confirmed=[true], and transport=herdr_pane_run.

## Recent Decisions

| Date | Decision | Why |
|------|----------|-----|
| 2026-07-21 | Initialize project knowledge | Enable shared human/agent context |
| 2026-07-21 | Use herdr pane run for monitor-herdr submit transport | Installed Herdr 0.7.1 documents pane run as text plus Enter, and live evidence showed the older paste-plus-Enter path could leave prompts visible but not executed. |
| 2026-07-21 | Keep scheduler health cron-sourced | run.sh status must distinguish latest_receipt from latest_cron_receipt because a manual eval can pass while the installed cron checkout is stale. |

## Open Questions

- [ ] What are the key architectural decisions?
- [ ] What are the known issues?

## Key Files

| File | Purpose |
|------|---------|
| PROJECT_KNOWLEDGE.md | Shared monitor-herdr project knowledge |
| SKILL.md | Operational contract agents must read before using or changing monitor-herdr |
| README.md | Human-facing guide with runtime shape, plugin usage, and proof boundaries |
| scripts/monitor_herdr.py | Main Herdr socket monitor, pane selection, prompt send, and receipt writer |
| scripts/herdr_terminal_control.py | Herdr CLI helpers, including pane-run submit transport |
| scripts/cron_support.py | Cron install and scheduler health reporting |
| evals/live_herdr_e2e.py | Opt-in live Herdr eval for real observation/apply receipts |
| evals/live_plugin_e2e.py | Opt-in live Herdr plugin wrapper eval |
| herdr-plugin/herdr-plugin.toml | Native Herdr plugin manifest |

## Infrastructure State

<!-- Auto-populated from /project-state --quick -->
