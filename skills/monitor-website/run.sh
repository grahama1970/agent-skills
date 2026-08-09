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

# `design-world-check` validates site/design-world.yml (the bespoke visual-world
# contract, #1337) and scans for deterministic AI-template residue. Returns
# NOT_TESTED, never PASS, while rendered/blind evidence is absent.
if [[ "${1:-}" == "design-world-check" ]]; then
  shift
  exec python3 scripts/design_world_check.py "$@"
fi

# `copy-audit` enforces the first-person human-voice contract (#1298):
# site/VOICE.md + site/voice-anchors.yml. Report-only, deterministic at a commit.
if [[ "${1:-}" == "copy-audit" ]]; then
  shift
  exec python3 ../../site/scripts/copy_audit.py "$@"
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

exec python3 scripts/monitor_website.py "$@"
