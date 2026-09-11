#!/bin/bash
# ops-recruiter sanity: status shape, claim-bind gate rejects unbacked facts, boundaries present.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
fail=0

echo "[1] status --json emits contract + forbidden effects"
out=$(./run.sh status --json)
echo "$out" | grep -q '"email_send": "PERMANENTLY_FORBIDDEN"' || { echo "  FAIL: email_send not forbidden"; fail=1; }
echo "$out" | grep -q '"linkedin_automation": "PERMANENTLY_FORBIDDEN"' || { echo "  FAIL: linkedin not forbidden"; fail=1; }
echo "$out" | grep -q 'COMPOSED_VIA_ASK' || { echo "  FAIL: draft/humanize not composed via ask"; fail=1; }

echo "[2] gate PASSES a backed draft"
tmp=$(mktemp -d)
printf 'Graham led ARCOS with 430 commits.\n' > "$tmp/draft.md"
printf 'ARCOS technical lead. 430 commits on pdf_oxide.\n' > "$tmp/claims.md"
./run.sh gate --draft "$tmp/draft.md" --claims "$tmp/claims.md" | grep -q '"verdict": "PASS"' \
  || { echo "  FAIL: backed draft did not pass"; fail=1; }

echo "[3] gate REJECTS an unbacked metric (fail-closed)"
printf 'Graham delivered 999 projects at 5000%% ROI.\n' > "$tmp/bad.md"
if ./run.sh gate --draft "$tmp/bad.md" --claims "$tmp/claims.md" 2>/dev/null; then
  echo "  FAIL: unbacked metric was not rejected"; fail=1
else
  echo "  ok: unbacked metric rejected"
fi

echo "[4] build emits a relationship flag (no false first-contact)"
printf 'hi again\n' > "$tmp/msg.md"; printf 'role\n' > "$tmp/role.md"; printf 'ARCOS lead.\n' > "$tmp/res.md"
./run.sh build --recruiter-message "$tmp/msg.md" --role "$tmp/role.md" --resume "$tmp/res.md" \
  --recruiter jane --thread-id t1 --out "$tmp/o" 2>/dev/null | grep -qE '"relationship": "(existing|new|unknown)"' \
  || { echo "  FAIL: no relationship flag in build output"; fail=1; }
grep -q '## Relationship:' "$tmp/o/context-packet.md" || { echo "  FAIL: packet missing relationship section"; fail=1; }

rm -rf "$tmp"
[ "$fail" -eq 0 ] && echo "SANITY: PASS" || { echo "SANITY: FAIL"; exit 1; }
