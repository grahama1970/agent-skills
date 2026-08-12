#!/usr/bin/env bash
set -euo pipefail
unset VIRTUAL_ENV

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

prepare_python_environment() {
  if ! command -v uv >/dev/null 2>&1; then
    echo "uv is required for Live Evidence." >&2
    return 2
  fi
  if [[ -z "${UV_PROJECT_ENVIRONMENT:-}" ]]; then
    if [[ -d /mnt/storage12tb/skills && -w /mnt/storage12tb/skills ]]; then
      export UV_PROJECT_ENVIRONMENT="/mnt/storage12tb/skills/live-evidence/.venv"
    else
      export UV_PROJECT_ENVIRONMENT="${XDG_CACHE_HOME:-$HOME/.cache}/live-evidence/venv"
    fi
  fi
  export UV_LINK_MODE="${UV_LINK_MODE:-copy}"
  mkdir -p "$(dirname "$UV_PROJECT_ENVIRONMENT")"
}

prepare_ui_modules() {
  if ! command -v npm >/dev/null 2>&1; then
    echo "npm is required for the React UI." >&2
    return 2
  fi

  local target="${LIVE_EVIDENCE_UI_NODE_MODULES:-}"
  if [[ -z "$target" ]]; then
    if [[ -d /mnt/storage12tb/skills && -w /mnt/storage12tb/skills ]]; then
      target="/mnt/storage12tb/skills/live-evidence/ui-runtime/node_modules"
    else
      target="${XDG_CACHE_HOME:-$HOME/.cache}/live-evidence/ui-runtime/node_modules"
    fi
  fi
  mkdir -p "$(dirname "$target")"

  local link="$SCRIPT_DIR/ui/node_modules"
  if [[ -L "$link" ]]; then
    local current
    current="$(readlink -f "$link")"
    if [[ "$current" != "$(readlink -f "$target")" ]]; then
      rm "$link"
      ln -s "$target" "$link"
    fi
  elif [[ -e "$link" ]]; then
    echo "Refusing repository-local ui/node_modules. Move it outside the code tree and retry." >&2
    return 2
  else
    ln -s "$target" "$link"
  fi
}

install_ui_modules() {
  prepare_ui_modules
  if [[ -x "$SCRIPT_DIR/ui/node_modules/.bin/tsc" && -x "$SCRIPT_DIR/ui/node_modules/.bin/vite" ]]; then
    return 0
  fi
  local target
  target="$(readlink -f "$SCRIPT_DIR/ui/node_modules")"
  local runtime_root
  runtime_root="$(dirname "$target")"
  cp "$SCRIPT_DIR/ui/package.json" "$runtime_root/package.json"
  if [[ -f "$SCRIPT_DIR/ui/package-lock.json" ]]; then
    cp "$SCRIPT_DIR/ui/package-lock.json" "$runtime_root/package-lock.json"
    npm --prefix "$runtime_root" ci --no-audit --no-fund
  else
    npm --prefix "$runtime_root" install --no-audit --no-fund
  fi
}

command_name="${1:-help}"

case "$command_name" in
  setup)
    shift || true
    with_stt="false"
    if [[ "${1:-}" == "--with-stt" ]]; then
      with_stt="true"
      shift
    fi
    prepare_python_environment
    uv sync --project "$SCRIPT_DIR" --extra dev
    if [[ "$with_stt" == "true" ]]; then
      uv pip install \
        --python "$UV_PROJECT_ENVIRONMENT/bin/python" \
        "RealtimeSTT[faster-whisper] @ git+https://github.com/grahama1970/RealtimeSTT.git@cbdbd12a8f573a92d7ffd14cfbd82baa59a59849"
    fi
    install_ui_modules
    echo "Live Evidence dependencies installed outside the code volume."
    exit 0
    ;;
  ui-build)
    shift || true
    install_ui_modules
    exec npm --prefix "$SCRIPT_DIR/ui" run build "$@"
    ;;
  ui-dev)
    shift || true
    install_ui_modules
    exec npm --prefix "$SCRIPT_DIR/ui" run dev -- "$@"
    ;;
  verify)
    shift || true
    exec "$SCRIPT_DIR/sanity.sh" "$@"
    ;;
  eval-adversarial)
    shift || true
    prepare_python_environment
    exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/eval_adversarial.py" "$SCRIPT_DIR" "$@"
    ;;
esac

if [[ $# -eq 0 ]]; then
  set -- --help
fi

prepare_python_environment
exec uv run --project "$SCRIPT_DIR" python -m live_evidence "$@"
