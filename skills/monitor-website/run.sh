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

exec python3 scripts/monitor_website.py "$@"
