#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
PI_MONO="$(cd "$SKILL_DIR/../../.." && pwd)"
SKILLS_DIR="$PI_MONO/.pi/skills"
INBOX_REGISTRY="${HOME}/.agent-inbox/projects.json"

PASS=0; FAIL=0; WARN=0

check() {
  local label="$1" result="$2"
  if [[ "$result" == "ok" ]]; then
    echo "  PASS  $label"; PASS=$((PASS + 1))
  elif [[ "$result" == "warn" ]]; then
    echo "  WARN  $label"; WARN=$((WARN + 1))
  else
    echo "  FAIL  $label"; FAIL=$((FAIL + 1))
  fi
}

echo "=== monitor-codebase sanity ==="

# Check executable composed skills have run.sh
EXEC_SKILLS=(
  project-state cleanup ingest-code dogpile agent-inbox
  scheduler memory create-code battle task-monitor
)
for skill in "${EXEC_SKILLS[@]}"; do
  if [[ -f "$SKILLS_DIR/$skill/run.sh" ]]; then
    check "$skill has run.sh" "ok"
  else
    check "$skill has run.sh" "fail"
  fi
done

# Check reference-only best-practices skills have SKILL.md
REF_SKILLS=(
  best-practices-python best-practices-react best-practices-kde
  best-practices-skills best-practices-streamdeck
)
for skill in "${REF_SKILLS[@]}"; do
  if [[ -f "$SKILLS_DIR/$skill/SKILL.md" ]]; then
    check "$skill has SKILL.md" "ok"
  else
    check "$skill has SKILL.md" "fail"
  fi
done

# Check agent-inbox registry
if [[ -f "$INBOX_REGISTRY" ]]; then
  check "agent-inbox projects.json exists" "ok"
  project_count=$(python3 -c "import json; print(len(json.load(open('$INBOX_REGISTRY'))))" 2>/dev/null || echo 0)
  if [[ "$project_count" -gt 0 ]]; then
    check "at least 1 registered project ($project_count found)" "ok"
    # Verify at least one resolves to a valid path
    first_path=$(python3 -c "import json; d=json.load(open('$INBOX_REGISTRY')); print(list(d.values())[0])" 2>/dev/null)
    if [[ -d "$first_path" ]]; then
      check "first project path is valid ($first_path)" "ok"
    else
      check "first project path is valid ($first_path)" "warn"
    fi
  else
    check "at least 1 registered project" "fail"
  fi
else
  check "agent-inbox projects.json exists" "fail"
fi

# Check memory skill directory is intact
if [[ -f "$SKILLS_DIR/memory/run.sh" && -f "$SKILLS_DIR/memory/SKILL.md" ]]; then
  check "memory skill is present" "ok"
else
  check "memory skill is present" "warn"
fi

# Check artifacts dir
if [[ -d "$SKILL_DIR/artifacts" ]]; then
  check "artifacts directory exists" "ok"
else
  check "artifacts directory exists" "warn"
fi

# Check own run.sh is executable
if [[ -x "$SKILL_DIR/run.sh" ]]; then
  check "run.sh is executable" "ok"
else
  check "run.sh is executable" "fail"
fi

echo ""
echo "Results: $PASS passed, $FAIL failed, $WARN warnings"
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
