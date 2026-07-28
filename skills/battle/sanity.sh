#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STORAGE_ROOT="${BATTLE_STORAGE_ROOT:-/mnt/storage12tb/skills/battle}"
TMP_ROOT="${TMPDIR:-/tmp}/battle-sanity"
OUT_DIR="$TMP_ROOT/battle-001"

export BATTLE_STORAGE_ROOT="$STORAGE_ROOT"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-$STORAGE_ROOT/.venv}"
export PYTHONPATH="$SCRIPT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

mkdir -p "$STORAGE_ROOT" "$TMP_ROOT"
rm -rf "$OUT_DIR"

echo "=== Battle Skill Sanity ==="
echo "storage_root=$STORAGE_ROOT"
echo "uv_environment=$UV_PROJECT_ENVIRONMENT"

echo "1. Checking root layout"
test -f "$SCRIPT_DIR/SKILL.md"
test -x "$SCRIPT_DIR/run.sh"
test -f "$SCRIPT_DIR/pyproject.toml"
test -d "$SCRIPT_DIR/src/battle_skill"
if find "$SCRIPT_DIR" -maxdepth 1 -type f -name '*.py' | grep -q .; then
  echo "Root-level Python files are not allowed; implementation belongs in src/battle_skill." >&2
  find "$SCRIPT_DIR" -maxdepth 1 -type f -name '*.py' >&2
  exit 1
fi

echo "2. Checking generated directories are absent or symlinked"
for generated in .venv __pycache__ artifacts battles worktrees node_modules; do
  path="$SCRIPT_DIR/$generated"
  if [[ -e "$path" && ! -L "$path" ]]; then
    echo "Generated directory must not live in skill root: $path" >&2
    exit 1
  fi
done

echo "3. Compiling and importing package"
uv run --project "$SCRIPT_DIR" python -m compileall -q "$SCRIPT_DIR/src/battle_skill"
uv run --project "$SCRIPT_DIR" python - <<'PY'
import battle_skill
from battle_skill.cli import app
from battle_skill.config import SKILL_DIR, ARTIFACTS_DIR

assert app is not None
assert SKILL_DIR.name == "battle", SKILL_DIR
assert str(ARTIFACTS_DIR).startswith("/mnt/storage12tb/skills/battle"), ARTIFACTS_DIR
print("BATTLE_IMPORT_PASS")
PY

echo "4. Checking CLI help and fail-closed missing fixture"
"$SCRIPT_DIR/run.sh" --help >/dev/null
if "$SCRIPT_DIR/run.sh" battle-fixture does-not-exist --out "$TMP_ROOT/missing" >/tmp/battle-sanity-missing.out 2>/tmp/battle-sanity-missing.err; then
  echo "Missing fixture unexpectedly succeeded" >&2
  exit 1
fi

echo "5. Running positive-control fixture"
"$SCRIPT_DIR/run.sh" battle-fixture battle-001 --out "$OUT_DIR" >/tmp/battle-sanity-fixture.out

echo "6. Asserting receipt artifacts and schemas"
uv run --project "$SCRIPT_DIR" python - <<PY
import json
from pathlib import Path

root = Path("$OUT_DIR")
required = [
    "battle-plan.json",
    "red-receipt.json",
    "blue-receipt.json",
    "judge/judge-receipt.json",
    "scoreboard.json",
    "monitor-index.json",
    "run-receipt.json",
]
missing = [path for path in required if not (root / path).is_file()]
assert not missing, missing

scoreboard = json.loads((root / "scoreboard.json").read_text())
judge = json.loads((root / "judge" / "judge-receipt.json").read_text())
run = json.loads((root / "run-receipt.json").read_text())

assert scoreboard["schema"] == "battle.scoreboard.v1", scoreboard
assert scoreboard["status"] == "PASS", scoreboard
assert scoreboard["verdict"] == "BLUE_SUCCESS", scoreboard
assert judge["schema"] == "battle.judge_receipt.v1", judge
assert judge["exploit_confirmed_before_patch"] is True, judge
assert judge["exploit_blocked_after_patch"] is True, judge
assert judge["regression_tests_pass"] is True, judge
assert run["execution"]["live"] == "local_deterministic_fixture", run
assert run["execution"]["agentic"] is False, run
print("BATTLE_SANITY_PASS")
PY

echo "7. Validating stable normalized UX JSON contracts"
for fixture in \
  "$SCRIPT_DIR/local/battle-004-parent-spawn.normalized.json" \
  "$SCRIPT_DIR/local/battle-004-sparse.normalized.json"; do
  test -f "$fixture"
  uv run --project "$SCRIPT_DIR" python -m battle_skill.cli validate-ux-contract "$fixture" >/tmp/battle-sanity-ux-contract.out
  cat /tmp/battle-sanity-ux-contract.out
done

if [[ -n "${BATTLE_UX_CONTRACT_FIXTURE:-}" ]]; then
  echo "8. Validating caller-provided normalized UX JSON contract"
  uv run --project "$SCRIPT_DIR" python -m battle_skill.cli validate-ux-contract "$BATTLE_UX_CONTRACT_FIXTURE" >/tmp/battle-sanity-ux-contract.out
  cat /tmp/battle-sanity-ux-contract.out
else
  echo "8. No caller-provided normalized UX JSON contract; set BATTLE_UX_CONTRACT_FIXTURE=/path/to/fixture.json to validate an extra fixture"
fi

echo "9. Checking normalized UX handoff summary matches local artifacts"
uv run --project "$SCRIPT_DIR" python -m battle_skill.cli validate-ux-handoff-summary "$SCRIPT_DIR/local/battle-004-ux-json-contract-summary.json" >/tmp/battle-sanity-ux-handoff-summary.out
cat /tmp/battle-sanity-ux-handoff-summary.out
echo "BATTLE_UX_HANDOFF_SUMMARY_PASS"

echo "10. Checking UX data contract index points at authoritative backend JSON"
uv run --project "$SCRIPT_DIR" python -m battle_skill.cli validate-ux-data-contract-index "$SCRIPT_DIR/local/battle-004-ux-data-contract-index.json" >/tmp/battle-sanity-ux-data-contract-index.out
cat /tmp/battle-sanity-ux-data-contract-index.out
echo "BATTLE_UX_DATA_CONTRACT_INDEX_PASS"

if [[ "${BATTLE_PROVE_SPECTATOR:-}" == "1" ]]; then
  echo "11. Running full spectator local proof gate"
  "$SCRIPT_DIR/scripts/prove-spectator-local.sh"
else
  echo "11. Skipping spectator live proof (set BATTLE_PROVE_SPECTATOR=1 to enable)"
fi

echo "12. Running deterministic backend eval (informational health signal)"
# Non-fatal: surfaces backend-contract + committed-fixture health as a legible
# receipt. Known pre-existing fixture defects must not block the sanity gate;
# the dedicated `./run.sh backend-eval` command owns the pass/fail gate.
if uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/backend_eval.py" \
    --out-dir "$TMP_ROOT/backend-eval" >/tmp/battle-sanity-backend-eval.out 2>&1; then
  echo "BATTLE_BACKEND_EVAL_ALL_PASS"
else
  echo "BATTLE_BACKEND_EVAL_HAS_FAILURES (informational; see receipt)"
fi
tail -20 /tmp/battle-sanity-backend-eval.out || true

echo "Result: PASS"
