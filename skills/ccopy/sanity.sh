#!/usr/bin/env bash
# Behavioral sanity gates for ccopy
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${ROOT}/scripts${PYTHONPATH:+:$PYTHONPATH}"
SKILL="${ROOT}/SKILL.md"
FAIL=0

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; FAIL=1; }

# Frontmatter contract
for field in triggers provides composes; do
  if rg -q "^${field}:" "$SKILL"; then
    pass "SKILL.md has ${field}"
  else
    fail "SKILL.md missing required frontmatter field: ${field}"
  fi
done

if rg -q "^name: ccopy" "$SKILL"; then
  pass "SKILL.md name matches directory"
else
  fail "SKILL.md name must be ccopy"
fi

# CLI smoke
if python3 "${ROOT}/scripts/cursor_copy.py" --help >/dev/null 2>&1; then
  pass "CLI --help"
else
  fail "CLI --help failed (is typer installed?)"
fi

# Unit tests (positive + negative controls)
if python3 -m unittest discover -s "${ROOT}/tests" -v; then
  pass "unit tests"
else
  fail "unit tests"
fi

# Transcript positive control
OUT="$(PYTHONPATH="${ROOT}/scripts" python3 - <<PY
from pathlib import Path
from ccopy.transcript import parse_agent_transcript_last_turn
u, a = parse_agent_transcript_last_turn(Path("${ROOT}") / "tests/fixtures/sample_transcript.jsonl")
print(u.text, "|||", a.text)
PY
)"
if [[ "$OUT" == "last user question ||| last assistant answer" ]]; then
  pass "transcript fixture extracts last complete turn"
else
  fail "transcript fixture unexpected output: $OUT"
fi

# Negative control: empty transcript fails closed
if PYTHONPATH="${ROOT}/scripts" python3 - <<PY >/dev/null 2>&1
from pathlib import Path
import tempfile
from ccopy.transcript import parse_agent_transcript_last_turn
from ccopy.errors import CursorCopyError
with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
    f.write("\n")
    path = Path(f.name)
try:
    parse_agent_transcript_last_turn(path)
    raise SystemExit(0)
except CursorCopyError:
    raise SystemExit(1)
PY
then
  fail "empty transcript should fail closed"
else
  pass "empty transcript fails closed"
fi

# Safety: no writes to real Cursor DB paths in package code
if rg -q "state\.vscdb.*(write|UPDATE|INSERT|DELETE)" "${ROOT}/scripts/ccopy" -i; then
  fail "possible write path to Cursor SQLite detected"
else
  pass "no obvious SQLite write operations in ccopy package"
fi

if [[ "$FAIL" -ne 0 ]]; then
  echo "sanity.sh: FAILED" >&2
  exit 1
fi
echo "sanity.sh: OK"
