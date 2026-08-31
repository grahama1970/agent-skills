#!/usr/bin/env bash
# Behavioral sanity gate for the /terraform skill.
# Positive control: scaffold + organize + check pass on a fresh root.
# Negative control: organize flags a bad layout; scaffold refuses non-empty root.
# Safety boundary: deploy without --yes never applies (APPLY_NOT_CONFIRMED).
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="$HOME/.local/bin:$PATH"
WORK="$(mktemp -d /tmp/terraform-skill-sanity.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT
fail() { echo "SANITY FAIL: $1" >&2; exit 1; }

# 1. doctor emits typed envelope
"$SKILL_DIR/run.sh" doctor | grep -q '"schema": "terraform_skill.outcome.v1"' || fail "doctor envelope"

# 2. positive: scaffold a fresh root, files exist on disk
"$SKILL_DIR/run.sh" scaffold "$WORK/proj" >/dev/null
for f in main.tf variables.tf outputs.tf versions.tf providers.tf .gitignore envs/dev.tfvars.example README.md; do
  [ -f "$WORK/proj/$f" ] || fail "scaffold missing $f"
done
[ -d "$WORK/proj/modules" ] || fail "scaffold missing modules/"

# 3. positive: organize passes on the scaffolded root
"$SKILL_DIR/run.sh" organize "$WORK/proj" | grep -q '"status": "PASS"' || fail "organize on scaffold"

# 4. negative: scaffold refuses a root that already has .tf files
if "$SKILL_DIR/run.sh" scaffold "$WORK/proj" >"$WORK/refuse.json" 2>/dev/null; then
  fail "scaffold should refuse non-empty root"
fi
grep -q 'target_not_empty' "$WORK/refuse.json" || fail "scaffold refusal code"

# 5. negative: organize flags violations on a messy root
mkdir -p "$WORK/messy"
echo 'resource "null_resource" "x" {}' > "$WORK/messy/everything.tf"
touch "$WORK/messy/terraform.tfstate" "$WORK/messy/prod.tfvars"
if "$SKILL_DIR/run.sh" organize "$WORK/messy" >"$WORK/messy.json" 2>/dev/null; then
  fail "organize should fail on messy root"
fi
grep -q 'layout_violations' "$WORK/messy.json" || fail "organize failure code"
grep -q 'no-state-in-root-vcs' "$WORK/messy.json" || fail "state-file rule"

# 6. safety boundary: deploy without --yes must NOT apply (needs terraform binary)
if command -v terraform >/dev/null 2>&1; then
  cp "$WORK/proj/envs/dev.tfvars.example" "$WORK/proj/envs/dev.tfvars"
  if "$SKILL_DIR/run.sh" deploy "$WORK/proj" --var-file "$WORK/proj/envs/dev.tfvars" >"$WORK/deploy.json" 2>/dev/null; then
    fail "deploy without --yes must exit non-zero"
  fi
  grep -q 'apply_not_confirmed' "$WORK/deploy.json" || fail "deploy gate code"
  [ ! -f "$WORK/proj/terraform.tfstate" ] || fail "deploy without --yes wrote state"
else
  "$SKILL_DIR/run.sh" doctor >"$WORK/doc.json" 2>/dev/null || true
  grep -q 'terraform_missing' "$WORK/doc.json" || fail "doctor should report terraform_missing"
fi

# 7. interview question artifact (no UI launch)
"$SKILL_DIR/run.sh" interview --out "$WORK/q.json" --no-launch >/dev/null
python3 -c "import json,sys; d=json.load(open('$WORK/q.json')); sys.exit(0 if len(d['questions'])>=5 else 1)" || fail "interview questions"

echo "SANITY PASS"
