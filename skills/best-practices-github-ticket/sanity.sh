#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== [best-practices-github-ticket] Sanity Check ==="

echo -n "Check 1 - Required files: "
for path in \
    "$SCRIPT_DIR/SKILL.md" \
    "$SCRIPT_DIR/references/ticket_contract.yml" \
    "$SCRIPT_DIR/scripts/gh-ticket-tools.sh" \
    "$SCRIPT_DIR/templates/proof.md" \
    "$SCRIPT_DIR/templates/blocker.md" \
    "$SCRIPT_DIR/templates/progress.md" \
    "$SCRIPT_DIR/templates/review.md"; do
    if [[ ! -f "$path" ]]; then
        echo "FAIL: missing $path"
        exit 1
    fi
done
echo "PASS"

echo -n "Check 2 - Frontmatter and contract YAML: "
uv run --no-project --with pyyaml python - "$SCRIPT_DIR" <<'PY'
from pathlib import Path
import re
import sys
import yaml

skill_dir = Path(sys.argv[1])
text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
match = re.match(r"\A---\n(.*?)\n---(?:\n|$)", text, re.S)
if not match:
    raise SystemExit("missing strict YAML frontmatter")
frontmatter = yaml.safe_load(match.group(1))
required = ["name", "description", "triggers", "provides", "composes", "complies"]
missing = [field for field in required if field not in frontmatter]
if missing:
    raise SystemExit(f"missing frontmatter fields: {missing}")
if frontmatter["name"] != "best-practices-github-ticket":
    raise SystemExit("name does not match directory")
if "best-practices-skills" not in frontmatter["complies"]:
    raise SystemExit("missing best-practices-skills compliance")
contract = yaml.safe_load((skill_dir / "references" / "ticket_contract.yml").read_text(encoding="utf-8"))
for ticket_type in ["bug", "feature", "optimization", "maintenance", "question", "triage"]:
    if ticket_type not in contract["ticket_types"]:
        raise SystemExit(f"missing ticket type {ticket_type}")
for route in [
    "backend_python_or_skill_runtime",
    "design_or_ux",
    "frontend_code",
    "rust_or_binary",
    "ops_or_scheduler",
    "documentation_or_report",
    "security_or_compliance",
]:
    if route not in contract["routes"]:
        raise SystemExit(f"missing route {route}")
PY
echo "PASS"

echo -n "Check 3 - Required guidance sections: "
for section in "Issuer Contract" "Resolver Contract" "Verification Contract" "WebGPT And External Review" "Common Mistakes"; do
    if ! grep -q "## $section" "$SCRIPT_DIR/SKILL.md"; then
        echo "FAIL: missing section $section"
        exit 1
    fi
done
echo "PASS"

echo -n "Check 4 - best-practices-skills validator: "
python3 "$REPO_ROOT/skills/best-practices-skills/scripts/validate_skill.py" \
    "$SCRIPT_DIR" --json >/dev/null
echo "PASS"

echo -n "Check 5 - gh helper dry-run safety: "
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
printf 'Proof: deterministic command exited 0.\n' > "$tmpdir/proof.md"
"$SCRIPT_DIR/scripts/gh-ticket-tools.sh" close 123 --repo owner/repo --proof "$tmpdir/proof.md" --dry-run > "$tmpdir/close.out"
grep -q 'gh issue comment 123' "$tmpdir/close.out"
grep -q -- '--repo owner/repo' "$tmpdir/close.out"
grep -q 'gh issue close 123' "$tmpdir/close.out"
if "$SCRIPT_DIR/scripts/gh-ticket-tools.sh" close 123 --dry-run >/dev/null 2>&1; then
    echo "FAIL: close without proof unexpectedly passed"
    exit 1
fi
echo "PASS"

echo -n "Check 6 - common flag order and workflow commands: "
printf 'Blocked: missing decision.\n' > "$tmpdir/blocker.md"
printf 'Progress: reproduced failure.\n' > "$tmpdir/progress.md"
"$SCRIPT_DIR/scripts/gh-ticket-tools.sh" search --repo owner/repo --label skill-bug --dry-run --search 'sort:updated-asc' > "$tmpdir/search.out"
grep -q -- '--repo owner/repo' "$tmpdir/search.out"
grep -q -- '--label skill-bug' "$tmpdir/search.out"
"$SCRIPT_DIR/scripts/gh-ticket-tools.sh" ensure-labels --repo owner/repo --dry-run > "$tmpdir/labels.out"
grep -q -- 'gh label create type:feature' "$tmpdir/labels.out"
grep -q -- 'gh label create monitor-skill-health' "$tmpdir/labels.out"
grep -q -- 'gh label create agent-maintenance' "$tmpdir/labels.out"
grep -q -- 'gh label create agent:agent-skill-maintainer' "$tmpdir/labels.out"
if grep -q -- 'gh label create type --repo' "$tmpdir/labels.out"; then
    echo "FAIL: colon label was split incorrectly"
    exit 1
fi
"$SCRIPT_DIR/scripts/gh-ticket-tools.sh" next --dry-run --label skill-maintenance --repo owner/repo > "$tmpdir/next.out"
grep -q -- '-label:maintainer-active' "$tmpdir/next.out"
"$SCRIPT_DIR/scripts/gh-ticket-tools.sh" lease 123 --repo owner/repo --agent tester --dry-run > "$tmpdir/lease.out"
grep -q '"action":"lease"' "$tmpdir/lease.out"
"$SCRIPT_DIR/scripts/gh-ticket-tools.sh" block 123 --reason "$tmpdir/blocker.md" --release --repo owner/repo --dry-run > "$tmpdir/block.out"
grep -q -- '--remove-label maintainer-active' "$tmpdir/block.out"
"$SCRIPT_DIR/scripts/gh-ticket-tools.sh" release 123 --agent tester --reason "$tmpdir/blocker.md" --repo owner/repo --dry-run > "$tmpdir/release.out"
grep -q '"action":"release"' "$tmpdir/release.out"
"$SCRIPT_DIR/scripts/gh-ticket-tools.sh" close 123 --proof "$tmpdir/proof.md" --reason not-planned --repo owner/repo --dry-run > "$tmpdir/close-not-planned.out"
grep -q -- '--reason not\\ planned' "$tmpdir/close-not-planned.out"
"$SCRIPT_DIR/scripts/gh-ticket-tools.sh" close-duplicate 123 --duplicate-of 122 --proof "$tmpdir/proof.md" --repo owner/repo --dry-run > "$tmpdir/close-duplicate.out"
grep -q -- '--reason not\\ planned' "$tmpdir/close-duplicate.out"
grep -q '"action":"close-duplicate"' "$tmpdir/close-duplicate.out"
"$SCRIPT_DIR/scripts/gh-ticket-tools.sh" proof-template proof > "$tmpdir/template.out"
grep -q 'Verification command' "$tmpdir/template.out"
if "$SCRIPT_DIR/scripts/gh-ticket-tools.sh" search --repo owner/repo --bogus --dry-run >/dev/null 2>&1; then
    echo "FAIL: unknown arg unexpectedly passed"
    exit 1
fi
echo "PASS"

echo ""
echo "Result: PASS"
