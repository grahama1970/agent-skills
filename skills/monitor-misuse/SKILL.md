---
name: monitor-misuse
description: >
  Nightly analysis of misuse_events collection to detect new patterns,
  propose corrections, and track skill health. Self-improving misuse guards.
triggers:
  - analyze misuse events
  - check skill misuses
  - monitor misuse patterns
  - review api misuses
provides:
  - misuse-analysis
  - correction-proposals
  - skill-health-metrics
composes:
  - memory
  - scillm
  - scheduler
  - monitor-skills
  - task-monitor
taxonomy:
  - observability
  - self-improvement
  - drift-detection
disciplines:
  - observability-operations
  - evaluation-quality
---

# monitor-misuse

Nightly job that analyzes `misuse_events` across all skills to:
1. Detect new misuse patterns (cluster unknown errors)
2. Propose corrections via LLM
3. Track which skills need better docs
4. Auto-commit high-confidence corrections

## Architecture

```
misuse_events collection (all skills)
         │
         ▼
┌────────────────────────┐
│   ./run.sh analyze     │  ← Runs nightly at 3:00am
│                        │
│  1. Query last 24h     │
│  2. Group by skill     │
│  3. Filter was_known=F │
│  4. Cluster similar    │
│  5. LLM propose fixes  │
│  6. Store proposals    │
└────────────────────────┘
         │
         ▼
misuse_corrections collection
(status: pending → approved → applied)
         │
         ▼
┌────────────────────────┐
│   ./run.sh apply       │  ← Human reviews, then applies
│                        │
│  1. Fetch approved     │
│  2. Group by skill     │
│  3. Locate guard file  │
│  4. Update corrections │
│  5. Mark as applied    │
└────────────────────────┘
         │
         ▼
skill/_misuse_guard.py updated
(COLLECTION_CORRECTIONS dict)
```

## Usage

```bash
# Manual run (analyzes last 24h)
./run.sh analyze

# Analyze specific time window
./run.sh analyze --hours 72

# List pending corrections
./run.sh pending

# Approve a correction (changes status to approved)
./run.sh approve --key <correction_key>

# Apply approved corrections to skill files
./run.sh apply                    # All skills
./run.sh apply --skill memory     # Specific skill
./run.sh apply --dry-run          # Preview without changes

# List skills with registered misuse guards
./run.sh skills

# Report: misuse stats by skill
./run.sh report
```

## Skill Registry

For `/monitor-misuse` to apply corrections to a skill, the skill must be
registered in `scripts/skill_registry.py`:

```python
SKILL_GUARDS = {
    "memory": SkillMisuseGuard(
        skill_name="memory",
        guard_path=Path("${HOME}/workspace/experiments/memory/src/graph_memory/service/app/_misuse_guard.py"),
        corrections_var="COLLECTION_CORRECTIONS",
    ),
    # Add your skill here after adopting misuse_guard
}
```

**To register a new skill:**
1. Copy `misuse_guard_template.py` from `/best-practices-skills`
2. Add logging calls to your validators
3. Register the skill in `skill_registry.py`

Skills not in the registry will have their misuse events analyzed, but
corrections must be applied manually.

## Event Schema (misuse_events)

| Field | Type | Description |
|-------|------|-------------|
| `_key` | str | Hash of skill:endpoint:error_type:sent_value |
| `skill` | str | Skill name (memory, scillm, fetcher) |
| `endpoint` | str | Endpoint path |
| `error_type` | str | Category (wrong_collection, missing_param) |
| `sent_value` | str | What the caller sent |
| `correct_value` | str? | What they should have sent |
| `was_known` | bool | True if we had a correction |
| `ts` | int | First occurrence timestamp |
| `last_ts` | int | Most recent occurrence |
| `count` | int | Total occurrences |

## Correction Schema (misuse_corrections)

| Field | Type | Description |
|-------|------|-------------|
| `_key` | str | Hash of skill:error_type:sent_value |
| `skill` | str | Target skill |
| `error_type` | str | Error category |
| `sent_value` | str | The wrong value |
| `proposed_correction` | str | LLM-proposed fix |
| `confidence` | float | 0.0-1.0 confidence score |
| `occurrence_count` | int | How many times this was seen |
| `status` | str | pending / approved / rejected / applied |
| `proposed_at` | int | Timestamp of proposal |
| `reviewed_at` | int? | Timestamp of review |
| `applied_at` | int? | Timestamp of application |

## Clustering Algorithm

1. Group by `skill` + `error_type`
2. Within each group, cluster `sent_value` by:
   - Exact match (dedup)
   - Levenshtein distance < 3 (typos)
   - Same prefix (partial matches)
3. For clusters with count >= 3, generate correction proposal

## LLM Correction Proposal

```python
prompt = f"""
Skill: {skill}
Endpoint: {endpoint}
Error type: {error_type}
Wrong values seen: {sent_values}  # clustered examples
Occurrences: {total_count}

Based on the misuse pattern, propose a correction mapping.
Return JSON: {{"correction": "correct_value", "confidence": 0.0-1.0}}

Known patterns in this skill:
{existing_corrections}
"""
```

## Auto-Commit Rules

Corrections are auto-applied (no human review) when:
- `confidence >= 0.95` AND
- `occurrence_count >= 10` AND
- Correction matches existing pattern (e.g., plural→singular)

Otherwise, corrections stay `pending` for human review.

## Scheduler Integration

Registered as `monitor-misuse-nightly`:
- Runs at 3:00am daily
- Depends on: misuse_events having data
- Notifies: Slack #skill-health on new high-frequency patterns

```bash
# Register with scheduler
/scheduler create monitor-misuse-nightly \
  --cron "0 3 * * *" \
  --command "./run.sh analyze --auto-apply"
```

## Metrics Tracked

- Misuse events per skill (24h, 7d, 30d)
- Unknown vs known pattern ratio
- Time to correction (proposal → applied)
- Top offending error types
- Skills with highest misuse rates

## Integration with /monitor-skills

`/monitor-misuse` is part of the skill health monitoring ecosystem:

```
/monitor-skills                    /monitor-misuse
─────────────────                  ─────────────────
Skill VERSION drift                Skill API USAGE drift
"Is this skill up to date?"        "Is this skill being misused?"
         │                                  │
         └──────────┬───────────────────────┘
                    ▼
              /task-monitor
         (unified health dashboard)
```

**Shared taxonomy tags:** `observability`, `drift-detection`

When `/monitor-skills` syncs a skill to a new version, any pending
corrections in `/monitor-misuse` for that skill should be reviewed —
the new version may have already fixed the pattern.

## Integration with /task-monitor

Reports status to task-monitor for dashboard visibility:

```python
# After analyze completes
task_monitor.report(
    skill="monitor-misuse",
    status="ok" if errors == 0 else "warn",
    metrics={
        "events_24h": count,
        "unknown_patterns": unknown,
        "pending_corrections": pending,
    }
)
```
