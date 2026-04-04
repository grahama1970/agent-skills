#!/usr/bin/env bash
# sanity.sh — smoke test for mockup-lab
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
PASS=0; FAIL=0

check() {
  local desc="$1"; shift
  if "$@" >/dev/null 2>&1; then
    echo "  PASS: $desc"
    PASS=$((PASS + 1))
  else
    echo "  FAIL: $desc"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== mockup-lab sanity ==="

# 1. SKILL.md exists with required frontmatter
check "SKILL.md exists" test -f "$SKILL_DIR/SKILL.md"
check "SKILL.md has triggers" grep -q "^triggers:" "$SKILL_DIR/SKILL.md"
check "SKILL.md has provides" grep -q "^provides:" "$SKILL_DIR/SKILL.md"
check "SKILL.md has composes" grep -q "^composes:" "$SKILL_DIR/SKILL.md"

# 2. run.sh exists and is executable
check "run.sh exists" test -x "$SKILL_DIR/run.sh"
check "run.sh has unset VIRTUAL_ENV" grep -q "unset VIRTUAL_ENV" "$SKILL_DIR/run.sh"

# 3. stitch_cli.mjs and spec-template.md exist
check "stitch_cli.mjs exists" test -f "$SKILL_DIR/stitch_cli.mjs"
check "spec-template.md exists" test -f "$SKILL_DIR/docs/spec-template.md"

# 4. STITCH_API_KEY is available
ENV_FILE="$(git -C "$SKILL_DIR" rev-parse --show-toplevel 2>/dev/null)/.env"
check "STITCH_API_KEY in .env" grep -q "STITCH_API_KEY" "$ENV_FILE"

# 5. Stitch SDK is importable
check "@google/stitch-sdk importable" node --input-type=module -e "import '@google/stitch-sdk'"

# 6. Can list projects (real API call)
check "stitch list projects" bash -c "cd '$SKILL_DIR' && ./run.sh list 2>&1 | grep -q screens"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
