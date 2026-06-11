#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cmd="${1:-}"
if [[ -z "$cmd" || "$cmd" == "--help" || "$cmd" == "-h" ]]; then
  cat <<'EOF'
Usage:
  ./run.sh create-asset-pack --root ./packs --type character --name Maya_Ren --version 1
  ./run.sh validate-asset-pack ./packs/CHAR_Maya_Ren_v01
  ./run.sh sanity
EOF
  exit 0
fi
shift || true

case "$cmd" in
  create-asset-pack)
    python3 "$ROOT/scripts/create_asset_pack.py" "$@"
    ;;
  validate-asset-pack)
    python3 "$ROOT/scripts/validate_asset_pack.py" "$@"
    ;;
  sanity)
    "$ROOT/sanity.sh" "$@"
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    exit 2
    ;;
esac
