#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# `memory` subcommands manage the site's authored content in /memory (ArangoDB):
#   memory push     content.json -> /memory (versioned; new revision on change)
#   memory pull     /memory -> content.json (authored projects; stats preserved)
#   memory history  in-memory revision history (--slug <slug> to scope)
if [[ "${1:-}" == "memory" ]]; then
  shift
  exec python3 scripts/site_memory.py "$@"
fi

# `design-render-check` is the fast deterministic lane for local design work:
# contract + source lock + typography boundary + rendered responsive/craft
# receipts. It deliberately excludes the formal blind-rater G11 gate.
if [[ "${1:-}" == "design-render-check" ]]; then
  shift
  exec python3 scripts/design_world_check.py --mode render "$@"
fi

# `design-certify` is the formal bespoke-design certification lane. It includes
# the blind-rater G11 gate and exits nonzero unless every gate is PASS.
if [[ "${1:-}" == "design-certify" ]]; then
  shift
  exec python3 scripts/design_world_check.py --mode certify --require-ready "$@"
fi

# Compatibility alias for the original formal gate. Prefer design-render-check
# while iterating and design-certify only for formal release certification.
if [[ "${1:-}" == "design-world-check" ]]; then
  shift
  >&2 echo "monitor-website: design-world-check is a compatibility alias; use design-render-check for deterministic local render health or design-certify for formal READY."
  exec python3 scripts/design_world_check.py "$@"
fi

# `copy-audit` enforces the first-person human-voice contract (#1298):
# site/VOICE.md + site/voice-anchors.yml. Report-only, deterministic at a commit.
if [[ "${1:-}" == "copy-audit" ]]; then
  shift
  exec python3 ../../site/scripts/copy_audit.py "$@"
fi

# `review-site` freezes section/page-state crops into immutable review bundles
# and serves nonce-gated loopback capability URLs for external design review.
if [[ "${1:-}" == "review-site" ]]; then
  shift
  exec python3 scripts/review_site.py "$@"
fi

# `visual-assets-check` validates site/visual-assets.yml against public image
# files and rejects generated media used as evidence, missing provenance,
# digest drift, private assets, and simulated craft.
if [[ "${1:-}" == "visual-assets-check" ]]; then
  shift
  exec python3 scripts/visual_assets_check.py "$@"
fi

# `case-composition-check` validates the three flagship case compositions and
# rejects shared project-card geometry, generated evidence, missing artifacts,
# and missing proof boundaries.
if [[ "${1:-}" == "case-composition-check" ]]; then
  shift
  exec python3 scripts/case_composition_check.py "$@"
fi

# `effects-check` validates the semantic effects registry and rejects public
# homepage ambient layers, load choreography, decorative path drawing, and
# animation of captured evidence values.
if [[ "${1:-}" == "effects-check" ]]; then
  shift
  exec python3 scripts/effects_check.py "$@"
fi

# `responsive-geometry-check` runs the required bespoke-design viewport matrix
# against the static site and rejects horizontal document overflow.
if [[ "${1:-}" == "responsive-geometry-check" ]]; then
  shift
  cd ../../site
  exec node ../skills/monitor-website/scripts/responsive_geometry_check.mjs "$@"
fi

exec python3 scripts/monitor_website.py "$@"
