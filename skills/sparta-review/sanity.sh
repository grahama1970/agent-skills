#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PI_SKILLS="/home/graham/workspace/experiments/pi-mono/.pi/skills"

echo "=== sparta-review sanity ==="

# 1. Delegated skills exist
echo -n "review-sparta exists... "
[[ -f "$PI_SKILLS/review-sparta/review_sparta.py" ]] && echo "OK" || echo "MISSING"

echo -n "reality-check-sparta exists... "
[[ -f "$PI_SKILLS/reality-check-sparta/check.py" ]] && echo "OK" || echo "MISSING"

# 2. /dogpile available
echo -n "dogpile skill exists... "
[[ -f "$PI_SKILLS/dogpile/run.sh" ]] && echo "OK" || echo "MISSING"

# 3. /ask consult available
echo -n "ask consult exists... "
[[ -f "$PI_SKILLS/ask/consult.py" ]] && echo "OK" || echo "MISSING"

# 4. SPARTA DB accessible
echo -n "SPARTA DuckDB exists... "
DB="/home/graham/workspace/experiments/sparta/data/runs/run-recovery-verify/sparta.duckdb"
[[ -f "$DB" ]] && echo "OK ($(du -h "$DB" | cut -f1))" || echo "MISSING"

# 5. Brandon persona file
echo -n "Brandon persona exists... "
[[ -f "$PI_SKILLS/reality-check-sparta/BRANDON_BAILEY_PERSONA.md" ]] && echo "OK" || echo "MISSING"

# 6. Help command works
echo -n "CLI help... "
bash "$SKILL_DIR/run.sh" help >/dev/null 2>&1 && echo "OK" || echo "FAIL"

# 7. Convergence loop exists
echo -n "converge.py exists... "
[[ -f "$SKILL_DIR/converge.py" ]] && echo "OK" || echo "MISSING"

# 8. prompt-lab available for recalibration
echo -n "prompt-lab skill exists... "
[[ -f "$PI_SKILLS/prompt-lab/run.sh" ]] && echo "OK" || echo "MISSING"

echo "=== sanity complete ==="
