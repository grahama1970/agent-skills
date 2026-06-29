#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
AGENT_DIR="$REPO_ROOT/agents/readme-maintainer"

echo "=== best-practices-readme sanity ==="

check() {
  local label="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    echo "PASS: $label"
  else
    echo "FAIL: $label"
    exit 1
  fi
}

check "SKILL.md exists" test -f "$SCRIPT_DIR/SKILL.md"
check "README.md exists" test -f "$SCRIPT_DIR/README.md"
check "readme template exists" test -f "$SCRIPT_DIR/references/readme-template.md"
check "gallery destination reference exists" test -f "$SCRIPT_DIR/references/gallery-destination.md"
check "agent AGENTS.md exists" test -f "$AGENT_DIR/AGENTS.md"
check "agent persona.yaml exists" test -f "$AGENT_DIR/persona.yaml"
check "no TODO placeholders in skill" bash -c "! grep -R --exclude sanity.sh \"TODO:\" '$SCRIPT_DIR' '$AGENT_DIR'"

check "skill validates" \
  python3 "$REPO_ROOT/skills/best-practices-skills/scripts/validate_skill.py" \
    "$SCRIPT_DIR" --skills-root "$REPO_ROOT/skills"

check "skill declares README capability" grep -q "readme-quality-contract" "$SCRIPT_DIR/SKILL.md"
check "skill composes project-knowledge" grep -q "project-knowledge" "$SCRIPT_DIR/SKILL.md"
check "agent declares dag spec" grep -q "dag_spec:" "$AGENT_DIR/persona.yaml"
check "agent registry name present" grep -q "^name: readme-maintainer" "$AGENT_DIR/AGENTS.md"
check "agent denies git push" grep -q "git_push" "$AGENT_DIR/persona.yaml"
check "agent has final receipt contract" grep -q "readme-maintainer-receipt.json" "$AGENT_DIR/persona.yaml"

echo "Result: PASS"
