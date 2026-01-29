#!/usr/bin/env bash
# Remove cached LLM artifacts (Ollama, HuggingFace, vLLM) with a dry-run by default.
set -euo pipefail

CACHE_DIRS=(${LLM_CACHE_DIRS:-"$HOME/.cache/ollama" "$HOME/.cache/huggingface" "$HOME/.cache/vllm"})
DRY_RUN=1
usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Options:
  --path <dir>   Add an additional cache directory to clean (repeatable).
  --execute      Delete files instead of printing what would be removed.
  --help         Show this help message.

Environment:
  LLM_CACHE_DIRS  Space-separated list of directories to consider.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --path)
      CACHE_DIRS+=("$2"); shift 2;;
    --execute)
      DRY_RUN=0; shift;;
    --help|-h)
      usage; exit 0;;
    *)
      echo "Unknown option: $1" >&2
      usage; exit 1;;
  esac
done

removed_any=0
for dir in "${CACHE_DIRS[@]}"; do
  if [[ ! -d "$dir" ]]; then
    continue
  fi
  echo "Processing cache directory: $dir"
  du -sh "$dir" || true
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[dry-run] Would remove contents of $dir"
  else
    rm -rf "$dir"/*
    removed_any=1
  fi
done

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "Dry run complete. Re-run with --execute to clear caches."
else
  if [[ $removed_any -eq 1 ]]; then
    echo "Cache directories cleared."
  else
    echo "No cache directories existed."
  fi
fi
