#!/usr/bin/env bash
# Compatibility entrypoint for the documented `surf webgpt.e2e-sanity` command.
# The live implementation is `live_webgpt_sanity.py`; this wrapper preserves the
# older CLI shape used by SKILL.md and project agents.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

args=(--allow-live --profile release)

while [[ $# -gt 0 ]]; do
  case "$1" in
    --json)
      # live_webgpt_sanity.py always prints a JSON summary.
      shift
      ;;
    --no-activate)
      # The live sanity gate is background-only by contract.
      shift
      ;;
    --timeout)
      [[ $# -ge 2 ]] || { echo "Error: --timeout requires seconds" >&2; exit 2; }
      args+=(--roundtrip-timeout "$2")
      shift 2
      ;;
    --timeout=*)
      args+=(--roundtrip-timeout "${1#*=}")
      shift
      ;;
    --output-dir)
      [[ $# -ge 2 ]] || { echo "Error: --output-dir requires a path" >&2; exit 2; }
      args+=(--output-root "$2")
      shift 2
      ;;
    --output-dir=*)
      args+=(--output-root "${1#*=}")
      shift
      ;;
    --profile|--tab-id|--url|--expect-url|--roundtrip-timeout|--roundtrip-interval|--output-root|--only)
      [[ $# -ge 2 ]] || { echo "Error: $1 requires a value" >&2; exit 2; }
      args+=("$1" "$2")
      shift 2
      ;;
    --profile=*|--tab-id=*|--url=*|--expect-url=*|--roundtrip-timeout=*|--roundtrip-interval=*|--output-root=*|--only=*)
      args+=("$1")
      shift
      ;;
    --allow-foreground-diagnostic|--plan-only|--allow-live)
      args+=("$1")
      shift
      ;;
    *)
      echo "Error: unknown webgpt.e2e-sanity argument: $1" >&2
      exit 2
      ;;
  esac
done

exec python3 "$SCRIPT_DIR/live_webgpt_sanity.py" "${args[@]}"
