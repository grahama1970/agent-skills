#!/usr/bin/env bash
# Eval: boot the dream API host on an ephemeral port, read back /runs from the
# real roots, and prove the path policy refuses a file outside its roots.
# Modes: "runs" (positive readback) | "policy" (adversarial 403).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
MODE="${1:-runs}"
PORT="${DREAM_API_EVAL_PORT:-8797}"

setsid env DREAM_API_PORT="$PORT" npx tsx scripts/dream-api-host.ts &
HOST_PID=$!
cleanup() {
  kill -TERM -"$HOST_PID" 2>/dev/null || kill "$HOST_PID" 2>/dev/null || true
  for _ in $(seq 1 20); do
    if ! kill -0 "$HOST_PID" 2>/dev/null; then
      wait "$HOST_PID" 2>/dev/null || true
      return 0
    fi
    sleep 0.1
  done
  kill -KILL -"$HOST_PID" 2>/dev/null || kill -KILL "$HOST_PID" 2>/dev/null || true
  wait "$HOST_PID" 2>/dev/null || true
}
trap cleanup EXIT

for _ in $(seq 1 30); do
  curl -sf -o /dev/null "http://127.0.0.1:$PORT/api/projects/dream/runs" && break
  sleep 0.5
done

if [ "$MODE" = "runs" ]; then
  BODY=$(curl -sf "http://127.0.0.1:$PORT/api/projects/dream/runs")
  COUNT=$(printf '%s' "$BODY" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["status"]=="ok"; print(len(d["runs"]))')
  [ "$COUNT" -ge 1 ] || { echo "RUNS_EMPTY"; exit 1; }
  printf '%s' "$BODY" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert any(r.get("runRoot") and r.get("manifestPath") for r in d["runs"]), "manifest-backed run missing"'
  echo "DREAM_API_RUNS_OK count=$COUNT manifest_run_listed=true"
else
  CODE=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/api/projects/dream/asset?path=/etc/passwd")
  [ "$CODE" = "403" ] || { echo "PATH_POLICY_LEAK: /etc/passwd returned $CODE, expected 403"; exit 1; }
  echo "PATH_POLICY_REFUSED_OUTSIDE_ROOT code=403"
fi
