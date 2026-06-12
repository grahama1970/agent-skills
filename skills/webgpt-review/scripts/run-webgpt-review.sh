#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT_DIR="$(cd "${SKILL_DIR}/../.." && pwd)"
ASK_RUN="${ROOT_DIR}/skills/ask/run.sh"
SURF_RUN="${ROOT_DIR}/skills/surf/run.sh"

usage() {
  cat <<'EOF'
Usage:
  run-webgpt-review.sh --bundle FILE --review-type code|design|prompt|plan [target] [options]

Targets:
  --project NAME
  --tab-id ID --url URL
  --url URL
  --create-tab

Options:
  --ask-id ID
  --timeout SECONDS
  --output-root DIR
  --instructions TEXT
  --json
  --preflight-only
  --allow-foreground-controlled
  --no-extension-refresh
EOF
}

bundle=""
review_type="code"
project=""
tab_id=""
url=""
create_tab=0
ask_id=""
timeout_s="900"
output_root=""
instructions=""
json_flag=0
refresh_extension=1
allow_foreground=0
preflight_only=0

case "${ASK_WEBGPT_ALLOW_FOREGROUND:-}" in
  1|true|TRUE|yes|YES|on|ON) allow_foreground=1 ;;
esac

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bundle) bundle="${2:-}"; shift 2 ;;
    --review-type) review_type="${2:-}"; shift 2 ;;
    --project) project="${2:-}"; shift 2 ;;
    --tab-id) tab_id="${2:-}"; shift 2 ;;
    --url) url="${2:-}"; shift 2 ;;
    --create-tab) create_tab=1; shift ;;
    --ask-id) ask_id="${2:-}"; shift 2 ;;
    --timeout) timeout_s="${2:-}"; shift 2 ;;
    --output-root) output_root="${2:-}"; shift 2 ;;
    --instructions) instructions="${2:-}"; shift 2 ;;
    --json) json_flag=1; shift ;;
    --preflight-only) preflight_only=1; shift ;;
    --allow-foreground-controlled) allow_foreground=1; shift ;;
    --no-extension-refresh) refresh_extension=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$bundle" ]]; then
  if [[ "$preflight_only" -eq 0 ]]; then
    usage >&2
    exit 2
  fi
else
  if [[ ! -f "$bundle" ]]; then
    echo "Bundle must be one readable file, not a directory or missing path: $bundle" >&2
    exit 2
  fi

  case "$bundle" in
    /*) ;;
    *) bundle="$(readlink -f "$bundle")" ;;
  esac
fi

case "$review_type" in
  code|design|prompt|plan) ;;
  *) echo "--review-type must be code, design, prompt, or plan" >&2; exit 2 ;;
esac

if [[ -z "$project" && -z "$tab_id" && -z "$url" && "$create_tab" -eq 0 ]]; then
  echo "Pass --project, --tab-id/--url, --url, or --create-tab." >&2
  exit 2
fi

if [[ "$refresh_extension" -eq 1 ]]; then
  "$SURF_RUN" extension.fresh --json >/tmp/webgpt-review-extension-fresh.json 2>/dev/null || true
fi

if [[ -n "$tab_id" || -n "$url" ]]; then
  preflight=("$SURF_RUN" webgpt.preflight --json)
  if [[ -n "$tab_id" ]]; then
    preflight+=(--tab-id "$tab_id")
    if [[ -n "$url" ]]; then
      preflight+=(--expect-url "$url")
    fi
  else
    preflight+=(--url "$url")
  fi
  preflight+=(--no-activate)
  if [[ "$allow_foreground" -eq 1 ]]; then
    preflight+=(--allow-foreground-controlled)
  fi
  if ! "${preflight[@]}" >/tmp/webgpt-review-preflight.json 2>/tmp/webgpt-review-preflight.err; then
    should_reload=0
    if [[ "$refresh_extension" -eq 1 ]]; then
      if python3 - /tmp/webgpt-review-preflight.json <<'PY'
import json
import sys

try:
    with open(sys.argv[1], "r", encoding="utf-8") as fh:
        failures = set(json.load(fh).get("failures") or [])
except Exception:
    failures = set()

sys.exit(0 if failures.intersection({"surf_extension_socket", "focus_state"}) else 1)
PY
      then
        should_reload=1
      fi
    fi
    if [[ "$should_reload" -eq 1 ]]; then
      "$SURF_RUN" extension.reload >/tmp/webgpt-review-extension-reload.out 2>/tmp/webgpt-review-extension-reload.err || {
        echo "WebGPT preflight failed, and extension reload failed. Details:" >&2
        cat /tmp/webgpt-review-preflight.json >&2 || true
        cat /tmp/webgpt-review-preflight.err >&2 || true
        cat /tmp/webgpt-review-extension-reload.out >&2 || true
        cat /tmp/webgpt-review-extension-reload.err >&2 || true
        exit 5
      }
      if ! "${preflight[@]}" >/tmp/webgpt-review-preflight.json 2>/tmp/webgpt-review-preflight.err; then
        echo "WebGPT preflight failed after extension reload. Details:" >&2
        cat /tmp/webgpt-review-preflight.json >&2 || true
        cat /tmp/webgpt-review-preflight.err >&2 || true
        cat /tmp/webgpt-review-extension-reload.out >&2 || true
        cat /tmp/webgpt-review-extension-reload.err >&2 || true
        exit 5
      fi
    else
      echo "WebGPT preflight failed. Details:" >&2
      cat /tmp/webgpt-review-preflight.json >&2 || true
      cat /tmp/webgpt-review-preflight.err >&2 || true
      exit 5
    fi
  fi
elif [[ "$preflight_only" -eq 1 ]]; then
  echo "--preflight-only requires --tab-id/--url or --url." >&2
  exit 2
fi

if [[ "$preflight_only" -eq 1 ]]; then
  if [[ "$json_flag" -eq 1 ]]; then
    cat /tmp/webgpt-review-preflight.json
  else
    echo "OK: WebGPT preflight passed"
    cat /tmp/webgpt-review-preflight.json
  fi
  exit 0
fi

cmd=("$ASK_RUN" webgpt-review --bundle "$bundle" --review-type "$review_type" --timeout "$timeout_s")
if [[ -n "$project" ]]; then
  cmd+=(--project "$project")
fi
if [[ -n "$tab_id" ]]; then
  cmd+=(--tab-id "$tab_id")
fi
if [[ -n "$url" ]]; then
  cmd+=(--url "$url")
fi
if [[ "$create_tab" -eq 1 ]]; then
  cmd+=(--create-tab)
fi
if [[ -n "$ask_id" ]]; then
  cmd+=(--ask-id "$ask_id")
fi
if [[ -n "$output_root" ]]; then
  cmd+=(--output-root "$output_root")
fi
if [[ -n "$instructions" ]]; then
  cmd+=(--instructions "$instructions")
fi
if [[ "$json_flag" -eq 1 ]]; then
  cmd+=(--json)
fi
if [[ "$allow_foreground" -eq 1 ]]; then
  export ASK_WEBGPT_ALLOW_FOREGROUND=1
fi

exec "${cmd[@]}"
