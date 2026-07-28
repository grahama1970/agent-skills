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
  --proof "focused test AND ./run.sh sanity-live.sh --allow-live with receipt read-back" \
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
  --proof "focused test AND ./run.sh sanity-live.sh --allow-live with receipt read-back" \
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
  --proof "screenshot plus focused UI test" \
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

echo -n "Check 11 - bootstrap context renders and is machine-readable: "
# project-watchdog forwards the whole issue body to the repair node, so these
# sections are the only project context a stateless cron agent receives (#1046).
"$SCRIPT_DIR/run.sh" bug "bootstrap probe" \
  --target skills/x --observed o --expected e --repro r \
  --proof "live run against 127.0.0.1:8018 read back from the written receipt" \
  --route backend_python_or_skill_runtime --agent agent-skill-maintainer \
  --context-file GOAL.md --context-file src/a.py \
  --required-skill best-practices-python \
  --depends-on grahama1970/agent-skills#1040 > "$TMPDIR/bootstrap.out"
grep -q '## Required repository context' "$TMPDIR/bootstrap.out"
grep -q -- '- `GOAL.md`' "$TMPDIR/bootstrap.out"
grep -q '## Required skills' "$TMPDIR/bootstrap.out"
grep -q '## Dependencies' "$TMPDIR/bootstrap.out"
grep -q 'blocked-by: grahama1970/agent-skills#1040' "$TMPDIR/bootstrap.out"
grep -q 'context_files: GOAL.md,src/a.py' "$TMPDIR/bootstrap.out"
grep -q 'required_skills: best-practices-python' "$TMPDIR/bootstrap.out"
grep -q 'depends_on: grahama1970/agent-skills#1040' "$TMPDIR/bootstrap.out"
echo "PASS"

echo -n "Check 12 - omitting bootstrap fields changes nothing: "
"$SCRIPT_DIR/run.sh" bug "no bootstrap probe" \
  --target skills/x --observed o --expected e --repro r \
  --proof "live run against 127.0.0.1:8018 read back from the written receipt" \
  --route backend_python_or_skill_runtime > "$TMPDIR/nobootstrap.out"
if grep -qE 'Required repository context|Required skills|## Dependencies|context_files:' "$TMPDIR/nobootstrap.out"; then
  echo "FAIL bootstrap sections rendered without the flags"
  exit 1
fi
grep -q 'type: bug' "$TMPDIR/nobootstrap.out"
echo "PASS"

# --- live-proof and closure-evidence gates ----------------------------------- #

echo -n "Check 13 - filing refuses a deterministic-only proof: "
OUT="$("$SCRIPT_DIR/run.sh" bug "p" --target src/x.py --observed o --expected e --repro r \
  --proof "pytest tests/test_x.py -q" --route backend_python_or_skill_runtime 2>&1 || true)"
grep -q "must include a LIVE end-to-end command" <<<"$OUT" || { echo "FAIL"; exit 1; }
echo "PASS"

echo -n "Check 14 - a pytest path containing 'e2e' does not count as live: "
OUT="$("$SCRIPT_DIR/run.sh" bug "p" --target src/x.py --observed o --expected e --repro r \
  --proof "pytest tests/test_e2e.py -q" --route backend_python_or_skill_runtime 2>&1 || true)"
grep -q "must include a LIVE end-to-end command" <<<"$OUT" || { echo "FAIL"; exit 1; }
echo "PASS"

echo -n "Check 15 - filing accepts a live proof: "
OUT="$("$SCRIPT_DIR/run.sh" bug "p" --target src/x.py --observed o --expected e --repro r \
  --proof "./run.sh sanity-live.sh --allow-live then read back receipt.json" \
  --route backend_python_or_skill_runtime 2>&1 || true)"
grep -q "^Labels" <<<"$OUT" || { echo "FAIL"; echo "$OUT" | tail -3; exit 1; }
echo "PASS"

echo -n "Check 16 - closure refuses failing unit, mocked e2e, and absent artifact: "
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

echo -n "Check 17 - closure accepts a passing unit + live e2e with a read-back artifact: "
cat > "$TMPDIR/r.json" <<JSON
{"schema":"agent_skills.ticket_closure_evidence.v1",
 "unit":{"command":"uv run pytest -q","exit_code":0},
 "e2e":{"command":"./run.sh sanity-live.sh --allow-live","exit_code":0,"mocked":false,"live":true,"artifact":"$TMPDIR/a.json"}}
JSON
OUT="$("$SCRIPT_DIR/run.sh" close 1 --proof "$TMPDIR/p.md" --results "$TMPDIR/r.json" --repo o/r --dry-run 2>&1 || true)"
grep -q "closure evidence accepted" <<<"$OUT" || { echo "FAIL"; echo "$OUT" | tail -3; exit 1; }
echo "PASS"

echo ""

echo -n "Check 18 - block --blocked-by validates references before mutating: "
printf 'blocked probe\n' > "$TMPDIR/reason.md"
# The watchdog polls these refs and fails closed, so an unreadable reference
# would stall the downstream ticket forever. Both rejections must happen before
# any label edit (#1042).
if "$SCRIPT_DIR/run.sh" block 1 --reason "$TMPDIR/reason.md" --blocked-by "not-a-ref" \
    --repo owner/repo >/dev/null 2>&1; then
  echo "FAIL malformed --blocked-by reference was accepted"
  exit 1
fi
if "$SCRIPT_DIR/run.sh" block 1 --reason "$TMPDIR/reason.md" \
    --blocked-by "grahama1970/agent-skills#999999" --repo owner/repo >/dev/null 2>&1; then
  echo "FAIL unreadable --blocked-by reference was accepted"
  exit 1
fi
echo "PASS"

# --- orientation + lanes ------------------------------------------------------ #

echo -n "Check 19 - agent-routable tickets carry the orientation block: "
OUT="$("$SCRIPT_DIR/run.sh" bug "p" --target skills/x --observed o --expected e --repro r \
  --proof "./run.sh sanity-live.sh --allow-live; read back receipt.json" \
  --route backend_python_or_skill_runtime 2>&1 || true)"
grep -q "Orientation for a stateless agent" <<<"$OUT" || { echo "FAIL"; exit 1; }
grep -q "skills/memory/run.sh recall" <<<"$OUT" || { echo "FAIL missing memory-first step"; exit 1; }
grep -q "skills/project-state/run.sh" <<<"$OUT" || { echo "FAIL missing project-state"; exit 1; }
echo "PASS"

echo -n "Check 20 - human-first tickets do not carry it: "
# Capture the status separately. This assertion is negative -- the orientation
# block must be ABSENT -- and a traceback contains no orientation block either,
# so without an exit check a crashing command satisfies it. That is exactly how
# a NameError in `question` shipped past a green sanity run.
if OUT="$("$SCRIPT_DIR/run.sh" question "p" --target skills/x --question q --answer-format prose \
  --source-scope src --proof "./run.sh sanity-live.sh --allow-live" \
  --route backend_python_or_skill_runtime 2>&1)"; then :; else
  echo "FAIL question exited nonzero:"; echo "$OUT" | tail -3; exit 1
fi
grep -q '^Labels' <<<"$OUT" || { echo "FAIL question produced no draft"; exit 1; }
grep -q "Orientation for a stateless agent" <<<"$OUT" && { echo "FAIL question got orientation"; exit 1; }
echo "PASS"

echo -n "Check 21 - every command the orientation names exists: "
for cmd in memory project-state treesitter github-search dogpile brave-search test; do
  [[ -f "$SCRIPT_DIR/../$cmd/run.sh" ]] || { echo "FAIL $cmd/run.sh missing"; exit 1; }
done
echo "PASS"

echo -n "Check 22 - lane is derived from route and overridable: "
FE="$("$SCRIPT_DIR/run.sh" bug "p" --target skills/x --observed o --expected e --repro r \
  --proof "./run.sh sanity-live.sh --allow-live" --route frontend_code 2>&1 | grep '^Labels' || true)"
OV="$("$SCRIPT_DIR/run.sh" bug "p" --target skills/x --observed o --expected e --repro r \
  --proof "./run.sh sanity-live.sh --allow-live" --route backend_python_or_skill_runtime --lane data 2>&1 | grep '^Labels' || true)"
BAD="$("$SCRIPT_DIR/run.sh" bug "p" --target skills/x --observed o --expected e --repro r \
  --proof "./run.sh sanity-live.sh --allow-live" --route backend_python_or_skill_runtime --lane nope 2>&1 || true)"
grep -q 'lane:fe' <<<"$FE" || { echo "FAIL frontend_code did not derive lane:fe"; exit 1; }
grep -q 'lane:data' <<<"$OV" || { echo "FAIL --lane override ignored"; exit 1; }
grep -q "unknown --lane" <<<"$BAD" || { echo "FAIL bad lane not refused"; exit 1; }
echo "PASS"

echo -n "Check 23 - only dispatchable tickets carry a lane: "
Q="$("$SCRIPT_DIR/run.sh" question "p" --target skills/x --question q --answer-format prose \
  --source-scope src --proof "$SCRIPT_DIR/sanity.sh" 2>&1 | grep '^Labels' || true)"
T="$("$SCRIPT_DIR/run.sh" triage "p" --target skills/x --clues c --missing-data m 2>&1 | grep '^Labels' || true)"
grep -q 'lane:' <<<"$Q" && { echo "FAIL question carries a lane it can never be scheduled by"; exit 1; }
grep -q 'lane:' <<<"$T" && { echo "FAIL triage carries a lane before its route is known"; exit 1; }
grep -q 'agent-work' <<<"$Q" && { echo "FAIL question is not agent-routable"; exit 1; }
echo "PASS"

echo -n "Check 24 - every ticket type builds a draft without crashing: "
# `question` and `triage` both raised NameError on main while sanity stayed
# green, because no check required any command to actually succeed. Every ticket
# type is exercised here, and each must exit zero and emit a Labels line.
PROOF="./run.sh sanity-live.sh --allow-live"
run_type() {
  local name="$1"; shift
  local out status=0
  # Declare first, then assign: `local out="$(cmd)"` reports local's status, not
  # the command's, and under `set -e` a failing substitution aborts the script
  # before the check can report which type broke.
  out="$("$SCRIPT_DIR/run.sh" "$name" "p" --target skills/x "$@" 2>&1)" || status=$?
  if [[ $status -ne 0 ]]; then
    echo "FAIL $name exited $status:"; echo "$out" | tail -3; exit 1
  fi
  grep -q '^Labels' <<<"$out" || { echo "FAIL $name emitted no draft"; exit 1; }
}
run_type bug          --observed o --expected e --repro r --proof "$PROOF"
run_type feature      --limitation l --capability c --workflow w --acceptance a --proof "$PROOF"
run_type optimization --friction f --improvement i --measurable-target t --proof "$PROOF"
run_type maintenance  --invariant i --cleanup c --scoped-files f --proof "$PROOF"
run_type question     --question q --answer-format prose --source-scope src --proof "$PROOF"
run_type triage       --clues c --missing-data m
echo "PASS"

echo ""
echo "Result: PASS"
