#!/usr/bin/env bash
set -euo pipefail
unset VIRTUAL_ENV || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TMPDIR="$(mktemp -d)"
export UV_PROJECT_ENVIRONMENT="$TMPDIR/uv-env"
trap 'rm -rf "$TMPDIR"' EXIT

echo "=== [ticket] Sanity Check ==="

echo -n "Check 1 - Required files: "
for path in \
  "$SCRIPT_DIR/SKILL.md" \
  "$SCRIPT_DIR/run.sh" \
  "$SCRIPT_DIR/pyproject.toml" \
  "$SCRIPT_DIR/scripts/ticket_cli.py" \
  "$SCRIPT_DIR/references/ticket_body_templates.yml"; do
  [[ -f "$path" ]] || { echo "FAIL missing $path"; exit 1; }
done
echo "PASS"

echo -n "Check 2 - Python compile/import: "
uv run --project "$SCRIPT_DIR" python -m py_compile "$SCRIPT_DIR/scripts/ticket_cli.py"
echo "PASS"

echo -n "Check 3 - best-practices-skills validator: "
python3 "$REPO_ROOT/skills/best-practices-skills/scripts/validate_skill.py" \
  "$SCRIPT_DIR" --json >/dev/null
echo "PASS"

echo -n "Check 4 - bug dry-run body contract: "
"$SCRIPT_DIR/run.sh" bug "Bug report" \
  --target skills/surf \
  --observed "Observed failure" \
  --expected "Expected behavior" \
  --repro "Run the focused repro" \
  --proof "focused test exits 0 AND ./run.sh sanity-live.sh --allow-live with receipt read-back" \
  --route backend_python_or_skill_runtime \
  --agent coder \
  --json > "$TMPDIR/bug.json"
grep -q '"type": "bug"' "$TMPDIR/bug.json"
grep -q 'Required proof' "$TMPDIR/bug.json"
grep -q 'Target paths' "$TMPDIR/bug.json"
grep -q 'Maintainer route' "$TMPDIR/bug.json"
grep -q 'skill-bug' "$TMPDIR/bug.json"
echo "PASS"

echo -n "Check 5 - maintenance labels are preserved: "
"$SCRIPT_DIR/run.sh" maintenance "Maintenance report" \
  --target skills/ticket \
  --invariant "Invariant stays true" \
  --cleanup "Concrete cleanup target" \
  --scoped-files "skills/ticket/SKILL.md" \
  --proof "focused monitor proof AND ./run.sh e2e --allow-live reading back latest_results.jsonl" \
  --route backend_python_or_skill_runtime \
  --agent agent-skill-maintainer \
  --label monitor-skill-health \
  --json > "$TMPDIR/maintenance.json"
grep -q '"type": "maintenance"' "$TMPDIR/maintenance.json"
grep -q 'skill-maintenance' "$TMPDIR/maintenance.json"
grep -q 'monitor-skill-health' "$TMPDIR/maintenance.json"
grep -q 'Target paths' "$TMPDIR/maintenance.json"
grep -q 'Maintainer route' "$TMPDIR/maintenance.json"
echo "PASS"

echo -n "Check 6 - missing proof fails closed: "
if "$SCRIPT_DIR/run.sh" feature "Bad feature" \
  --target skills/ticket \
  --limitation "Missing proof" \
  --capability "Should fail" \
  --workflow "No workflow" \
  --acceptance "No acceptance" >/dev/null 2>&1; then
  echo "FAIL feature without proof passed"
  exit 1
fi
echo "PASS"

echo -n "Check 7 - fleet dry-run splits items: "
cat > "$TMPDIR/design.md" <<'EOF'
- Add compact sidebar
- Replace vague status card with proof table
EOF
"$SCRIPT_DIR/run.sh" fleet "$TMPDIR/design.md" \
  --target skills/hum/ui \
  --route design_or_ux \
  --agent designer \
  --proof "focused UI test AND live browser run with a fresh screenshot artifact" \
  --json > "$TMPDIR/fleet.json"
grep -q 'Add compact sidebar' "$TMPDIR/fleet.json"
grep -q 'Replace vague status card' "$TMPDIR/fleet.json"
echo "PASS"

echo '{"ok":true}' > "$TMPDIR/live-artifact.json"
cat > "$TMPDIR/closure.json" <<JSON
{"schema":"agent_skills.ticket_closure_evidence.v1",
 "unit":{"command":"uv run pytest -q","exit_code":0},
 "e2e":{"command":"./run.sh sanity-live.sh --allow-live","exit_code":0,"mocked":false,"live":true,"artifact":"$TMPDIR/live-artifact.json"}}
JSON
echo -n "Check 8 - lifecycle helper dry-run wrapper: "
"$SCRIPT_DIR/run.sh" lookup --next --label skill-bug --repo owner/repo --dry-run > "$TMPDIR/lookup.out"
grep -q 'gh issue list' "$TMPDIR/lookup.out"
grep -q -- '--label skill-bug' "$TMPDIR/lookup.out"
"$SCRIPT_DIR/run.sh" ensure-labels --repo owner/repo --dry-run > "$TMPDIR/ensure-labels.out"
grep -q 'monitor-skill-health' "$TMPDIR/ensure-labels.out"
grep -q 'agent-maintenance' "$TMPDIR/ensure-labels.out"
grep -q 'agent:agent-skill-maintainer' "$TMPDIR/ensure-labels.out"
printf 'Proof command exited 0.\n' > "$TMPDIR/proof.md"
"$SCRIPT_DIR/run.sh" close 123 --proof "$TMPDIR/proof.md" --results "$TMPDIR/closure.json" --repo owner/repo --dry-run > "$TMPDIR/close.out"
grep -q 'gh issue close 123' "$TMPDIR/close.out"
echo "PASS"

echo -n "Check 9 - CI commands are gated: "
"$SCRIPT_DIR/run.sh" ci dispatch verify.yml --repo owner/repo --ref branch --field issue=123 --dry-run > "$TMPDIR/dispatch.out"
grep -q 'gh workflow run verify.yml' "$TMPDIR/dispatch.out"
if "$SCRIPT_DIR/run.sh" ci rerun 12345 --repo owner/repo >/dev/null 2>&1; then
  echo "FAIL ci rerun without --yes passed"
  exit 1
fi
echo "PASS"

echo -n "Check 10 - verify writes proof and fails on command failure: "
"$SCRIPT_DIR/run.sh" verify 123 --cmd "printf ok" --output "$TMPDIR/issue-proof.md" > "$TMPDIR/verify.out"
grep -q 'mocked: no' "$TMPDIR/issue-proof.md"
grep -q 'Exit code: 0' "$TMPDIR/issue-proof.md"
if "$SCRIPT_DIR/run.sh" verify 123 --cmd "exit 7" --output "$TMPDIR/bad-proof.md" >/dev/null 2>&1; then
  echo "FAIL verify did not fail on nonzero command"
  exit 1
fi
grep -q 'Exit code: 7' "$TMPDIR/bad-proof.md"
echo "PASS"

# --- agent routing ----------------------------------------------------------- #

echo -n "Check 11 - agent-work is stamped only on agent-routable tickets: "
ROUTABLE="$("$SCRIPT_DIR/run.sh" bug "p" --target src/x.py --observed o --expected e --repro r \
  --proof "./run.sh sanity-live.sh --allow-live; read back receipt.json" --route backend_python_or_skill_runtime 2>&1 | grep '^Labels' || true)"
UNROUTED="$("$SCRIPT_DIR/run.sh" bug "p" --target src/x.py --observed o --expected e --repro r \
  --proof "./run.sh sanity-live.sh --allow-live; read back receipt.json" 2>&1 | grep '^Labels' || true)"
QUESTION="$("$SCRIPT_DIR/run.sh" question "p" --target src/x.py --question q \
  --answer-format prose --source-scope src --proof "./run.sh sanity-live.sh --allow-live" \
  --route backend_python_or_skill_runtime 2>&1 | grep '^Labels' || true)"
grep -q 'agent-work' <<<"$ROUTABLE" || { echo "FAIL routable ticket missing agent-work: $ROUTABLE"; exit 1; }
grep -q 'agent-work' <<<"$UNROUTED" && { echo "FAIL unknown-route ticket got agent-work: $UNROUTED"; exit 1; }
grep -q 'agent-work' <<<"$QUESTION" && { echo "FAIL question ticket got agent-work: $QUESTION"; exit 1; }
echo "PASS"

# --- live-proof and closure-evidence gates ----------------------------------- #

echo -n "Check 16 - filing refuses a deterministic-only proof: "
OUT="$("$SCRIPT_DIR/run.sh" bug "p" --target src/x.py --observed o --expected e --repro r \
  --proof "pytest tests/test_x.py -q" --route backend_python_or_skill_runtime 2>&1 || true)"
grep -q "must include a LIVE end-to-end command" <<<"$OUT" || { echo "FAIL"; exit 1; }
echo "PASS"

echo -n "Check 17 - a pytest path containing 'e2e' does not count as live: "
OUT="$("$SCRIPT_DIR/run.sh" bug "p" --target src/x.py --observed o --expected e --repro r \
  --proof "pytest tests/test_e2e.py -q" --route backend_python_or_skill_runtime 2>&1 || true)"
grep -q "must include a LIVE end-to-end command" <<<"$OUT" || { echo "FAIL"; exit 1; }
echo "PASS"

echo -n "Check 18 - filing accepts a live proof: "
OUT="$("$SCRIPT_DIR/run.sh" bug "p" --target src/x.py --observed o --expected e --repro r \
  --proof "./run.sh sanity-live.sh --allow-live then read back receipt.json" \
  --route backend_python_or_skill_runtime 2>&1 || true)"
grep -q "^Labels" <<<"$OUT" || { echo "FAIL"; echo "$OUT" | tail -3; exit 1; }
echo "PASS"

echo -n "Check 19 - closure refuses failing unit, mocked e2e, and absent artifact: "
echo "proof" > "$TMPDIR/p.md"; echo '{"ok":true}' > "$TMPDIR/a.json"
close_refuses() {
  echo "$1" > "$TMPDIR/r.json"
  OUT="$("$SCRIPT_DIR/run.sh" close 1 --proof "$TMPDIR/p.md" --results "$TMPDIR/r.json" \
    --repo o/r --dry-run 2>&1 || true)"
  grep -q "closure refused" <<<"$OUT"
}
close_refuses '{"schema":"agent_skills.ticket_closure_evidence.v1","unit":{"command":"pytest -q","exit_code":1},"e2e":{"command":"./run.sh sanity-live.sh","exit_code":0,"mocked":false,"live":true,"artifact":"'"$TMPDIR"'/a.json"}}' || { echo "FAIL failing-unit"; exit 1; }
close_refuses '{"schema":"agent_skills.ticket_closure_evidence.v1","unit":{"command":"pytest -q","exit_code":0},"e2e":{"command":"./run.sh sanity-live.sh","exit_code":0,"mocked":true,"live":true,"artifact":"'"$TMPDIR"'/a.json"}}' || { echo "FAIL mocked-e2e"; exit 1; }
close_refuses '{"schema":"agent_skills.ticket_closure_evidence.v1","unit":{"command":"pytest -q","exit_code":0},"e2e":{"command":"./run.sh sanity-live.sh","exit_code":0,"mocked":false,"live":true,"artifact":"/tmp/nope-does-not-exist.json"}}' || { echo "FAIL absent-artifact"; exit 1; }
close_refuses '{"schema":"agent_skills.ticket_closure_evidence.v1","unit":{"command":"pytest -q","exit_code":0},"e2e":{"command":"pytest tests/test_e2e.py -q","exit_code":0,"mocked":false,"live":true,"artifact":"'"$TMPDIR"'/a.json"}}' || { echo "FAIL pytest-as-e2e"; exit 1; }
echo "PASS"

echo -n "Check 20 - closure accepts a passing unit + live e2e with a read-back artifact: "
cat > "$TMPDIR/r.json" <<JSON
{"schema":"agent_skills.ticket_closure_evidence.v1",
 "unit":{"command":"uv run pytest -q","exit_code":0},
 "e2e":{"command":"./run.sh sanity-live.sh --allow-live","exit_code":0,"mocked":false,"live":true,"artifact":"$TMPDIR/a.json"}}
JSON
OUT="$("$SCRIPT_DIR/run.sh" close 1 --proof "$TMPDIR/p.md" --results "$TMPDIR/r.json" --repo o/r --dry-run 2>&1 || true)"
grep -q "closure evidence accepted" <<<"$OUT" || { echo "FAIL"; echo "$OUT" | tail -3; exit 1; }
echo "PASS"

echo ""
echo "Result: PASS"
