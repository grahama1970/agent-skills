#!/usr/bin/env bash
# Probe local LLM runtimes (Ollama, vLLM, SGLang) and report readiness.
set -euo pipefail

TARGETS=()
WARN_ONLY=0
TIMEOUT="${LLM_HEALTH_TIMEOUT:-2}"
usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Options:
  --target <name:url>   Target endpoint (repeatable). Example: ollama:http://127.0.0.1:11434
  --warn-only           Exit with 0 even if targets are unreachable.
  --timeout <seconds>   CURL timeout per target (default: 2 or LLM_HEALTH_TIMEOUT).
  --help                Show this help message.

If no targets are provided the script probes common defaults:
  ollama:http://127.0.0.1:11434
  vllm:http://127.0.0.1:8000
  sglang:http://127.0.0.1:30000
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      TARGETS+=("$2"); shift 2;;
    --warn-only)
      WARN_ONLY=1; shift;;
    --timeout)
      TIMEOUT="$2"; shift 2;;
    --help|-h)
      usage; exit 0;;
    *)
      echo "Unknown option: $1" >&2
      usage; exit 1;;
  esac
done

if [[ ${#TARGETS[@]} -eq 0 ]]; then
  TARGETS=(
    "ollama:http://127.0.0.1:11434"
    "vllm:http://127.0.0.1:8000"
    "sglang:http://127.0.0.1:30000"
  )
fi

status=0
for target in "${TARGETS[@]}"; do
  name="${target%%:*}"
  url="${target#*:}"
  url="${url#//}"
  if [[ "$url" != http://* && "$url" != https://* ]]; then
    url="http://$url"
  fi
  echo "Checking $name at $url ..."
  if curl --silent --show-error --fail --max-time "$TIMEOUT" "$url" >/dev/null 2>&1; then
    echo "  OK"
  else
    echo "  FAILED"
    status=1
  fi
done

if [[ $status -ne 0 && $WARN_ONLY -eq 1 ]]; then
  echo "One or more targets failed, but --warn-only was specified."
  status=0
fi

exit $status
