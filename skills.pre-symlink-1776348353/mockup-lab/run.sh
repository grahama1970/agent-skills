#!/usr/bin/env bash
set -euo pipefail
unset VIRTUAL_ENV 2>/dev/null || true
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"

# Load API key from project .env if not set
if [[ -z "${STITCH_API_KEY:-}" ]]; then
  ENV_FILE="$(git -C "$SKILL_DIR" rev-parse --show-toplevel 2>/dev/null)/.env"
  if [[ -f "$ENV_FILE" ]]; then
    export STITCH_API_KEY="$(grep '^STITCH_API_KEY=' "$ENV_FILE" | cut -d'"' -f2)"
  fi
fi

if [[ -z "${STITCH_API_KEY:-}" ]]; then
  echo "ERROR: STITCH_API_KEY not set. Add to .env or export." >&2
  exit 1
fi

# Ensure SDK is available
if ! node -e "require('@google/stitch-sdk')" 2>/dev/null; then
  echo "Installing @google/stitch-sdk..." >&2
  npm install --no-save @google/stitch-sdk 2>/dev/null
fi

CMD="${1:-help}"
shift || true

case "$CMD" in
  generate)
    node "$SKILL_DIR/stitch_cli.mjs" generate "$@"
    ;;
  variants)
    node "$SKILL_DIR/stitch_cli.mjs" variants "$@"
    ;;
  iterate)
    node "$SKILL_DIR/stitch_cli.mjs" iterate "$@"
    ;;
  pull)
    node "$SKILL_DIR/stitch_cli.mjs" pull "$@"
    ;;
  list)
    node "$SKILL_DIR/stitch_cli.mjs" list "$@"
    ;;
  converge)
    node "$SKILL_DIR/stitch_cli.mjs" converge "$@"
    ;;
  theme)
    node "$SKILL_DIR/stitch_cli.mjs" theme "$@"
    ;;
  explore)
    node "$SKILL_DIR/stitch_cli.mjs" explore "$@"
    ;;
  reference)
    # Gemini→Stitch pipeline: analyze reference image → output Stitch-optimized prompt
    # Usage: ./run.sh reference --image ref.png [--spec spec.md] [--output stitch-prompt.txt]
    IMAGE=""
    SPEC=""
    OUTPUT=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --image) IMAGE="$2"; shift 2 ;;
        --spec) SPEC="$2"; shift 2 ;;
        --output) OUTPUT="$2"; shift 2 ;;
        *) shift ;;
      esac
    done
    if [[ -z "$IMAGE" ]]; then
      echo "Usage: ./run.sh reference --image <screenshot.png> [--spec <spec.md>] [--output <file>]" >&2
      exit 1
    fi
    if [[ ! -f "$IMAGE" ]]; then
      echo "ERROR: Image not found: $IMAGE" >&2
      exit 1
    fi

    GEMINI_KEY="${GEMINI_API_KEY:-}"
    if [[ -z "$GEMINI_KEY" ]]; then
      # Try project .env
      ENV_FILE="$(git -C "$SKILL_DIR" rev-parse --show-toplevel 2>/dev/null)/.env"
      if [[ -f "$ENV_FILE" ]]; then
        GEMINI_KEY="$(grep '^GEMINI_API_KEY=' "$ENV_FILE" | cut -d'"' -f2)"
      fi
    fi
    if [[ -z "$GEMINI_KEY" ]]; then
      echo "ERROR: GEMINI_API_KEY not set." >&2
      exit 1
    fi

    SPEC_TEXT=""
    if [[ -n "$SPEC" && -f "$SPEC" ]]; then
      SPEC_TEXT="$(cat "$SPEC")"
    fi

    IMG_B64="$(base64 -w0 "$IMAGE")"
    MIME="image/png"
    [[ "$IMAGE" == *.jpg || "$IMAGE" == *.jpeg ]] && MIME="image/jpeg"

    PROMPT="You are a UI design translator. Analyze this reference screenshot and produce a Stitch-optimized text prompt (UNDER 100 WORDS) that will recreate a similar layout and design pattern.

Rules for the output prompt:
- Reference existing products by name (e.g. 'PromptFoo-style eval grid')
- State the PURPOSE in one sentence
- State CONSTRAINTS (theme, layout, device)
- Use UI/UX terminology (navigation bar, card layout, data table)
- Do NOT specify hex colors, pixel sizes, or CSS properties
- Output ONLY the prompt text, nothing else"

    if [[ -n "$SPEC_TEXT" ]]; then
      PROMPT="$PROMPT

Additional context from spec:
$SPEC_TEXT"
    fi

    RESULT=$(python3 -c "
import json, sys, base64
import httpx

body = {
    'contents': [{'parts': [
        {'text': '''$PROMPT'''},
        {'inlineData': {'mimeType': '$MIME', 'data': '$IMG_B64'}}
    ]}],
    'generationConfig': {'temperature': 0.4, 'maxOutputTokens': 300}
}

resp = httpx.post(
    'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=$GEMINI_KEY',
    json=body, timeout=60.0
)
resp.raise_for_status()
text = resp.json()['candidates'][0]['content']['parts'][0]['text']
print(text.strip())
" 2>&1)

    if [[ -n "$OUTPUT" ]]; then
      echo "$RESULT" > "$OUTPUT"
      echo "Stitch prompt written to: $OUTPUT" >&2
    fi
    echo "$RESULT"
    ;;
  mockup)
    # Gemini ZIP mockup: bundle context → Gemini 3 Flash → HTML + PNG
    # Usage: ./run.sh mockup --brief "..." --files f1 f2 --screenshots s1 --references url1 --output dir/
    python3 "$SKILL_DIR/gemini_mockup.py" generate "$@"
    ;;
  mockup-review)
    # VLM review: compare implementation against reference
    python3 "$SKILL_DIR/gemini_mockup.py" review "$@"
    ;;
  review)
    node "$SKILL_DIR/stitch_cli.mjs" review "$@"
    ;;
  review-ui)
    node "$SKILL_DIR/review_ui.mjs" "$@"
    # Serve via HTTP (iframes need HTTP, not file://) and open browser
    MANIFEST="$(echo "$@" | sed -n 's/.*--manifest \([^ ]*\).*/\1/p')"
    if [[ -n "$MANIFEST" ]]; then
      OUT_DIR="$(echo "$@" | sed -n 's/.*--output \([^ ]*\).*/\1/p')"
      REVIEW_DIR="${OUT_DIR:-$(dirname "$MANIFEST")}"
      REVIEW_DIR="$(cd "$REVIEW_DIR" && pwd)"
      PORT="${MOCKUP_REVIEW_PORT:-8321}"
      # Kill any previous review server on this port
      fuser -k "$PORT/tcp" 2>/dev/null || true
      sleep 0.3
      cd "$REVIEW_DIR" && python3 -m http.server "$PORT" &>/dev/null &
      echo "Review server: http://localhost:$PORT/review.html"
      sleep 0.5
      xdg-open "http://localhost:$PORT/review.html" 2>/dev/null &
    fi
    ;;
  help|*)
    echo "mockup-lab: UI mockup generation via Gemini (primary) and Stitch (legacy)"
    echo ""
    echo "Commands:"
    echo "  mockup    --brief <text> --files f1 f2 --screenshots s1 --output dir/ [--variations 3]"
    echo "            Generate N HTML/CSS mockup variations via Gemini 3 Flash (ZIP context)"
    echo "  mockup-review  --mockup <html|png> --reference <png>  VLM comparison scoring"
    echo "  generate  --spec <file> [--device desktop|mobile|tablet]  Create Stitch project (legacy)"
    echo "  variants  --project <id> --screen <id> --prompt <text>"
    echo "  iterate   --project <id> --screen <id> --feedback <text>"
    echo "  pull      --project <id> --screen <id> --output <dir>"
    echo "  list      [--project <id>]           List projects or screens"
    echo "  explore   --project <id> --screen <id> --views <file.json> [--output <dir>]"
    echo "  review    --project <id> --screen <id> --screenshot <path.png>"
    echo "  review-ui --manifest <manifest.json> [--output <dir>] [--title <name>]"
    echo "  converge  --spec <file> [--max-rounds 3]"
    echo "  theme     --project <id> [--output <file>]"
    ;;
esac
