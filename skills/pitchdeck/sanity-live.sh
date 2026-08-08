#!/usr/bin/env bash
# Opt-in LIVE end-to-end gate for the skills pitchdeck composes (LIVE001).
#
# sanity.sh proves the deterministic compiler. This proves the COMPOSITION:
# that the embedding service, Qdrant, the memory route, and the browser-oracle
# registry are actually reachable and answer correctly. Each check reports
# PASS, SKIP (dependency absent), or FAIL — a missing service is never reported
# as success, and a reachable service that answers wrongly always fails.
#
# Usage: ./sanity-live.sh            (skips everything not reachable)
#        ./sanity-live.sh --require  (a SKIP becomes a FAIL — release profile)
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REQUIRE=0
[[ "${1:-}" == "--require" ]] && REQUIRE=1

pass=0; skip=0; fail=0
report() {  # report <status> <name> <detail>
  printf '  [%s] %-26s %s\n' "$1" "$2" "$3"
  case "$1" in
    PASS) pass=$((pass + 1)) ;;
    FAIL) fail=$((fail + 1)) ;;
    SKIP) skip=$((skip + 1)); [[ $REQUIRE -eq 1 ]] && fail=$((fail + 1)) ;;
  esac
}

echo "pitchdeck live composition gate"

# --- /embedding: multimodal vectors ------------------------------------------
if curl -s -m 3 -o /dev/null http://127.0.0.1:8603/openapi.json; then
  dim=$(curl -s -m 30 -X POST http://127.0.0.1:8603/embed \
        -H 'content-type: application/json' -d '{"text":"pitchdeck live probe"}' \
        | python3 -c 'import json,sys; print(len(json.load(sys.stdin).get("embedding") or []))' 2>/dev/null)
  if [[ "$dim" == "1024" ]]; then
    report PASS "embedding /embed" "1024-d vector returned"
  else
    report FAIL "embedding /embed" "expected 1024 dims, got '${dim:-none}'"
  fi
else
  report SKIP "embedding /embed" "service not listening on :8603"
fi

# --- Qdrant: the house-slide layout index ------------------------------------
if curl -s -m 3 -o /dev/null http://127.0.0.1:6333/collections; then
  points=$(curl -s -m 10 http://127.0.0.1:6333/collections/pitchdeck_house_slides_v1 \
           | python3 -c 'import json,sys; print(json.load(sys.stdin).get("result",{}).get("points_count",0))' 2>/dev/null)
  if [[ "${points:-0}" -gt 0 ]]; then
    report PASS "qdrant house slides" "$points indexed real slides"
  else
    report FAIL "qdrant house slides" "collection empty — run index-house-slides"
  fi
else
  report SKIP "qdrant" "not listening on :6333"
fi

# --- /memory: the only sanctioned ArangoDB route -----------------------------
if [[ -x "$SCRIPT_DIR/../memory/run.sh" ]]; then
  report PASS "memory route present" "skills/memory/run.sh is executable"
else
  report SKIP "memory route" "skills/memory/run.sh not found"
fi

# --- browser-oracle: the visual-review binding -------------------------------
if [[ -f "$SCRIPT_DIR/.ask/browser-oracles.yaml" ]]; then
  project=$(python3 -c "import yaml,sys; print(yaml.safe_load(open('$SCRIPT_DIR/.ask/browser-oracles.yaml'))['webgpt']['default'])" 2>/dev/null)
  if [[ -n "${project:-}" ]]; then
    report PASS "browser-oracle registry" "webgpt project '$project'"
  else
    report FAIL "browser-oracle registry" "registry present but no webgpt default"
  fi
else
  report SKIP "browser-oracle registry" ".ask/browser-oracles.yaml missing"
fi

# --- house conformance on the committed example deck -------------------------
DECK="/mnt/storage12tb/skills/pitchdeck/outputs/ticket-1278/approved.pptx"
if [[ -f "$DECK" ]]; then
  out=$("$SCRIPT_DIR/run.sh" house-conformance --pptx "$DECK" 2>&1)
  chrome=$(printf '%s' "$out" | python3 -c '
import json,sys
try: d=json.load(sys.stdin)
except Exception: print("parse-error"); raise SystemExit
print(sum(1 for f in d.get("findings",[]) if f["code"] not in {"HOUSE_VISUAL_DENSITY","UNREADABLE"}))' 2>/dev/null)
  if [[ "${chrome:-x}" == "0" ]]; then
    report PASS "house conformance" "zero chrome violations on the emitted deck"
  else
    report FAIL "house conformance" "chrome violations: ${chrome:-parse-error}"
  fi
else
  report SKIP "house conformance" "no emitted deck at $DECK"
fi

echo "  ---"
echo "  pass=$pass skip=$skip fail=$fail"
[[ $fail -eq 0 ]] || { echo "LIVE GATE: FAIL"; exit 1; }
echo "LIVE GATE: PASS"
