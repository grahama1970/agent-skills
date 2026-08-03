# Clarify, Then Create Full Solution — Dewey monitor-sparta nightly

## Objective

The problem: Dewey (the DBA Auditor cron agent) runs monitor-sparta repair-cycle every night but gets stuck at 24/29 PASS with no clear logs showing WHY health isn't improving. The cron has been paused.

What we need: A hardened Dewey nightly loop that:
1. Runs repair-cycle until 29/29 PASS or budget exhausted
2. Produces easy-to-debug logs showing exactly what each cycle attempted and what changed
3. Calibrated timeouts for subprocess calls (health --json takes about 66 seconds, health --fix takes about 120 seconds)
4. Gracefully handles unfixable dimensions (UX guardrails, QRA pipeline gaps)
5. Detects and warns on stall conditions
6. Can be re-enabled in cron

Round 1 rule: If material ambiguity remains, return only numbered clarifying questions.
If ready, return the full solution zip named `dewey-P0-solution.zip`.

DO NOT return PASS/NEEDS_CHANGES/BLOCKED. Create finished files only.

---

## GOAL_DEWEY.md

Slice ID: P0-dewey-monitor-sparta-nightly

### Primary Question

How should cron -> Dewey -> monitor-sparta loop find every health failure and fix it until 29/29 PASS, producing easy-to-debug logs?

### Implemented Already

| Capability | Status |
|------------|--------|
| Health diff per cycle (IMPROVED/REGRESSED/STUCK) | LIVE |
| Per-cycle step-level logging | LIVE |
| Persistent failure tracking | LIVE |
| Stall warnings at DEWEY_STALL_LIMIT=8 cycles | LIVE |
| Per-step timing (duration_s) on repair-cycle | LIVE |
| once subcommand for smoke testing | LIVE |
| dewey.log always created with timestamps | LIVE |
| cron.sh with flock, wall clock, worker poll | LIVE |
| 12 unit tests passing | LIVE |
| services.yaml pointing to dba-auditor | CONFIGURED (disabled) |
| ARCHITECTURE.md from R1 WebGPT | LIVE |

### What WebGPT Must Fix

P1: Subprocess timeout calibration
- health --json takes  about 66 seconds, health --fix takes  about 120 seconds. The once command and subprocess defaults need calibrated timeouts.

P2: Graceful handling of unfixable dimensions
- sparta_explorer_page_purpose (UX) and qra_coverage_per_control (pipeline) cannot be fixed by Dewey. Log clearly, skip wasted attempts, detect stall.

P3: Worker wait should not hang
- Verify _wait_for_monitor_workers() returns immediately when no workers launched.

P4: Morning report integration
- Implement or verify the morning report writer.

P5: Re-enable cron
- Flip enabled: true after verification.

### Non-Goals
- Dewey will not mutate React/UX files
- Dewey will not replace human QRA review

---

## Current File Architecture

### dewey_overnight_run.py (510 lines) — the orchestrator
Location: agent-skills/agents/dba-auditor/scripts/

Key design:
- start subcommand: backup-first, iterate repair-cycle until pass
- once subcommand: single cycle for smoke testing, no backup
- Backup-first via db_repair_session.py
- Per-cycle logging via _session_log() -> dewey.log
- _health_diff() for cycle-to-cycle comparison (IMPROVED / REGRESSED / STUCK)
- _format_repair_steps() for human-readable step output
- _format_stall_warnings() for stall detection
- Persistent failure tracking across cycles
- STALL_THRESHOLD = DEWEY_STALL_LIMIT (default 8)

### dewey_nightly_cron.sh (48 lines) — cron wrapper
Features: flock-based mutual exclusion, wall-clock timeout (43200s), worker poll (30s)

### monitor_sparta.py repair-cycle function
Location: memory/scripts/validation/monitor_sparta.py

The repair-cycle command steps:
1. health --json baseline (takes  about 66 seconds)
2. Apply sparta repair manifests (if relationship/framework dims failing)
3. Run Qdrant embed batch (if embedding dims failing)
4. health --fix (takes  about 120 seconds, runs all fix lanes)
5. Start create-qras backfill (if QRA coverage dims failing)
6. Wait for workers (up to wait_timeout_s)
7. health --json final (takes  about 66 seconds)

Each step now logs duration_s (wall-clock seconds).

---

## Existing Solution Zip from June 23

An earlier WebGPT engagement produced a solution zip with:
- ARCHITECTURE.md (state machine, lane table, budgets, rollback)
- monitor_sparta.py (785-line clean version)
- dewey_overnight_run.py (528-line version with start and once commands)
- dewey_nightly_cron.sh (with flock)
- sanity_live_repair_cycle_smoke.sh (smoke test harness)
- test_dewey_monitor_sparta_nightly.py (fixture tests)
- services.yaml alignment
- prompt_improvements.md

This was never ported. Keeping the dba-auditor location for scripts.

---

## Current Health State (2026-06-24)

24/29 PASS from health --json:
- FAIL: embedding_gaps (170 sparta_controls missing embeddings)
- FAIL: description_completeness
- FAIL: qra_coverage_per_control
- FAIL: inline_embedding_policy
- FAIL: sparta_explorer_page_purpose (UX guardrails)

---

## Test Results

12/12 unit tests passing:
- Health summary parsing, 29-pass detection, mutation waiver
- Health diff improvement/regression/no-change/full-pass
- Format diff line, repair steps, stall warnings, compact cycle record

Live test (dewey once --wait-timeout-s 60):
- Baseline logged correctly: 23/28 failed
- repair-cycle subprocess timed out (60s too short for health --json at 66s)

---

## Infrastructure Status

All running:
- UX Lab: responding on port 3002
- scillm: healthy on port 4001
- ArangoDB: responding on port 8529

---

## Required Output (WebGPT)

If material ambiguity remains, return only numbered clarifying questions.

If ready, return a solution zip named dewey-P0-solution.zip with MANIFEST.json containing:

1. ARCHITECTURE.md — updated design contract
2. agent-skills/agents/dba-auditor/scripts/dewey_overnight_run.py — fixed orchestrator (P1-P4)
3. agent-skills/agents/dba-auditor/scripts/dewey_nightly_cron.sh — updated cron wrapper
4. agent-skills/agents/dba-auditor/scripts/sanity_live_repair_cycle_smoke.sh — updated smoke test
5. agent-skills/agents/dba-auditor/tests/test_dewey_monitor_sparta_nightly.py — updated tests
6. memory/.agents/services.yaml — with enabled: true
7. MANIFEST.json
8. prompt_improvements.md

Do not return PASS/NEEDS_CHANGES/BLOCKED. Create finished files only.
Do not paste multiple files inline — use one zip with manifest.
