# Clarify, Then Create Full Solution — Dewey monitor-sparta nightly

## Objective

**The problem:** Dewey (the DBA Auditor cron agent) runs `/monitor-sparta repair-cycle` every night but gets stuck at 24/29 PASS with no clear logs showing WHY health isn't improving. The cron has been paused.

**What we need:** A hardened Dewey nightly loop that:
1. Runs repair-cycle until 29/29 PASS or budget exhausted
2. Produces easy-to-debug logs showing exactly what each cycle attempted and what changed
3. Calibrated timeouts for subprocess calls (health --json takes ~66s, health --fix takes ~120s)
4. Gracefully handles unfixable dimensions (UX guardrails, QRA pipeline gaps)
5. Detects and warns on stall conditions
6. Can be re-enabled in cron

**Round 1 rule:** If material ambiguity remains, return only numbered clarifying questions. If ready, return the full solution zip.

---

## GOAL_DEWEY.md

```markdown
# GOAL_DEWEY: Dewey Nightly Monitor-Sparta Repair Loop

**Slice ID:** P0-dewey-monitor-sparta-nightly
**Status:** New engagement
**Project Repos:**
  - memory: /home/graham/workspace/experiments/memory (monitor_sparta.py, services.yaml)
  - agent-skills: /home/graham/workspace/experiments/agent-skills (Dewey scripts in agents/dba-auditor/)

## Primary Question

How should cron -> Dewey -> /monitor-sparta loop find every health failure and fix it until 29/29 PASS, producing easy-to-debug logs?

## Implemented Already

| Capability | Location | Status |
|------------|----------|--------|
| Health diff per cycle (IMPROVED/REGRESSED/STUCK) | dewey_overnight_run.py | LIVE |
| Per-cycle step-level logging | dewey_overnight_run.py | LIVE |
| Persistent failure tracking | dewey_overnight_run.py | LIVE |
| Stall warnings at DEWEY_STALL_LIMIT=8 cycles | dewey_overnight_run.py | LIVE |
| Per-step timing (duration_s) on repair-cycle | monitor_sparta.py | LIVE |
| `once` subcommand for smoke testing | dewey_overnight_run.py | LIVE |
| dewey.log always created with timestamps | dewey_overnight_run.py | LIVE |
| cron.sh with flock, wall clock, worker poll | dewey_nightly_cron.sh | LIVE |
| 12 unit tests passing | tests/test_dewey_monitor_sparta_nightly.py | LIVE |
| services.yaml pointing to dba-auditor | memory/.agents/services.yaml | CONFIGURED (disabled) |
| ARCHITECTURE.md from R1 WebGPT | docs/create-architecture/.../ARCHITECTURE.md | LIVE |

## What WebGPT Must Fix

### P1: Subprocess timeout calibration
health --json takes ~66s, health --fix takes ~120s. The `once` command and subprocess defaults need calibrated timeouts.

### P2: Graceful handling of unfixable dimensions
sparta_explorer_page_purpose (UX) and qra_coverage_per_control (pipeline) cannot be fixed by Dewey. Log clearly, skip wasted attempts, detect stall.

### P3: Worker wait should not hang
Verify _wait_for_monitor_workers() returns immediately when no workers launched.

### P4: Morning report integration
Implement or verify the morning report writer.

### P5: Re-enable cron
Flip enabled: true after verification.

## Non-Goals
- Dewey will not mutate React/UX files
- Dewey will not replace human QRA review

## Acceptance Gates
- dewey once passes with real repair-cycle JSON output
- Health diff and stall warnings in dewey.log
- Subprocess timeouts calibrated to real run times
- Unfixable dims handled gracefully (logged, not retried wastefully)
- Morning report written
- services.yaml re-enabled
```

---

## Current File Contents

### dewey_overnight_run.py (510 lines) — the orchestrator
Path: `agent-skills/agents/dba-auditor/scripts/dewey_overnight_run.py`

Key design:
- `start` subcommand: backup-first, iterate repair-cycle until pass
- `once` subcommand: single cycle for smoke testing, no backup
- Backup-first via db_repair_session.py
- Per-cycle logging via _session_log() -> dewey.log
- _health_diff() for cycle-to-cycle comparison
- _format_repair_steps() for human-readable step output
- _format_stall_warnings() for stall detection
- Persistent failure tracking across cycles
- STALL_THRESHOLD = DEWEY_STALL_LIMIT (default 8)

### dewey_nightly_cron.sh (48 lines) — cron wrapper
Path: `agent-skills/agents/dba-auditor/scripts/dewey_nightly_cron.sh`

Features:
- Flock-based mutual exclusion
- Wall-clock timeout (DEWEY_WALL_CLOCK_S=43200)
- Worker poll interval (DEWEY_WORKER_POLL_S=30)
- Logs to artifacts/dewey_nightly/<run_id>/cron.log

### monitor_sparta.py repair-cycle (~80 lines in the function)
Path: `memory/scripts/validation/monitor_sparta.py` (10,780 line file)

The repair-cycle command:
1. `health --json` baseline (takes ~66s)
2. Apply sparta repair manifests (if relationship/framework dims failing)
3. Run Qdrant embed batch (if embedding dims failing)
4. `health --fix` (takes ~120s, runs all fix lanes)
5. Start create-qras backfill (if QRA coverage dims failing)
6. Wait for workers (up to wait_timeout_s)
7. `health --json` final (takes ~66s)

Each step now logs `duration_s` (wall-clock seconds).

---

## Existing Solution Zip from June 23

An earlier WebGPT engagement produced `memory-dewey-monitor-sparta-nightly-solution.zip` with:
- ARCHITECTURE.md (state machine, lane table, budgets, rollback)
- monitor_sparta.py (785-line clean version — NOT our 10,780-line real file)
- dewey_overnight_run.py (528-line version with `start` and `once` commands)
- dewey_nightly_cron.sh (with flock)
- sanity_live_repair_cycle_smoke.sh (smoke test harness)
- test_dewey_monitor_sparta_nightly.py (fixture tests)
- services.yaml alignment
- prompt_improvements.md

This was never ported. We kept the dba-auditor location for scripts (not memory/scripts/validation/).

---

## Current Health State (2026-06-24)

**24/29 PASS** from `health --json`:
- FAIL: embedding_gaps (170 sparta_controls missing embeddings)
- FAIL: description_completeness 
- FAIL: qra_coverage_per_control
- FAIL: inline_embedding_policy
- FAIL: sparta_explorer_page_purpose (UX guardrails)

Dimensions that haven't changed in the last 62 Dewey cycles.

---

## Test Results

**12/12 unit tests passing:**
- test_health_summary_parses_standard_format
- test_health_summary_29_pass
- test_health_summary_waives_mutation_default
- test_health_diff_improvement
- test_health_diff_regression
- test_health_diff_no_change
- test_health_diff_full_pass
- test_format_diff_line
- test_format_repair_steps
- test_format_stall_warnings
- test_format_stall_warnings_no_warning
- test_compact_cycle_record

**Live test (dewey once --wait-timeout-s 60):**
- Baseline logged correctly: 23/28 failed=[embedding_gaps, description_completeness, qra_coverage_per_control, inline_embedding_policy, sparta_explorer_page_purpose]
- repair-cycle subprocess timed out (60s too short for health --json at 66s)

---

## Infrastructure

All running:
- UX Lab: HTTP 200 on :3002
- scillm: HTTP 200 on :4001 (161K sec uptime, gpt-5.5 proven with 171 successes)
- ArangoDB: responding on :8529
- Dewey session dir: /mnt/storage12tb/skills/review-db/outputs/dewey-sessions/

---

## Required Output (WebGPT)

If material ambiguity remains, return only numbered clarifying questions.

If ready, return a **solution zip** named `dewey-P0-solution.zip`:

1. `ARCHITECTURE.md` — updated design contract
2. `agent-skills/agents/dba-auditor/scripts/dewey_overnight_run.py` — fixed orchestrator (P1-P4)
3. `agent-skills/agents/dba-auditor/scripts/dewey_nightly_cron.sh` — updated cron wrapper
4. `agent-skills/agents/dba-auditor/scripts/sanity_live_repair_cycle_smoke.sh` — updated smoke test
5. `agent-skills/agents/dba-auditor/tests/test_dewey_monitor_sparta_nightly.py` — updated tests
6. `memory/.agents/services.yaml` — with enabled: true
7. `MANIFEST.json`
8. `prompt_improvements.md`

Do not return PASS/NEEDS_CHANGES/BLOCKED. Create finished files only.
