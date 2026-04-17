#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check SKILL.md frontmatter
python3 - <<'PY'
from pathlib import Path
import yaml

skill = Path("SKILL.md")
text = skill.read_text(encoding="utf-8")
if not text.startswith("---\n"):
    raise SystemExit("SKILL.md must start with YAML frontmatter")
parts = text.split("---\n", 2)
if len(parts) < 3:
    raise SystemExit("SKILL.md frontmatter closing delimiter missing")
data = yaml.safe_load(parts[1])
required = ["name", "description", "triggers", "provides", "composes"]
missing = [k for k in required if k not in data]
if missing:
    raise SystemExit(f"Missing frontmatter keys: {missing}")
if data["name"] != "review-paper":
    raise SystemExit("Frontmatter name must match directory name")
print("SKILL.md frontmatter OK")
PY

# Check CLI loads
if command -v uv >/dev/null 2>&1; then
  uv run --project "$SCRIPT_DIR" python -m review_paper.cli --help >/dev/null
else
  python3 -m review_paper.cli --help >/dev/null
fi

# Check imports: loguru not logging, httpx not requests
python3 -c "
import ast, sys
from pathlib import Path
for py in Path('review_paper').glob('*.py'):
    tree = ast.parse(py.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == 'logging':
                    print(f'ERROR: {py} uses logging instead of loguru')
                    sys.exit(1)
                if alias.name == 'requests':
                    print(f'ERROR: {py} uses requests instead of httpx')
                    sys.exit(1)
print('Import checks OK')
"

# Run against sample paper if available
if [[ -f examples/sample_paper.md ]]; then
  if command -v uv >/dev/null 2>&1; then
    uv run --project "$SCRIPT_DIR" python -m review_paper.cli diagnose examples/sample_paper.md --json-out /tmp/review-paper-sanity.json >/dev/null
  else
    python3 -m review_paper.cli diagnose examples/sample_paper.md --json-out /tmp/review-paper-sanity.json >/dev/null
  fi
  python3 -c "
import json
d = json.load(open('/tmp/review-paper-sanity.json'))
assert 'diagnostics' in d, 'Missing diagnostics'
assert 'humanization' in d, 'Missing humanization'
assert 'persona_alignment' in d, 'Missing persona_alignment'
assert 'revision_plan' in d, 'Missing revision_plan'
print('Sample paper analysis OK')
"
  rm -f /tmp/review-paper-sanity.json
fi

echo "sanity.sh OK"
