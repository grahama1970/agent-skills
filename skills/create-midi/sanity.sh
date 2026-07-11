#!/bin/bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== create-midi sanity ==="

# --- Structure checks ---
[[ -f "$SCRIPT_DIR/SKILL.md" ]] \
  && echo "  SKILL.md: PASS" \
  || { echo "  SKILL.md: FAIL"; exit 1; }

[[ -x "$SCRIPT_DIR/run.sh" ]] \
  && echo "  run.sh executable: PASS" \
  || { echo "  run.sh executable: FAIL"; exit 1; }

grep -q "triggers:" "$SCRIPT_DIR/SKILL.md" \
  && echo "  triggers section: PASS" \
  || { echo "  triggers section: FAIL"; exit 1; }

[[ -f "$SCRIPT_DIR/compose.py" ]] \
  && echo "  compose.py: PASS" \
  || { echo "  compose.py: FAIL"; exit 1; }

[[ -f "$SCRIPT_DIR/midi_utils.py" ]] \
  && echo "  midi_utils.py: PASS" \
  || { echo "  midi_utils.py: FAIL"; exit 1; }

[[ -f "$SCRIPT_DIR/battle_score_packet.py" ]] \
  && echo "  battle_score_packet.py: PASS" \
  || { echo "  battle_score_packet.py: FAIL"; exit 1; }

# --- Prompt managed by /prompt-lab ---
PROMPT="$SCRIPT_DIR/../prompt-lab/prompts/midi_arrangement_v1.txt"
[[ -f "$PROMPT" ]] \
  && echo "  prompt-lab/prompts/midi_arrangement_v1.txt: PASS" \
  || { echo "  prompt-lab/prompts/midi_arrangement_v1.txt: FAIL (missing)"; exit 1; }

# --- DoD: verify --help shows required flags ---
echo "  Checking compose.py --help flags..."
HELP_OUT=$(cd "$SCRIPT_DIR" && uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/compose.py" --help 2>&1)
for FLAG in "--lyrics" "--references" "--heart" "--out"; do
  echo "$HELP_OUT" | grep -qF -- "$FLAG" \
    && echo "    $FLAG: PASS" \
    || { echo "    $FLAG: FAIL (not in --help output)"; exit 1; }
done

echo "  Checking Battle score-packet positive fixture..."
POSITIVE_REPORT="$(mktemp)"
"$SCRIPT_DIR/run.sh" validate-score-packet \
  --packet "$SCRIPT_DIR/fixtures/battle-score-packet.valid.json" \
  --motif-manifest "$SCRIPT_DIR/fixtures/battle-score-motif-manifest.json" \
  --out "$POSITIVE_REPORT" >/tmp/create-midi-positive-score-packet.out
python3 - "$POSITIVE_REPORT" <<'PY'
import json
import sys
report = json.load(open(sys.argv[1], encoding="utf-8"))
assert report["status"] == "PASS", report
assert report["mocked"] is False
assert report["live"] == "local_deterministic_validator"
assert report["checks"]["rendering_not_run"] is True
assert report["checks"]["playback_not_run"] is True
print("    valid score packet: PASS")
PY

echo "  Checking Battle score-packet negative claim fixture..."
NEGATIVE_REPORT="$(mktemp)"
if "$SCRIPT_DIR/run.sh" validate-score-packet \
  --packet "$SCRIPT_DIR/fixtures/battle-score-packet.invalid-claim.json" \
  --motif-manifest "$SCRIPT_DIR/fixtures/battle-score-motif-manifest.json" \
  --out "$NEGATIVE_REPORT" >/tmp/create-midi-negative-score-packet.out 2>&1; then
  echo "    invalid claim fixture: FAIL (validator accepted overclaim)"
  exit 1
fi
python3 - "$NEGATIVE_REPORT" <<'PY'
import json
import sys
report = json.load(open(sys.argv[1], encoding="utf-8"))
assert report["status"] == "FAIL", report
assert any("claim" in error.lower() for error in report["errors"]), report
print("    invalid claim fixture: PASS")
PY

echo "=== 0 errors ==="
