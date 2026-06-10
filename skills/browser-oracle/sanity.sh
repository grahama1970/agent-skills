#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "[sanity] uv sync"
uv sync --project "$SCRIPT_DIR" >/dev/null

echo "[sanity] unit tests"
uv run --project "$SCRIPT_DIR" pytest -q

echo "[sanity] negative control: no registry in temp dir"
TMP_NO_REG="$(mktemp -d)"
if uv run --project "$SCRIPT_DIR" python -m browser_oracle.cli resolve --from "$TMP_NO_REG" --json >/tmp/bo-no-reg.json 2>/dev/null; then
  echo "expected resolve to fail without registry" >&2
  exit 1
fi
rm -rf "$TMP_NO_REG"

echo "[sanity] positive control: walk-up + resolve fixture"
FIXTURE="$(mktemp -d)"
mkdir -p "$FIXTURE/skills/oc-subagent/personas/mathematics"
uv run --project "$SCRIPT_DIR" python -m browser_oracle.cli register \
  --at "$FIXTURE/skills/oc-subagent" \
  --backend webgpt \
  --default \
  oc-subagent-fixture
uv run --project "$SCRIPT_DIR" python -m browser_oracle.cli register \
  --at "$FIXTURE/skills/oc-subagent" \
  --backend webgpt \
  --relative-path personas/mathematics \
  oc-subagent-math-fixture
OUT="$(uv run --project "$SCRIPT_DIR" python -m browser_oracle.cli resolve \
  --from "$FIXTURE/skills/oc-subagent/personas/mathematics" --json)"
echo "$OUT" | grep -q oc-subagent-math-fixture
rm -rf "$FIXTURE"

echo "[sanity] bind roundtrip in temp project root"
BIND_ROOT="$(mktemp -d)"
BROWSER_ORACLE_WEBGPT_PROJECT_ROOT="$BIND_ROOT" \
  uv run --project "$SCRIPT_DIR" python -m browser_oracle.cli bind demo-sanity \
  --tab-id 999001 --url 'https://chatgpt.com/c/demo' --manual --json >/dev/null
test -f "$BIND_ROOT/demo-sanity.json"
rm -rf "$BIND_ROOT"

echo "[sanity] oc-subagent live resolve (registry in repo)"
MATH_DIR="$SCRIPT_DIR/../oc-subagent/personas/mathematics"
if [[ -d "$MATH_DIR" ]]; then
  uv run --project "$SCRIPT_DIR" python -m browser_oracle.cli resolve --from "$MATH_DIR" --json | grep -q oc-subagent-personas
fi

echo "browser-oracle sanity: PASS"
