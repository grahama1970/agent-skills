#!/bin/bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_DIR="$(mktemp -d)"
trap 'rm -rf "$TEST_DIR"' EXIT

printf '1. dependency check... '
"$SKILL_DIR/run.sh" check >/dev/null
printf 'PASS\n'

cat > "$TEST_DIR/icon.svg" <<'SVG'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" fill="white">
  <rect x="6" y="6" width="20" height="14" rx="4" />
  <rect x="10" y="10" width="12" height="2" rx="1" fill="black" />
  <rect x="10" y="14" width="8" height="2" rx="1" fill="black" />
</svg>
SVG
magick "$TEST_DIR/icon.svg" "$TEST_DIR/icon.png"

printf '2. fill conversion... '
"$SKILL_DIR/run.sh" convert "$TEST_DIR/icon.png" --output "$TEST_DIR/icon-fill.svg" >/dev/null
rg -q 'currentColor' "$TEST_DIR/icon-fill.svg"
printf 'PASS\n'

printf '3. stroke conversion... '
"$SKILL_DIR/run.sh" convert "$TEST_DIR/icon.png" --output "$TEST_DIR/icon-stroke.svg" --mode stroke --stroke-width 1.25 >/dev/null
rg -q 'stroke-width="1.25"' "$TEST_DIR/icon-stroke.svg"
printf 'PASS\n'

printf '4. help text... '
"$SKILL_DIR/run.sh" --help | rg -q 'png-svg-converter'
printf 'PASS\n'
