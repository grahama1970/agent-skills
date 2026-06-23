#!/usr/bin/env bash
set -euo pipefail
unset VIRTUAL_ENV

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python - <<'PY'
from pathlib import Path
import yaml

skill = Path("skills/personaplex")
text = (skill / "SKILL.md").read_text()
assert text.startswith("---\n"), "SKILL.md frontmatter missing"
frontmatter = text.split("---", 2)[1]
data = yaml.safe_load(frontmatter)
for key in ["name", "description", "triggers", "provides", "composes", "complies"]:
    assert key in data, f"missing frontmatter key {key}"
assert data["name"] == "personaplex"
assert "best-practices-skills" in data["complies"]
assert "best-practices-python" in data["complies"]
for dirname in ["outputs", "work", "logs", "data", "models"]:
    path = skill / dirname
    assert path.is_symlink(), f"{path} must be a symlink to /mnt/storage12tb"
PY

uv run --directory "$SCRIPT_DIR" python -m py_compile "$SCRIPT_DIR/scripts/personaplex_cli.py"
uv run --directory "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/personaplex_cli.py" --help >/dev/null

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
python - <<PY
import json
from pathlib import Path
pack = {
    "schema": "orpheus.personaplex_reference_pack.v1",
    "persona": "fixture",
    "references": []
}
Path("$tmp/pack.json").write_text(json.dumps(pack))
PY
uv run --directory "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/personaplex_cli.py" validate-pack --reference-pack "$tmp/pack.json" --allow-empty >/dev/null

python - <<PY
import json
import subprocess
from pathlib import Path
bad = {
    "schema": "orpheus.personaplex_reference_pack.v1",
    "persona": "../escape",
    "references": []
}
Path("$tmp/bad-pack.json").write_text(json.dumps(bad))
cmd = [
    "uv", "run", "--directory", "$SCRIPT_DIR", "python",
    "$SCRIPT_DIR/scripts/personaplex_cli.py",
    "validate-pack",
    "--reference-pack", "$tmp/bad-pack.json",
    "--allow-empty",
]
result = subprocess.run(cmd, text=True, capture_output=True)
assert result.returncode != 0, "path-like persona slug must fail validation"
PY

grep -q -- "--save-voice-embeddings" \
  /home/graham/workspace/experiments/personaplex/moshi/moshi/offline.py

echo "personaplex sanity PASS"
