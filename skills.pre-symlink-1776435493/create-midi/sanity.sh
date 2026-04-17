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

# --- Prompt managed by /prompt-lab ---
PROMPT="$SCRIPT_DIR/../prompt-lab/prompts/midi_arrangement_v1.txt"
[[ -f "$PROMPT" ]] \
  && echo "  prompt-lab/prompts/midi_arrangement_v1.txt: PASS" \
  || { echo "  prompt-lab/prompts/midi_arrangement_v1.txt: FAIL (missing)"; exit 1; }

# --- DoD: verify --help shows required flags ---
echo "  Checking compose.py --help flags..."
HELP_OUT=$(cd "$SCRIPT_DIR" && uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/compose.py" --help 2>&1)
for FLAG in "--lyrics" "--references" "--heart" "--out"; do
  echo "$HELP_OUT" | grep -qF "$FLAG" \
    && echo "    $FLAG: PASS" \
    || { echo "    $FLAG: FAIL (not in --help output)"; exit 1; }
done

echo "=== 0 errors ==="
