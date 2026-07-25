#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/tmp/best-practices-project-state-venv}"
export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/best-practices-project-state-pycache}"
PY=(uv run --project "$SKILL_DIR" python)

test -f "$SKILL_DIR/SKILL.md"
"${PY[@]}" -m py_compile "$SCRIPT_DIR/validate_project_state.py"

positive="$(mktemp)"
negative="$(mktemp)"
negative_output="$(mktemp)"
before_hash="$(sha256sum "$SKILL_DIR/SKILL.md" | awk '{print $1}')"
trap 'rm -f "$positive" "$negative" "$negative_output"' EXIT

cat >"$positive" <<'MD'
# Project State: example

## Executive Summary

Example.

## Evidence Receipts

- Sanity receipt: `.artifacts/sanity/example/summary.json`
- Review receipt: `.ask_artifacts/runs/example/review.md`

## What Works

- Not established without receipt.

## Outstanding Gaps

- Not established.

## Aspirational Or Stale Material

- Not established.

## Missing Or Regressed Capabilities

- Not established.

## Competitive And Research Landscape

- Not established.

## Project Positioning

- Not established.

## Risks And Unknowns

- Not established.

## Recommended Next Actions

- Not established.
MD

cat >"$negative" <<'MD'
# Project State: broken

## Executive Summary

This file intentionally lacks the required evidence sections.
MD

"${PY[@]}" "$SCRIPT_DIR/validate_project_state.py" "$positive"
"${PY[@]}" "$SCRIPT_DIR/validate_project_state.py" "$positive" --json | grep -q '"ok": true'
if "${PY[@]}" "$SCRIPT_DIR/validate_project_state.py" "$negative" >"$negative_output" 2>&1; then
  echo "[FAIL] negative-control fixture unexpectedly passed" >&2
  exit 1
fi
grep -q "missing required section" "$negative_output"
after_hash="$(sha256sum "$SKILL_DIR/SKILL.md" | awk '{print $1}')"
test "$before_hash" = "$after_hash"
test ! -e "$SKILL_DIR/PROJECT_STATE.md"
echo "Result: PASS"
