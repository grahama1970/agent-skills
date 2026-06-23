#!/usr/bin/env bash
set -euo pipefail
unset VIRTUAL_ENV

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

load_zshrc_secret() {
  local name="$1"
  if [[ -n "${!name:-}" ]]; then
    return 0
  fi
  if [[ ! -f "$HOME/.zshrc" ]] || ! command -v zsh >/dev/null 2>&1; then
    return 0
  fi
  local value
  value="$(zsh -ic "print -r -- \${${name}:-}" 2>/dev/null | tail -n 1 || true)"
  if [[ -n "$value" ]]; then
    export "$name=$value"
  fi
}

load_zshrc_secret HF_TOKEN
load_zshrc_secret HUGGINGFACE_HUB_TOKEN
load_zshrc_secret BRAVE_API_KEY
load_zshrc_secret BRAVE_SEARCH_API_KEY
load_zshrc_secret BRAVE_API_KEY_PAID
load_zshrc_secret BRAVE_SEARCH_API_KEY_PAID
if [[ -n "${HF_TOKEN:-}" && -z "${HUGGINGFACE_HUB_TOKEN:-}" ]]; then
  export HUGGINGFACE_HUB_TOKEN="$HF_TOKEN"
fi
if [[ -n "${HUGGINGFACE_HUB_TOKEN:-}" && -z "${HF_TOKEN:-}" ]]; then
  export HF_TOKEN="$HUGGINGFACE_HUB_TOKEN"
fi

usage() {
  cat <<'USAGE'
personaplex

Usage:
  ./run.sh validate-pack --reference-pack PACK.json
  ./run.sh pack-from-receipt --receipt INFERENCE_RECEIPT.json --out PACK.json [--persona horus] [--register neutral]
  ./run.sh from-orpheus --reference-pack PACK.json --personaplex-root DIR --human-input-wav WAV [--out-dir DIR]
  ./run.sh verify-e2e --reference-pack PACK.json --personaplex-root DIR --human-input-wav WAV [--out-dir DIR]
  ./run.sh render-review --receipt RECEIPT.json [--out-html index.html]
  ./run.sh research-gate-sanity --transcript "..." [--persona embry] [--out-dir DIR]

Heavy artifacts are written under /mnt/storage12tb/skills/personaplex by default.
USAGE
}

if [[ $# -eq 0 ]]; then
  usage >&2
  exit 2
fi

cmd="${1:-}"
shift

case "$cmd" in
  validate-pack|pack-from-receipt|from-orpheus|verify-e2e|render-review|research-gate-sanity)
    exec uv run --directory "$SCRIPT_DIR" python scripts/personaplex_cli.py "$cmd" "$@"
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    usage >&2
    exit 2
    ;;
esac
