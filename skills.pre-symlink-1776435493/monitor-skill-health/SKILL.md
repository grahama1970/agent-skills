---
name: monitor-skill-health
description: >
  Nightly skill quality monitor that scans registered skills for best-practice
  violations, aspirational gaps, and trend drift. Produces per-skill findings and
  an aggregate summarized report for tracking over time.
triggers:
  - monitor skill health
  - nightly skill audit
  - scan all skills for violations
  - aggregate skill health report
  - skill best-practices monitor
allowed-tools:
  - Bash
  - Read
metadata:
  short-description: Nightly best-practice and aspirational quality monitor for skills
provides:
  - skill-health-monitoring
  - aggregate-reporting
  - trend-tracking
composes:
  - assess
  - review-code
  - memory
  - scheduler
  - task-monitor

taxonomy:
  - validation
  - observability
  - quality
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Monitor Skill Health

Monitors all registered skills and reports:
- Best-practice violations (`best-practices-kde`, `best-practices-python`, `best-practices-react`, `best-practices-skills`)
- Missing and aspirational code signals
- What works well, what needs fixing, and explicit next steps
- Aggregate summarized report for nightly tracking

## Continuous Operation (Non-Negotiable)

This skill is **always-on**. It:
- Runs on its configured schedule indefinitely — it NEVER stops unless explicitly halted by the user
- The agent MUST NOT stop and wait for the human to ask for status or remember to check
- If a cycle fails, diagnose the failure, attempt auto-repair, and continue
- Only escalate to the human if genuinely blocked after exhausting /dogpile research
- Gracefully handles restarts and maintains state across cycles
- Is designed for multi-day/week/month autonomous operation

**Anti-pattern**: Reporting status and waiting for the human to ask "what next?" is UNACCEPTABLE. The agent must proactively fix issues and continue the monitoring loop.

## Commands

```bash
# Run full audit over registered skills
./run.sh audit

# Run full audit but skip deep code review stage
./run.sh audit --no-deep-review

# Dry run on a subset
./run.sh audit --limit 5 --no-memory --json

# Single skill
./run.sh audit --skill monitor-taxonomy --json

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
- `latest_results.jsonl` - one JSON finding per skill
- `latest_summary.json` - aggregate summarized report for latest run
- `history.jsonl` - run-over-run trend entries
- `task_state.json` - task-monitor compatible progress snapshot
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
- `total_skills`
- `status_counts`
- `severity_counts`
- `rule_pack_counts`
- `top_issues` (highest-severity normalized findings)

This summary is designed so project agents can immediately decide what to fix next.
