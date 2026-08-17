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
    # Local cache first. This previously preferred /mnt/storage12tb whenever it
    # was writable, which put the runtime venv on /dev/sda1 (rotational=1, 87%
    # full) while /dev/nvme0n1p2 (rotational=0) had 1.2T free. Every interpreter
    # start and per-question runner spawn paid seek latency on a spinning disk
    # for a latency-critical live app. Set UV_PROJECT_ENVIRONMENT explicitly to
    # override.
    export UV_PROJECT_ENVIRONMENT="${XDG_CACHE_HOME:-$HOME/.cache}/live-evidence/venv"
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
    if [[ "$with_stt" == "true" ]]; then
      uv sync --project "$SCRIPT_DIR" --extra dev --extra stt
    else
      uv sync --project "$SCRIPT_DIR" --extra dev
    fi
    if [[ "$with_stt" == "true" ]]; then
      uv run --project "$SCRIPT_DIR" --extra stt python - <<'PY'
import RealtimeSTT
print(f"RealtimeSTT import: PASS ({RealtimeSTT.__file__})")
PY
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
  doctor)
    shift || true
    prepare_python_environment
    exec uv run --project "$SCRIPT_DIR" --extra dev --extra stt python -m live_evidence doctor "$@"
    ;;
  listen)
    shift || true
    consent_seen="false"
    for arg in "$@"; do
      if [[ "$arg" == "--consent-confirmed" ]]; then
        consent_seen="true"
        break
      fi
    done
    if [[ "$consent_seen" != "true" ]]; then
      echo "Invalid value: live modes require --consent-confirmed" >&2
      exit 2
    fi
    prepare_python_environment
    exec uv run --project "$SCRIPT_DIR" --extra dev --extra stt python -m live_evidence listen "$@"
    ;;
  eval-adversarial)
    shift || true
    prepare_python_environment
    exec uv run --project "$SCRIPT_DIR" --extra dev python "$SCRIPT_DIR/scripts/eval_adversarial.py" "$SCRIPT_DIR" "$@"
    ;;
  eval-interview-loop)
    shift || true
    prepare_python_environment
    exec uv run --project "$SCRIPT_DIR" --extra dev --extra stt python "$SCRIPT_DIR/scripts/eval_interview_loop.py" "$SCRIPT_DIR" "$@"
    ;;
  eval-youtube-interview)
    shift || true
    prepare_python_environment
    exec uv run --project "$SCRIPT_DIR" --extra dev --extra stt python "$SCRIPT_DIR/scripts/eval_youtube_interview.py" "$SCRIPT_DIR" "$@"
    ;;
  eval-ui-surf-controls)
    shift || true
    prepare_python_environment
    exec uv run --project "$SCRIPT_DIR" --extra dev --extra stt python "$SCRIPT_DIR/scripts/eval_ui_surf_controls.py" "$SCRIPT_DIR" "$@"
    ;;
  eval-real-stt-window)
    shift || true
    prepare_python_environment
    exec uv run --project "$SCRIPT_DIR" --extra dev --extra stt python "$SCRIPT_DIR/scripts/eval_real_stt_window.py" "$SCRIPT_DIR" "$@"
    ;;
  eval-live-youtube-oracle)
    shift || true
    prepare_python_environment
    exec uv run --project "$SCRIPT_DIR" --extra dev python "$SCRIPT_DIR/scripts/eval_live_youtube_oracle.py" "$SCRIPT_DIR" "$@"
    ;;
  eval-mvp-steps-2-8)
    shift || true
    prepare_python_environment
    exec uv run --project "$SCRIPT_DIR" --extra dev python "$SCRIPT_DIR/scripts/eval_mvp_steps_2_8.py" "$SCRIPT_DIR" "$@"
    ;;
  eval-two-stage-prompt-contract)
    shift || true
    prepare_python_environment
    exec uv run --project "$SCRIPT_DIR" --extra dev python "$SCRIPT_DIR/scripts/eval_two_stage_prompt_contract.py" "$SCRIPT_DIR" "$@"
    ;;
  eval-leetcode-memory-recall)
    shift || true
    prepare_python_environment
    exec uv run --project "$SCRIPT_DIR" --extra dev python "$SCRIPT_DIR/scripts/eval_leetcode_memory_recall.py" "$SCRIPT_DIR" "$@"
    ;;
  eval-leetcode-public-corpus)
    shift || true
    prepare_python_environment
    exec uv run --project "$SCRIPT_DIR" --extra dev python "$SCRIPT_DIR/scripts/eval_leetcode_public_corpus.py" "$SCRIPT_DIR" "$@"
    ;;
  ingest-leetcode-public-repos)
    shift || true
    prepare_python_environment
    exec uv run --project "$SCRIPT_DIR" --extra dev python "$SCRIPT_DIR/scripts/ingest_leetcode_public_repos.py" "$@"
    ;;
esac

if [[ $# -eq 0 ]]; then
  set -- --help
fi

prepare_python_environment
exec uv run --project "$SCRIPT_DIR" python -m live_evidence "$@"
