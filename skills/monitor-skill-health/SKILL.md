---
name: monitor-skill-health
description: >
  Nightly skill and agent quality monitor that scans registered skills plus
  agents for best-practice violations, aspirational gaps, and trend drift.
  Produces per-target findings and an aggregate summarized report for tracking
  over time.
triggers:
  - monitor skill health
  - nightly skill audit
  - scan all skills for violations
  - scan all agents for violations
  - aggregate skill health report
  - skill best-practices monitor
allowed-tools:
  - Bash
  - Read
metadata:
  short-description: Nightly best-practice and aspirational quality monitor for skills and agents
provides:
  - skill-health-monitoring
  - aggregate-reporting
  - trend-tracking
  - ticket-draft-handoff
composes:
  - assess
  - review-code
  - memory
  - scheduler
  - task-monitor
  - ticket
  - tau

taxonomy:
  - validation
  - observability
  - quality
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Monitor Skill Health

Monitors all registered skills and agents and reports:
- Best-practice violations (`best-practices-kde`, `best-practices-python`, `best-practices-react`, `best-practices-skills`)
- Agent contract violations (`best-practices-agent`)
- Missing and aspirational code signals
- What works well, what needs fixing, and explicit next steps
- Aggregate summarized report for nightly tracking

## Continuous Operation (Non-Negotiable)

This skill is **always-on as a reporter and ticket producer**. It:
- Runs on its configured schedule indefinitely until explicitly halted by the user
- Writes durable audit state and trend artifacts on every cycle
- Converts concrete violations into preview-first `$ticket` maintenance drafts
- May create GitHub tickets only when the caller explicitly passes `tickets --apply`
- Does not patch skills, deprecate agents, or close issues from the monitor path
- Gracefully handles restarts and maintains state across cycles
- Is designed for multi-day/week/month autonomous operation

Repair work belongs to the Tau-backed maintainer lane. `monitor-skill-health`
creates normalized work items; `agent-skill-maintainer` leases exactly one item,
routes a bounded repair subagent, dispatches an independent verifier, attaches
deterministic proof, and closes only after the proof gate is satisfied.

**Anti-pattern**: Letting the monitor silently patch broad findings or close
tickets from its own report is UNACCEPTABLE. The monitor owns observation,
normalization, and ticket handoff; the maintainer owns one-ticket repair.

## Commands

```bash
# Run full audit over registered skills and agents
./run.sh audit

# Run full audit but skip deep code review stage
./run.sh audit --no-deep-review

# Dry run on a subset
./run.sh audit --limit 5 --no-memory --json

# Single skill
./run.sh audit --skill monitor-taxonomy --json

# Single agent
./run.sh audit --agent skill-maintainer --json

# Draft one maintenance ticket per concrete violation from the latest audit
./run.sh tickets --json

# Create GitHub tickets explicitly after inspecting the preview artifact
./run.sh tickets --apply --repo grahama1970/agent-skills

# Show latest aggregate summary
./run.sh status

# Show trend history
./run.sh history --limit 30

# Register nightly scheduler job
./run.sh register --cron "0 2 * * *"
```

## Output Artifacts

State directory (default):
`~/.pi/monitor-skill-health`

Generated artifacts:
- `latest_results.jsonl` - one JSON finding per skill or agent target
- `latest_summary.json` - aggregate summarized report for latest run
- `history.jsonl` - run-over-run trend entries
- `task_state.json` - task-monitor compatible progress snapshot
- `ticket_drafts/<run_id>.json` - preview-first maintenance tickets with `tau.agent_handoff.v1` metadata
- `runs/<run_id>/...` - immutable per-run archive

## Composition Strategy

This skill is intentionally thin and composes existing capabilities:
- `/assess` for baseline project-health extraction
- `/memory` to persist high-value aggregate run summaries
- `/scheduler` for nightly automation
- `/task-monitor` via state file output for live progress
- `/review-code` for automatic deep review of high-risk skills (`provider=openai`, `model=gpt-5.2-codex`)

## Aggregate Summary Contract

Each run writes `latest_summary.json` with:
- `run_id`, `started_at`, `finished_at`
- `overall_status` (`healthy`, `warning`, `critical`)
- `total_skills` / `total_targets`
- `target_type_counts`
- `status_counts`
- `severity_counts`
- `rule_pack_counts`
- `top_issues` (highest-severity normalized findings)

This summary is designed so project agents can immediately decide what to fix next.

## Ticket Handoff Contract

`./run.sh tickets` reads `latest_results.jsonl` and emits one maintenance draft
per concrete `needs_fix` violation. Aspirational gaps are excluded by default
and require `--include-aspirational`.

Each draft contains:
- `$ticket` fields: title, target, invariant, cleanup, scoped files, required proof, route, requested repair agent, and labels
- `tau.agent_handoff.v1` metadata for one-ticket-at-a-time maintainer leasing
- the originating monitor run, target type, skill/agent id, status, and normalized finding

Default mode is preview-only. `--apply` is the only mode that creates GitHub
issues. Ticket closure remains outside this skill and requires deterministic
proof attached through `$ticket`.
