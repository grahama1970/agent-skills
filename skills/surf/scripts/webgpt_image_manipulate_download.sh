#!/usr/bin/env bash
# Live runner: /ask webgpt image-reference manipulation with download.
# Attaches a reference image, asks WebGPT to manipulate it (do X), and
# auto-downloads the produced image. Prints marker lines the agentic-eval
# fixture asserts on. Exit 0 iff a manipulated image file was downloaded.
#
# Usage: webgpt_image_manipulate_download.sh <reference.png> <tab-id> "<manipulation instruction>"
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REF="${1:-}"; TAB="${2:-}"; INSTRUCTION="${3:-replace the red square with a solid blue circle of similar size, centered}"
[ -z "$REF" ] || [ -z "$TAB" ] && { echo "usage: $0 <reference.png> <tab-id> [instruction]" >&2; exit 2; }
[ -f "$REF" ] || { echo "reference image not found: $REF" >&2; exit 2; }

tmp="$(mktemp -d)"
dl_dir="$tmp/downloads"; mkdir -p "$dl_dir"
cat > "$tmp/prompt.md" <<EOF
Using the attached image strictly as a visual reference, create a NEW image on
the same 512x512 canvas where you $INSTRUCTION. Generate the image and provide
it as a downloadable PNG.
EOF

before=$(find "$dl_dir" -name '*.png' 2>/dev/null | wc -l)
SURF_DOWNLOAD_DIR="$dl_dir" timeout 540 "$SKILL_DIR/run.sh" webgpt.submit \
  --input "$tmp/prompt.md" --attach-file "$REF" \
  --output "$tmp/out.md" --raw-output "$tmp/raw.md" --meta-output "$tmp/meta.json" \
  --auto-download "png|image|Download|download" \
  --tab-id "$TAB" --no-activate >/dev/null 2>"$tmp/err.txt" || true

python3 - "$tmp/meta.json" "$dl_dir" "$REF" <<'PY'
import json, sys, glob, os
meta_path, dl_dir, ref = sys.argv[1:]
m = {}
try:
    m = json.load(open(meta_path))
except Exception:
    pass
print(f"ATTACHMENT_DELIVERY:{m.get('attachment_delivery_proven')}")
print(f"PROOF_STATUS:{m.get('proof_status')}")
pngs = sorted(glob.glob(os.path.join(dl_dir, "*.png")), key=os.path.getmtime)
# also honor a downloaded_files list in meta if present
for f in (m.get("downloaded_files") or m.get("downloads") or []):
    if isinstance(f, str) and f.endswith(".png") and os.path.isfile(f):
        pngs.append(f)
downloaded = [p for p in pngs if os.path.getsize(p) > 1000 and os.path.abspath(p) != os.path.abspath(ref)]
if downloaded:
    newest = downloaded[-1]
    print(f"DOWNLOADED_IMAGE:{newest} ({os.path.getsize(newest)} bytes)")
    print("IMAGE_MANIPULATE_DOWNLOAD_PASS")
    sys.exit(0)
print(f"NO_IMAGE_DOWNLOADED (proof_status={m.get('proof_status')}, failure={m.get('failure')})")
sys.exit(1)
PY
