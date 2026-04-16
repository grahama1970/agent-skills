#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROMPT=""
PERSONA=""
MAX_CYCLES=3
OUT_DIR="outputs/run-$(date +%s)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --persona) PERSONA="$2"; shift 2 ;;
    --max-cycles) MAX_CYCLES="$2"; shift 2 ;;
    *) PROMPT="$1"; shift ;;
  esac
done

if [[ -z "$PROMPT" || -z "$PERSONA" ]]; then
  echo "Usage: ./run.sh loop \"<prompt>\" --persona NAME [--max-cycles N]"
  exit 1
fi

echo "🚀 Starting Design Loop for: $PROMPT"
echo "👤 Primary Persona: $PERSONA"
echo "📂 Output Directory: $OUT_DIR"

# 1. Create Variant
echo "Step 1: Scaffolding Production-Ready App..."
"$SKILL_DIR/run.sh" create "$PROMPT" --out "$OUT_DIR"

APP_DIR="$OUT_DIR/app"
cd "$APP_DIR"

# 2. Start Dev Server
echo "Step 2: Starting Dev Server..."
# We use a randomized port to avoid conflicts
PORT=$((3000 + RANDOM % 1000))
pnpm dev --port $PORT &
PID=$!

# Ensure cleanup on exit
cleanup() {
  echo "🧹 Stopping Dev Server (PID $PID)..."
  kill $PID 2>/dev/null || true
}
trap cleanup EXIT

# Wait for server
echo "Waiting for server to be ready on port $PORT..."
sleep 10 # Simple wait, ideally use wait-on or similar

URL="http://localhost:$PORT"

# 3. Loop
for ((i=1; i<=MAX_CYCLES; i++)); do
  echo "--- Cycle $i/$MAX_CYCLES ---"
  
  # Council Critique
  echo "Step 3: Convening Persona Council..."
  "$SKILL_DIR/run.sh" council --url "$URL" --persona "$PERSONA" --out "$OUT_DIR/cycle-$i"
  
  # Iterate
  if [[ $i -lt $MAX_CYCLES ]]; then
    echo "Step 4: Iterating on Design..."
    "$SKILL_DIR/run.sh" iterate --dir "$OUT_DIR/cycle-$i"
    
    # Wait for Next.js to rebuild
    echo "Waiting for rebuild..."
    sleep 5
  else
    echo "🏁 Final cycle complete."
  fi
done

echo "✅ Design Loop Finished. Final output in $APP_DIR"
