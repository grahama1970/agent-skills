#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
SKILLS_ROOT="$(dirname "$SKILL_DIR")"
PROJECT_DIR="${1:-$(pwd)}"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="${PROJECT_STATE_LIVE_ARTIFACT_DIR:-${PROJECT_DIR}/.artifacts/best-practices-project-state/${RUN_ID}}"

mkdir -p "$OUT_DIR"

if command -v browser-oracle >/dev/null 2>&1; then
  BROWSER_ORACLE=(browser-oracle)
elif [[ -x "$SKILLS_ROOT/browser-oracle/run.sh" ]]; then
  BROWSER_ORACLE=(bash "$SKILLS_ROOT/browser-oracle/run.sh")
else
  echo '{"ok": false, "error": "browser-oracle command not found"}' >"$OUT_DIR/browser-oracle.resolve.json"
  echo "Result: FAIL ($OUT_DIR)" >&2
  exit 1
fi

"${BROWSER_ORACLE[@]}" resolve --from "$PROJECT_DIR" --backend webgpt --json \
  >"$OUT_DIR/browser-oracle.resolve.json"

ENTRYPOINT_RECEIPTS=()
for entrypoint in \
  "$SKILLS_ROOT/brave-search/run.sh" \
  "$SKILLS_ROOT/github-search/run.sh" \
  "$SKILLS_ROOT/dogpile/run.sh" \
  "$SKILLS_ROOT/ask/run.sh"; do
  if [[ ! -x "$entrypoint" ]]; then
    printf '{"ok": false, "missing_entrypoint": "%s"}\n' "$entrypoint" \
      >"$OUT_DIR/entrypoint-missing.json"
    echo "Result: FAIL ($OUT_DIR)" >&2
    exit 1
  fi
  receipt="$OUT_DIR/$(basename "$(dirname "$entrypoint")").help.txt"
  if ! timeout 30 bash "$entrypoint" --help >"$receipt" 2>&1; then
    printf '{"ok": false, "failed_entrypoint": "%s", "receipt": "%s"}\n' \
      "$entrypoint" "$receipt" >"$OUT_DIR/entrypoint-failed.json"
    echo "Result: FAIL ($OUT_DIR)" >&2
    exit 1
  fi
  ENTRYPOINT_RECEIPTS+=("$receipt")
done

cat >"$OUT_DIR/summary.json" <<JSON
{
  "ok": true,
  "project_dir": "$PROJECT_DIR",
  "browser_oracle_receipt": "$OUT_DIR/browser-oracle.resolve.json",
  "entrypoints_checked": [
    "$SKILLS_ROOT/brave-search/run.sh",
    "$SKILLS_ROOT/github-search/run.sh",
    "$SKILLS_ROOT/dogpile/run.sh",
    "$SKILLS_ROOT/ask/run.sh"
  ],
  "entrypoint_receipts": [
    "${ENTRYPOINT_RECEIPTS[0]}",
    "${ENTRYPOINT_RECEIPTS[1]}",
    "${ENTRYPOINT_RECEIPTS[2]}",
    "${ENTRYPOINT_RECEIPTS[3]}"
  ],
  "does_not_prove": "actual research or WebGPT review completion"
}
JSON

echo "Result: PASS ($OUT_DIR)"
