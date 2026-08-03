# GOAL_DEWEY: Dewey Nightly Monitor-Sparta Repair Loop

**Slice ID:** `P0-dewey-monitor-sparta-nightly`  
**Status:** New engagement — existing June 23 solution zip needs updates and porting  
**Project:** `memory` (scripts) + `agent-skills/agents/dba-auditor` (Dewey agent)

## Primary Question

How should cron → Dewey → `/monitor-sparta` loop find every health failure and fix it until **29/29 PASS**, producing easy-to-debug logs that make failures obvious?

## Goals

1. **cron → Dewey → repair-cycle loop** works end-to-end with calibrated timeouts
2. **Health diff + stall detection** (already implemented) logs per-cycle progress showing which dimensions improved, regressed, or stayed stuck
3. **Timeouts calibrated** to real `health --json` runtime (~66s) and `health --fix` runtime (~120s)
4. **Worker wait** properly handles missing PID files (no hang when no workers launched)
5. **Ownership split** is handled correctly: Dewey repairs `qra_coverage_per_control` through the bounded create-qras lane, while product-owned dimensions such as `sparta_explorer_page_purpose` are logged and surfaced as operator/product-required.
6. **Stall detection** triggers after `DEWEY_STALL_LIMIT` cycles with no progress on a dimension
7. **Morning report** always written, even on failure
8. **Dewey cron re-enabled** in `services.yaml` with `enabled: true`
9. **Coverage closure** is the proof bar: Dewey keeps repairing QRA coverage until the SPARTA corpus is 100% covered, the configured scillm/Chutes call budget is exhausted, or a concrete non-QRA blocker is named with file/owner/evidence.

## Implemented Already

| Capability | File | Status |
|------------|------|--------|
| Health diff per cycle | `dewey_overnight_run.py:_health_diff()` | LIVE |
| Per-cycle step-level logging | `dewey_overnight_run.py:_format_repair_steps()` | LIVE |
| Persistent failure tracking | `dewey_overnight_run.py:step_iterate_monitor_sparta()` | LIVE |
| Stall warnings (DEWEY_STALL_LIMIT=8) | `dewey_overnight_run.py:_format_stall_warnings()` | LIVE |
| Per-step timing (duration_s) | `monitor_sparta.py:repair_cycle()` | LIVE |
| Timing for worker_wait, final health | `monitor_sparta.py:repair_cycle()` | LIVE |
| `once` subcommand for smoke testing | `dewey_overnight_run.py:cmd_once()` | LIVE |
| `dewey.log` always created with timestamps | `dewey_overnight_run.py:_session_log()` | LIVE |
| cron.sh with flock, wall clock, worker poll | `dewey_nightly_cron.sh` | LIVE |
| 12 unit tests passing | `tests/test_dewey_monitor_sparta_nightly.py` | LIVE |
| services.yaml pointing to dba-auditor | `memory/.agents/services.yaml` | CONFIGURED (disabled) |
| ARCHITECTURE.md from R1 WebGPT | `docs/create-architecture/dewey-monitor-sparta-nightly/ARCHITECTURE.md` | LIVE |

## What WebGPT Must Fix In This Engagement

### P1: Subprocess timeout calibration

**Problem:** `monitor_sparta.py health --json` takes ~66s. `health --fix` takes ~120s. `repair-cycle` calls each as subprocess with `subprocess.run(timeout=7200)` — but Dewey's own `once` command passed `--wait-timeout-s 60` which is too short for even the first health call.

**Fix needed:** Calibrate the default timeouts in `dewey_overnight_run.py` and the `once` smoke command to match real run times. The issue is in `cmd_once` and the `_run` helper.

**Target files:**
- `agent-skills/agents/dba-auditor/scripts/dewey_overnight_run.py`

### P2: Correct ownership of repairable vs product-owned dimensions

**Problem:** `repair-cycle` runs `health --fix`, `_run_qdrant_embed_batch()`, `_apply_sparta_repair_manifests()`, `_start_create_qras_backfill()`, and `_wait_for_monitor_workers()`. Some dimensions like `sparta_explorer_page_purpose` cannot be fixed by Dewey (they need UX React work). Others like `qra_coverage_per_control` need multi-night QRA pipeline runs.

**Fix needed:** Dewey must not treat ordinary QRA coverage gaps as operator-owned. It should:
- repair one bounded QRA target per cycle through `create_qras_repair_lane`
- write create-qras and storage proof artifacts
- retry QRA coverage until it clears or the configured scillm/Chutes call budget is exhausted
- stop as operator/product-required only when remaining failures are outside DBA ownership, such as `sparta_explorer_page_purpose`

When Dewey detects a dimension that can't be fixed by the DBA lane, it should:
- Log it clearly as `UNFIXABLE_BY_DEWEY: <dimension>`
- Track consecutive cycles it's been stuck
- Skip wasted repair attempts (don't re-run health --fix when only unfixable dims remain)
- Queue an operator/product manifest entry

**Target files:**
- `agent-skills/agents/dba-auditor/scripts/dewey_overnight_run.py`

### P3: Worker wait should not hang

**Problem:** `_wait_for_monitor_workers()` checks PID files that may not exist. When no workers were launched, it immediately returns `{"ok": True, "waited_s": 0}`. But the repair-cycle calls it with `wait_timeout_s=7200` by default. The real issue is the outer call needs `--wait` to even invoke the wait.

**Fix needed:** Document the wait behavior. The `repair-cycle` command's `--wait` flag must be honored — if no QRA backfill was launched, worker wait should be skipped. Already handled by the code but needs verification.

### P4: Morning report integration

**Problem:** The WebGPT ARCHITECTURE.md specifies a morning report format. Our current `dewey_overnight_run.py` calls `render_overnight_morning_report.py` which may not exist or may not match the expected format.

**Fix needed:** Implement the morning report writer from the existing solution zip, or verify the current path works.

**Target files:**
- `agent-skills/agents/dba-auditor/scripts/dewey_overnight_run.py`

### P5: Re-enable cron

**Problem:** `services.yaml` has `enabled: false` for `dewey-overnight-monitor-sparta`.

**Fix needed:** After P1-P4 are verified with a live smoke test, flip `enabled: true`.

**Target files:**
- `memory/.agents/services.yaml`

## Non-Goals

- Dewey will not mutate React/UX files
- Dewey will not bypass create-qras/QRA review gates, but Dewey owns invoking the bounded QRA coverage repair lane for monitor-sparta gaps.
- Dewey will not claim 29/29 if any dimension is unfixable by DB repair alone
- Dewey will not create new health dimensions or modify monitor-sparta thresholds

## Source-of-Truth Boundaries

| Artifact | Location | Authority |
|----------|----------|-----------|
| Health JSON | `monitor_sparta.py health --json` | Source of truth for pass/fail |
| Repair-cycle output | `repair-cycle --json` stdout | Source of truth for what was attempted |
| Dewey session log | `<session_dir>/dewey.log` | Human-readable audit trail |
| Dewey receipt | `<session_dir>/once_receipt.json` or `nightly_receipt.json` | Machine-readable audit |
| ARCHITECTURE.md | `docs/create-architecture/dewey-monitor-sparta-nightly/ARCHITECTURE.md` | Design contract |

## Acceptance Gates

| Gate | Evidence Required |
|------|-------------------|
| `dewey once` passes with real repair-cycle output | `once_receipt.json` exists, `repair-cycle` JSON has steps + duration_s |
| Health diff logged in dewey.log | dewey.log shows `IMPROVED=` / `STUCK=` lines |
| Stall warning fires at threshold | dewey.log shows `STALL WARNING:` after repeated cycles on same dim |
| Subprocess timeouts calibrated | `health --json` subprocess completes within 120s in the `once` run |
| Unfixable dims handled gracefully | dewey.log shows `UNFIXABLE_BY_DEWEY` for UX/pipeline dims |
| Morning report written | `morning_report.md` exists with stop_reason and final health |
| Services.yaml re-enabled | `enabled: true` with note about monitoring |

## Required Output (WebGPT)

If material ambiguity remains, return numbered clarifying questions. Otherwise return a **solution zip** with:

1. `ARCHITECTURE.md` — updated with current design
2. `agent-skills/agents/dba-auditor/scripts/dewey_overnight_run.py` — updated orchestrator with P1-P4 fixes
3. `memory/.agents/services.yaml` — with `enabled: true`
4. `tests/test_dewey_monitor_sparta_nightly.py` — updated tests
5. `MANIFEST.json` — bundle manifest
6. `prompt_improvements.md` — what to improve next round
