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

exec python3 scripts/monitor_website.py "$@"
