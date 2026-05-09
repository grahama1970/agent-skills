#!/usr/bin/env bash
# Example Codex Stop hook wrapper.
# Configure this as a Stop hook, or call from an orchestrate/checkpoint boundary.
set -euo pipefail

REPO_ROOT="${PROJECT_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
SKILL_DIR="${PROJECT_DRIFT_SKILL_DIR:-$REPO_ROOT/skills/project-drift}"
TRANSCRIPT_PATH="${TRANSCRIPT_PATH:-${transcript_path:-}}"
OUT_DIR="${PROJECT_DRIFT_OUT_DIR:-$REPO_ROOT/.project-drift/latest}"

if [[ -z "$TRANSCRIPT_PATH" ]]; then
    # Codex/Claude hook payload is usually JSON on stdin. Try to extract transcript_path.
    if command -v jq >/dev/null 2>&1; then
      payload="$(cat || true)"
      TRANSCRIPT_PATH="$(printf '%s' "$payload" | jq -r '.transcript_path // .transcriptPath // empty' 2>/dev/null || true)"
      payload_cwd="$(printf '%s' "$payload" | jq -r '.cwd // empty' 2>/dev/null || true)"
      if [[ -n "$payload_cwd" ]]; then
        REPO_ROOT="${PROJECT_ROOT:-$(git -C "$payload_cwd" rev-parse --show-toplevel 2>/dev/null || printf '%s' "$payload_cwd")}"
        OUT_DIR="${PROJECT_DRIFT_OUT_DIR:-$REPO_ROOT/.project-drift/latest}"
      fi
    fi
  fi
  
scan_args=(
  scan
  --project-root "$REPO_ROOT"
  --out-dir "$OUT_DIR"
  --since auto
  --trigger "Stop hook"
  --no-execute
)

if [[ -n "$TRANSCRIPT_PATH" && -f "$TRANSCRIPT_PATH" ]]; then
  scan_args+=(--transcript "$TRANSCRIPT_PATH")
fi

"$SKILL_DIR/run.sh" "${scan_args[@]}" >/dev/null || true

echo '{"continue": true, "suppressOutput": true, "systemMessage": "project-drift prompt payload written"}'
