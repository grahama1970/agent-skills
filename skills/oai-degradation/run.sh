#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cmd="${1:-protocol}"
shift || true
case "$cmd" in
  protocol)
    awk 'BEGIN{p=0} /^## Immediate response/{p=1} /^## Recovery closeout/{print; p=1} p{print}' "$ROOT/SKILL.md"
    ;;
  check-skill)
    python3 "$ROOT/scripts/check_contract.py" --skill "$ROOT/SKILL.md"
    ;;
  check-answer)
    python3 "$ROOT/scripts/check_contract.py" --answer "${1:--}"
    ;;
  sanity)
    "$ROOT/sanity.sh"
    ;;
  help|--help|-h)
    cat <<'EOF'
Usage: skills/oai-degradation/run.sh <command>

Commands:
  protocol              Print the degraded-model procedure.
  check-skill           Verify SKILL.md contains the required procedure gates.
  check-answer [file|-] Verify a degraded-session status answer uses the required table and switch policy.
  sanity                Run local contract checks.
EOF
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    exit 2
    ;;
esac
