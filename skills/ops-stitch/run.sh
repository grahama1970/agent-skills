#!/usr/bin/env bash
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MONO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Load .env for STITCH_API_KEY
if [[ -f "$MONO_ROOT/.env" ]]; then
  set -a; source "$MONO_ROOT/.env"; set +a
fi

CMD="${1:-help}"

case "$CMD" in
  # Python bundler commands (screenshot + DESIGN.md + refs)
  bundle|list-bundles)
    uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/bundle.py" "$@"
    ;;
  # Node.js Stitch SDK commands
  list-projects|get-project|generate|edit|variants|download|stitch-bundle)
    # Remap stitch-bundle → bundle for the TS side
    if [[ "$CMD" == "stitch-bundle" ]]; then
      shift; set -- "bundle" "$@"
    fi
    npx --prefix "$MONO_ROOT" tsx "$SCRIPT_DIR/stitch.ts" "$@"
    ;;
  help|--help|-h)
    echo "ops-stitch: Design context bundling + Stitch SDK integration"
    echo ""
    echo "Python commands (local bundling):"
    echo "  bundle          Bundle screenshots + DESIGN.md + refs for manual upload"
    echo "  list-bundles    List previous bundles"
    echo ""
    echo "Stitch SDK commands (requires STITCH_API_KEY):"
    echo "  list-projects   List all Stitch projects"
    echo "  get-project     Get screens from a project"
    echo "  generate        Generate a new screen from prompt"
    echo "  edit            Edit an existing screen"
    echo "  variants        Generate variants of a screen"
    echo "  download        Download all screens from a project"
    echo "  stitch-bundle   Generate via Stitch + bundle for integration"
    ;;
  *)
    echo "Unknown command: $CMD" >&2
    "$0" help
    exit 1
    ;;
esac
