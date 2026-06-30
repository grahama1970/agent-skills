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
  --proof "focused test exits 0" \
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
  --proof "focused monitor proof" \
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

echo -n "Check 8 - lifecycle helper dry-run wrapper: "
"$SCRIPT_DIR/run.sh" lookup --next --label skill-bug --repo owner/repo --dry-run > "$TMPDIR/lookup.out"
grep -q 'gh issue list' "$TMPDIR/lookup.out"
grep -q -- '--label skill-bug' "$TMPDIR/lookup.out"
printf 'Proof command exited 0.\n' > "$TMPDIR/proof.md"
"$SCRIPT_DIR/run.sh" close 123 --proof "$TMPDIR/proof.md" --repo owner/repo --dry-run > "$TMPDIR/close.out"
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

echo ""
echo "Result: PASS"
