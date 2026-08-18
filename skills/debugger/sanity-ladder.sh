#!/usr/bin/env bash
# Deterministic gate for the debugger escalation ladder.
#
# The fixtures store artifact paths as FIXTURE_DIR/<name> so they stay
# relocatable; this script materializes them into a temp dir with real files,
# because "the cited artifact exists" is the load-bearing check and cannot be
# exercised against a placeholder.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="$(mktemp -d /tmp/debugger-ladder.XXXXXX)"
trap 'rm -rf "$WORK_DIR"' EXIT
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/mnt/storage12tb/skills/debugger/.venv}"
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"
PYTHON=(uv run --project "$SCRIPT_DIR" python)
VALIDATOR="$SCRIPT_DIR/scripts/validate_debugger_ladder.py"
FIXTURES="$SCRIPT_DIR/fixtures/ladders"

cp "$FIXTURES/dagrun.json" "$FIXTURES/proof.json" "$WORK_DIR/"
for fixture in "$FIXTURES"/canonical-*.json; do
  sed "s#FIXTURE_DIR#$WORK_DIR#g" "$fixture" > "$WORK_DIR/$(basename "$fixture")"
done

"${PYTHON[@]}" "$VALIDATOR" "$WORK_DIR/canonical-valid.json" --expect-valid
"${PYTHON[@]}" "$VALIDATOR" "$WORK_DIR/canonical-invalid-skips-dispatch.json" --expect-invalid
"${PYTHON[@]}" "$VALIDATOR" "$WORK_DIR/canonical-invalid-no-research-rung.json" --expect-invalid

# The check an agent is most likely to route around: cite an artifact it never
# read. Proven here against a path that genuinely does not exist.
python3 - "$WORK_DIR" <<'PY'
import json, pathlib, sys
work = pathlib.Path(sys.argv[1])
payload = json.loads((work / "canonical-valid.json").read_text())
payload["rungs"][0]["artifact"] = str(work / "never-written.json")
(work / "ghost.json").write_text(json.dumps(payload))
PY
"${PYTHON[@]}" "$VALIDATOR" "$WORK_DIR/ghost.json" --expect-invalid

echo "LADDER SANITY OK"
