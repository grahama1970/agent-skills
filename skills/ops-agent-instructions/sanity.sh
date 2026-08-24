#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"$SCRIPT_DIR/run.sh" audit --json --require-identical >/tmp/ops-agent-instructions-audit.json
"$SCRIPT_DIR/run.sh" self-test --case all --json >/tmp/ops-agent-instructions-self-test.json

python3 - "$SCRIPT_DIR" <<'PY'
from pathlib import Path
import sys

skill_dir = Path(sys.argv[1])
for rel in ("SKILL.md", "run.sh", "sanity.sh", "pyproject.toml", "fixtures/agentic_eval.json"):
    path = skill_dir / rel
    if not path.exists():
        raise SystemExit(f"missing required file: {rel}")

script = skill_dir / "scripts" / "audit_agent_instructions.py"
lines = script.read_text(encoding="utf-8").splitlines()
if len(lines) > 800:
    raise SystemExit(f"{script} has {len(lines)} lines, expected <= 800")
PY

echo "ops-agent-instructions sanity passed"
