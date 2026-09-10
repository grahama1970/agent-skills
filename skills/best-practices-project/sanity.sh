#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_ROOT="$(dirname "$SCRIPT_DIR")"
VALIDATOR="$SKILLS_ROOT/best-practices-skills/scripts/validate_skill.py"

uv run --project "$SKILLS_ROOT/best-practices-skills" python "$VALIDATOR" "$SCRIPT_DIR" --skills-root "$SKILLS_ROOT"

grep -Fq -- '- setup-project' "$SCRIPT_DIR/SKILL.md"
grep -Fq -- '- best-practices-python' "$SCRIPT_DIR/SKILL.md"
grep -Fq -- '- best-practices-react' "$SCRIPT_DIR/SKILL.md"
grep -Fq -- '- explain-project' "$SCRIPT_DIR/SKILL.md"
grep -Fq -- '- agentic-evals' "$SCRIPT_DIR/SKILL.md"
grep -Fq -- '$setup-project plan' "$SCRIPT_DIR/SKILL.md"
grep -Fq -- '$explain-project' "$SCRIPT_DIR/SKILL.md"

echo "Result: PASS"
