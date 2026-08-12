#!/usr/bin/env bash
# The NORTH-STAR eval: sparta-public README -> claim-bound deck -> every gate ->
# looks-like-a-Graham-deck. One command, one honest per-stage report.
#
# This is the skill's actual goal, so the eval is allowed to FAIL — a goal eval
# that always passes is measuring something else. Exit 0 only when every stage
# including house-similarity passes. Current known state: the house gate fails
# on density and drawn art (recorded in STYLE_GUIDE.md §7); this script is the
# scoreboard for closing that gap, not a demo.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"
export SPARTA_ROOT="${SPARTA_ROOT:-$HOME/workspace/experiments/sparta}"
export SPARTA_PUBLIC_ROOT="${SPARTA_PUBLIC_ROOT:-/mnt/storage12tb/skills/pitchdeck/sources/sparta-public}"

WORK="${1:-$(mktemp -d /tmp/pitchdeck-e2e-XXXXXX)}"
mkdir -p "$WORK"
O=/mnt/storage12tb/skills/pitchdeck/outputs/ticket-1278
HT=/mnt/storage12tb/skills/pitchdeck/sources/style-corpus/SpartaAI_CyberSummitv_v3.pptx
BUNDLE=examples/sparta-explorer
pass=0; fail=0
stage() { # stage <name> <cmd...>
  local name="$1"; shift
  if "$@" >"$WORK/$name.log" 2>&1; then
    echo "  PASS  $name"; pass=$((pass+1))
  else
    echo "  FAIL  $name  (log: $WORK/$name.log)"; fail=$((fail+1))
  fi
}

echo "north-star eval: README -> deck -> Graham gate   (work: $WORK)"
echo "--- stage 1: source is the real sparta-public README ---"
stage readme-present test -s "$SPARTA_PUBLIC_ROOT/README.md"

echo "--- stage 2: claim-bound compilation (target: 15-20 slides) ---"
stage materialize ./run.sh materialize-outline --outline "$O/approved_outline.json" \
  --context /tmp/claude-1000/-home-graham-workspace-experiments-agent-skills/c97e92ee-f998-42c3-8cea-10d08775cc68/scratchpad/deck_context.json \
  --bundle-dir "$BUNDLE" --output "$WORK/deck.document.json"
stage design-lint ./run.sh design-lint --document "$WORK/deck.document.json"
stage slide-count python3 -c "
import json,sys
n=len([s for s in json.load(open('$WORK/deck.document.json'))['slides'] if not s.get('hidden')])
print(f'slides: {n} (target 15-20)')
sys.exit(0 if 15 <= n <= 20 else 1)"
stage coverage python3 -c "
import json,sys
d=json.load(open('$WORK/deck.document.json'))
bound={b['claim_id'] for s in d['slides'] for b in s.get('bindings',[]) if b.get('claim_id')}
import yaml
claims=[c['id'] for c in yaml.safe_load(open('examples/sparta-explorer/claim_ledger.yaml'))['claims'] if c['id'].startswith('sparta-public')]
missing=[c for c in claims if c not in bound]
print(f'public claims represented: {len(claims)-len(missing)}/{len(claims)}; missing: {missing}')
sys.exit(0 if len(missing) <= 2 else 1)"

echo "--- stage 3: emission on the house template ---"
stage emit-pptx ./run.sh emit-document-pptx --document "$WORK/deck.document.json" \
  --output "$WORK/deck.pptx" --asset-base "$BUNDLE" --house-template "$HT" \
  --disclaimer-owner grahama.co --disclaimer-approved-by "graham (chat approval 2026-08-08)" --brandmark

echo "--- stage 4: chain + publication verification ---"
stage build-manifest ./run.sh build-manifest --bundle-dir "$BUNDLE" \
  --document "$WORK/deck.document.json" --outline "$O/approved_outline.json" \
  --pptx "$WORK/deck.pptx" --house-template "$HT" --output "$WORK/manifest.json"
stage verify-publish ./run.sh verify-publish --pptx "$WORK/deck.pptx" \
  --ledger "$BUNDLE/claim_ledger.yaml" \
  --approvals /tmp/claude-1000/-home-graham-workspace-experiments-agent-skills/c97e92ee-f998-42c3-8cea-10d08775cc68/scratchpad/publish-approvals-attested.json \
  --document "$WORK/deck.document.json" \
  --build-manifest "$WORK/manifest.json" --bundle-dir "$BUNDLE"
stage house-conformance ./run.sh house-conformance --pptx "$WORK/deck.pptx"
stage house-structure ./run.sh house-structure --pptx "$WORK/deck.pptx" --document "$WORK/deck.document.json"
stage house-deck-gate ./run.sh house-deck-gate --pptx "$WORK/deck.pptx"

echo "--- stage 5: render ---"
mkdir -p "$WORK/render"
stage render-pdf soffice "-env:UserInstallation=file://$WORK/.lo" --headless \
  --convert-to pdf "$WORK/deck.pptx" --outdir "$WORK/render"
if [ -f "$WORK/render/deck.pdf" ]; then
  NPAGES=$(pdfinfo "$WORK/render/deck.pdf" 2>/dev/null | awk '/^Pages:/{print $2}'); NPAGES=${NPAGES:-6}
  for p in $(seq 1 "$NPAGES"); do pdftoppm -png -r 50 -f $p -l $p "$WORK/render/deck.pdf" "$WORK/render/s$p" >/dev/null 2>&1; done
  python3 - "$WORK" <<'PYEOF'
import hashlib, json, sys
from pathlib import Path
work = Path(sys.argv[1])
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
receipt = {
    "schema": "pitchdeck.render_receipt.v1",
    "pptx_sha256": sha(work / "deck.pptx"),
    "pdf_sha256": sha(work / "render" / "deck.pdf"),
    "dpi": 50,
    "pages": [{"file": p.name, "sha256": sha(p)} for p in sorted((work / "render").glob("s*.png"))],
}
(work / "render-receipt.json").write_text(json.dumps(receipt, indent=1))
PYEOF
fi

echo "--- stage 6: house gate (HOUSE_NON_ANOMALOUS semantics) ---"
stage house-similarity ./run.sh house-similarity --slides-dir "$WORK/render" --glob "s*.png" \
  --calibration fixtures/house-gate/calibration.v1.json \
  --render-receipt "$WORK/render-receipt.json" --pptx "$WORK/deck.pptx" \
  --document "$WORK/deck.document.json"

echo "---"
echo "stages: $pass pass, $fail fail"
if [ $fail -eq 0 ]; then echo "NORTH-STAR: PASS — HOUSE_NON_ANOMALOUS: every gate cleared; this is an anomaly filter, NOT a validated looks-like-Graham classifier (webgpt review 2026-08-11, reports/webgpt-house-gate-review-2026-08-11.md)"; exit 0; fi
echo "NORTH-STAR: NOT YET — see failing stage logs; the gap is the scoreboard"
exit 1
