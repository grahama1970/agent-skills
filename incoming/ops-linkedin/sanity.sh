#!/usr/bin/env bash
# Deterministic local sanity checks for the draft-only LinkedIn skill.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHONPATH="$SCRIPT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH
export OPS_LINKEDIN_USE_SYSTEM_PYTHON=1

echo "=== [ops-linkedin] Sanity Check ==="

required=(
  SKILL.md
  README.md
  PROJECT_KNOWLEDGE.md
  pyproject.toml
  run.sh
  src/ops_linkedin/models.py
  src/ops_linkedin/service.py
  src/ops_linkedin/cli.py
  tests/test_service.py
  fixtures/agentic_eval.json
)
for rel in "${required[@]}"; do
  if [[ ! -f "$SCRIPT_DIR/$rel" ]]; then
    echo "FAIL: missing $rel" >&2
    exit 1
  fi
done

echo "Check: Python modules parse and have module docstrings"
python3 - "$SCRIPT_DIR" <<'PY'
import ast
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
for path in sorted((root / "src").rglob("*.py")):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    if not ast.get_docstring(tree):
        raise SystemExit(f"missing module docstring: {path}")
print("module-docstrings=PASS")
PY

echo "Check: runtime has no browser, session, scraping, or HTTP implementation"
python3 - "$SCRIPT_DIR" <<'PY'
import ast
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
prohibited = {
    "httpx",
    "playwright",
    "requests",
    "selenium",
    "urllib.request",
    "websocket",
    "websockets",
}
found = []
for path in sorted((root / "src").rglob("*.py")):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            if any(name == item or name.startswith(f"{item}.") for item in prohibited):
                found.append(f"{path}: {name}")
if found:
    raise SystemExit("prohibited imports:\n" + "\n".join(found))
print("no-browser-network-imports=PASS")
PY

echo "Check: unit tests"
python3 -m pytest "$SCRIPT_DIR/tests" -q

echo "Check: policy and status entrypoints"
bash "$SCRIPT_DIR/run.sh" policy | grep -q '"design_posture": "draft-and-human-handoff"'
bash "$SCRIPT_DIR/run.sh" status | grep -q '"overall_readiness": "READY_FOR_DRAFT_ONLY_USE"'

echo "Check: positive prepare and packet validation"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT
bash "$SCRIPT_DIR/run.sh" prepare \
  "$SCRIPT_DIR/assets/examples/publish-post.json" \
  --output "$tmp_dir/post-packet.json"
bash "$SCRIPT_DIR/run.sh" validate "$tmp_dir/post-packet.json" | grep -q '"valid": true'

echo "Check: evidence-sensitive request fails closed"
set +e
bash "$SCRIPT_DIR/run.sh" prepare \
  "$SCRIPT_DIR/assets/examples/profile-update-blocked.json" \
  --output "$tmp_dir/blocked-packet.json" >/dev/null
blocked_rc=$?
set -e
if [[ "$blocked_rc" -ne 3 ]]; then
  echo "FAIL: expected blocked prepare exit 3, got $blocked_rc" >&2
  exit 1
fi
grep -q '"readiness": "BLOCKED_UNVERIFIED_CLAIMS"' "$tmp_dir/blocked-packet.json"

echo "Check: attestation requires explicit human confirmation"
set +e
bash "$SCRIPT_DIR/run.sh" attest "$tmp_dir/post-packet.json" --actor sanity >/dev/null 2>&1
attest_rc=$?
set -e
if [[ "$attest_rc" -ne 3 ]]; then
  echo "FAIL: expected unattested exit 3, got $attest_rc" >&2
  exit 1
fi

bash "$SCRIPT_DIR/run.sh" attest \
  "$tmp_dir/post-packet.json" \
  --actor sanity \
  --confirm-human-completed \
  --output "$tmp_dir/completed.json" >/dev/null
grep -q '"platform_verified": false' "$tmp_dir/completed.json"
grep -q '"execution_claim": "USER_ATTESTED_MANUAL_ACTION"' "$tmp_dir/completed.json"

echo "Result: PASS"
