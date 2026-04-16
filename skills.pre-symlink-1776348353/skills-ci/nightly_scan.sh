#!/usr/bin/env bash
# Nightly quality pipeline: scan → autofix → code-runner fixes → git-sync.
# Registered with scheduler as "skills-ci-nightly" at 01:00.
#
# Flow:
#   1. Safety commit (revert point)               ~30s
#   2. Tier 1: skills-ci autofix                  ~120s (130+ skills)
#   3. Full scan to find remaining violations      ~120s
#   4. [SKIPPED — monitor-codebase runs at 03:00]
#   5. Tier 2: generate fix plan → /orchestrate   ~3600s (worst case)
#   6. Git sync to agent-skills                    ~30s
#   7. Nightly report + Discord                    ~15s
#
# Estimated total: ~3925s. Scheduler timeout: 4800s (20% buffer).
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_ROOT="$(dirname "$SCRIPT_DIR")"
COMMON="$SKILLS_ROOT/common"
BROADCAST="$SKILLS_ROOT/skills-broadcast/run.sh"
MONITOR_CODEBASE="$SKILLS_ROOT/monitor-codebase/run.sh"
ORCHESTRATE="$SKILLS_ROOT/orchestrate/run.sh"
REPO_ROOT="$(cd "$SKILLS_ROOT/../.." && pwd)"
DATE=$(date +%Y-%m-%d)

COMMON="$SKILLS_ROOT/common"
NIGHTLY_START=$(date +%s)

cd "$SCRIPT_DIR"

# Phase 0: Cache corruption audit (prevent cascading damage)
echo "=== Phase 0: Cache Audit ==="
cache_result=$(uv run python cache_audit.py scan --json 2>/dev/null) || true
cache_corrupted=$(echo "$cache_result" | python3 -c "import json,sys; print(json.load(sys.stdin).get('corrupted_dirs',0))" 2>/dev/null || echo 0)
if [[ "$cache_corrupted" -gt 0 ]]; then
    echo "[CRITICAL] $cache_corrupted corrupted cache directories detected!"
    echo "Running auto-repair..."
    uv run python cache_audit.py fix 2>&1 | tail -10
    echo "Cache repaired. Continuing with nightly scan."
fi

# Phase 1: Safety commit (revert point)
echo "=== Phase 1: Safety Commit ==="
cd "$REPO_ROOT"
if git diff --quiet && git diff --cached --quiet; then
    echo "[SKIP] Working tree clean, no safety commit needed"
else
    git add -A
    # --no-verify: safety snapshot is infrastructure, not a code change.
    # Pre-commit hooks (biome, tsc) fail on existing warnings unrelated to nightly.
    git commit --no-verify -m "nightly: safety snapshot before skills-ci-nightly ($DATE)" || true
fi
cd "$SCRIPT_DIR"

# Phase 2: Tier 1 autofix (safe mechanical fixes)
echo ""
echo "=== Phase 2: Tier 1 Autofix ==="
autofix_output=$(uv run python skills_ci.py --mode autofix 2>&1) || true
echo "$autofix_output" | tail -5

# Phase 3: Full scan
echo ""
echo "=== Phase 3: Skills CI Scan ==="
scan_output=$(uv run python skills_ci.py --mode scan --best-practices best-practices-python,best-practices-skills 2>&1) || true
echo "$scan_output" | tail -5

errors=$(echo "$scan_output" | grep -oP '\d+ errors' | grep -oP '\d+' || echo "0")
warnings=$(echo "$scan_output" | grep -oP '\d+ warnings' | grep -oP '\d+' || echo "0")

# Phase 4: Monitor-codebase — SKIPPED (runs as separate scheduler job at 03:00)
echo ""
echo "=== Phase 4: Monitor Codebase ==="
echo "[SKIP] monitor-codebase runs independently at 03:00 via scheduler"

# Phase 5: Tier 2 — generate fix plan and run via /orchestrate
echo ""
echo "=== Phase 5: Tier 2 Fix Plan ==="
FIX_PLAN="$SCRIPT_DIR/0N_FIX_${DATE}.yaml"
uv run python generate_fix_plan.py --output "$FIX_PLAN" 2>&1 || true

if [[ -f "$FIX_PLAN" ]] && [[ -s "$FIX_PLAN" ]]; then
    task_count=$(grep -c "^- id:" "$FIX_PLAN" || echo "0")
    echo "Generated $task_count fix tasks"

    if [[ "$task_count" -gt 0 ]] && [[ -x "$ORCHESTRATE" ]]; then
        echo "Running /orchestrate..."
        # Budget: 3600s for orchestrate (measured: ~60s per code-runner task × up to 50 tasks)
        timeout 3600 "$ORCHESTRATE" run "$FIX_PLAN" 2>&1 | tail -20 || echo "[WARN] orchestrate exited non-zero"

        # Commit any changes from code-runner fixes
        cd "$REPO_ROOT"
        if ! git diff --quiet || ! git diff --cached --quiet; then
            git add -A
            git commit -m "nightly: skills-ci Tier 2 fixes ($DATE) — $task_count tasks" || true
        fi
        cd "$SCRIPT_DIR"
    fi

    # Re-scan to get updated counts
    rescan=$(uv run python skills_ci.py --mode scan 2>&1) || true
    errors=$(echo "$rescan" | grep -oP '\d+ errors' | grep -oP '\d+' || echo "0")
    warnings=$(echo "$rescan" | grep -oP '\d+ warnings' | grep -oP '\d+' || echo "0")
else
    echo "[SKIP] No Tier 2 violations to fix"
fi

# Phase 5.5: Create PR if on a nightly branch with fix commits
echo ""
echo "=== Phase 5.5: PR Creation ==="
current_branch=$(git -C "$REPO_ROOT" branch --show-current || true)
if [[ "$current_branch" != "main" ]] && git -C "$REPO_ROOT" log main.."$current_branch" --oneline 2>/dev/null | grep -q .; then
    echo "Nightly branch has commits — creating PR..."
    MONITOR_CODEBASE_SCRIPT="$SKILLS_ROOT/monitor-codebase/run.sh"
    if [[ -x "$MONITOR_CODEBASE_SCRIPT" ]]; then
        "$MONITOR_CODEBASE_SCRIPT" create-pr --title "nightly: skills-ci + monitor-codebase fixes ($DATE)" 2>&1 | tail -5 || echo "[WARN] PR creation failed"
    fi
else
    echo "[SKIP] On main or no new commits — no PR needed"
fi

# Phase 6: Git sync to agent-skills
echo ""
echo "=== Phase 6: Git Sync ==="
if [[ -x "$BROADCAST" ]]; then
    "$BROADCAST" git-sync 2>&1 | tail -5
else
    echo "[SKIP] skills-broadcast not found"
fi

# Phase 7: Generate nightly report and store to /memory
echo ""
echo "=== Phase 7: Nightly Report ==="
REPORT_MD="$SCRIPT_DIR/nightly-report-${DATE}.md"
REPORT_JSON_OUT="$SCRIPT_DIR/nightly-report-${DATE}.json"
uv run python nightly_report.py --output "$REPORT_MD" --json "$REPORT_JSON_OUT" 2>&1 | tail -10 || echo "[WARN] nightly report generation failed"

# Record execution duration to /memory
NIGHTLY_END=$(date +%s)
NIGHTLY_DURATION=$((NIGHTLY_END - NIGHTLY_START))
python3 "$COMMON/estimate_timeout.py" record \
  --skill skills-ci-nightly \
  --duration "$NIGHTLY_DURATION" \
  --units 1 \
  --outcome success \
  --trigger scheduler \
  --cmd "nightly_scan.sh" \
  --composed skills-ci monitor-codebase orchestrate skills-broadcast \
  2>/dev/null || true

# Phase 8: Discord notification
echo ""
echo "=== Phase 8: Notify ==="
if [[ "$errors" -gt 0 ]]; then
    uv run --project "$SCRIPT_DIR" python -c "
import sys; sys.path.insert(0, '$COMMON')
from discord_notify import notify
notify('skills-ci', 'critical', '$errors errors, $warnings warnings across skill estate',
       title='Skills CI Nightly: ERRORS', event_type='health',
       data={'errors': $errors, 'warnings': $warnings}, priority='high')
"
    echo "[skills-ci-nightly] ALERT: $errors errors, $warnings warnings"
    # Exit 0 — the nightly RAN successfully, it just found errors.
    # Exit 1 would mark the scheduler job as "failed" which is misleading.
elif [[ "$warnings" -gt 0 ]]; then
    uv run --project "$SCRIPT_DIR" python -c "
import sys; sys.path.insert(0, '$COMMON')
from discord_notify import notify
notify('skills-ci', 'ok', '0 errors, $warnings warnings — Tier 1+2 applied',
       title='Skills CI Nightly: CLEAN', event_type='health',
       data={'errors': 0, 'warnings': $warnings})
"
    echo "[skills-ci-nightly] OK: 0 errors, $warnings warnings"
else
    echo "[skills-ci-nightly] OK: fully clean"
fi
