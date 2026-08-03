# R2: Fix ALL remaining Dewey bugs — one zip to close P0

This is a **repair engagement**. A previous round produced `dewey-P0-solution.zip` which was ported and tested. 16 unit tests pass and the new logging works correctly (per-command timing, baseline health, cycle tracking). But there are several bugs and gaps that need fixing in one shot.

**Return ONE zip** named `dewey-P0-r2-fixes.zip` containing ALL fixed files. Fix EVERY issue listed below.

---

## Bug 1: repair-cycle has wrong subprocess call

Your previous solution called `repair-cycle` with fictional flags: `--receipt`, `--worker-poll-s`, `--qra-batch-limit`. I fixed these mechanically in the port. But the `repair_cycle()` function in `dewey_overnight_run.py` needs to match the real `monitor_sparta.py repair-cycle` API exactly:

**Real API:**
```
monitor_sparta.py repair-cycle
  --artifact-dir PATH          # required
  --embed-batch-limit INT      # required
  --wait-timeout-s INT         # required
  --json                       # required for machine output
```

**Fix needed:** Verify the current `repair_cycle()` function in the file uses ONLY these flags. The current port removed the fictional flags but needs review.

---

## Bug 2: Total timeout too tight for one cycle

Live test showed: `health --json` = 71s, then `repair-cycle` was launched with `wait_timeout_s + 300s` margin. But `repair-cycle` internally calls:
1. `health --json` (71s) 
2. optional repair manifests
3. optional Qdrant embed
4. `health --fix` (~120s)
5. optional create-qras backfill
6. `_wait_for_monitor_workers` (up to wait_timeout_s)
7. `health --json` (71s)

Total realistic max for one cycle: ~600-900s. The `once` command's outer timeout needs calibration.

**Fix needed:** Add `--repair-timeout-s` CLI flag and set reasonable defaults. The `compute_repair_cycle_timeout_s` function exists but was removed from the receipt/wiring. Restore and use it in both `start` and `once` commands. Default should be `wait_timeout_s + 600` (not 300).

---

## Bug 3: Unfixable dims still trigger repair-cycle

The code has `UNFIXABLE_DIMENSIONS = {"sparta_explorer_page_purpose": "...", "qra_coverage_per_control": "..."}` and `should_stop_for_unfixable_only()` exists. But testing shows repair-cycle still runs when only these dims remain.

**Fix needed:** In `run_dewey()`, BEFORE launching repair-cycle, check if ALL remaining failures are in `UNFIXABLE_DIMENSIONS`. If so, write morning report with stop_reason="operator_required_unfixable_only", exit code 10, and skip repair-cycle entirely.

---

## Bug 4: Worker wait hangs when no workers launched

The `_wait_for_monitor_workers()` function in `monitor_sparta.py` polls PID files. When no QRA backfill or health autofix was launched, it should return immediately. Currently may poll up to `wait_timeout_s`.

**Fix needed:** This is in `monitor_sparta.py` (not in the Dewey zip). Add a quick check: if `_start_create_qras_backfill()` was NOT called (check if the step exists and has a non-empty payload), skip the wait. Or add a `--no-wait` flag pass-through from the Dewey caller.

---

## Bug 5: `start` command untested

The `start` command (with backup, multi-cycle loop, verify, revert, morning report) has never been tested against real infrastructure. The `db_session_command()` function calls `db_repair_session.py` which is in the agent-skills repo, not in memory/scripts/validation/.

**Fix needed:** Verify `db_session_command()` in the `start` flow:
1. It calls `memory/scripts/validation/db_repair_session.py` - but that script lives at `agent-skills/agents/dba-auditor/scripts/db_repair_session.py`, not in the memory repo. Fix the path or add a fallback.
2. The backup step should skip gracefully if the script isn't found (already has `required: bool` param).
3. Test that verify detects regression.

---

## Bug 6: `once` command should work as cron smoke test

The `sanity_live_repair_cycle_smoke.sh` script runs `dewey once --json` and validates the receipt. After fixing Bug 2 (timeout calibration), this must pass with the real infra.

---

## Files to fix in the zip

| File | Bugs |
|------|------|
| `agent-skills/agents/dba-auditor/scripts/dewey_overnight_run.py` | 1, 2, 3, 5 |
| `agent-skills/agents/dba-auditor/scripts/dewey_nightly_cron.sh` | (peer review) |
| `agent-skills/agents/dba-auditor/scripts/sanity_live_repair_cycle_smoke.sh` | 6 |
| `agent-skills/agents/dba-auditor/tests/test_dewey_monitor_sparta_nightly.py` | (add tests for new behavior) |
| `memory/.agents/services.yaml` | (peer review) |
| `ARCHITECTURE.md` | (update with fixes) |
| `MANIFEST.json` | |
| `prompt_improvements.md` | (required) |

---

## Acceptance gates for this round

| Gate | Evidence |
|------|----------|
| `dewey once --wait-timeout-s 300` completes in <600s | Exit code 1 (not 124 timeout), dewey.log shows REPAIR_STEP lines |
| `dewey once` with only unfixable dims returns exit 10 | Short-circuits without calling repair-cycle |
| `start` command handles missing db_repair_session.py gracefully | Logs warning, continues without backup |
| All 16+ unit tests pass | pytest output |
| Worker wait doesn't hang when no workers launched | dewey.log shows worker_wait completed in <5s |

---

Do NOT return PASS/NEEDS_CHANGES/BLOCKED. Return ONE zip with ALL fixes.
