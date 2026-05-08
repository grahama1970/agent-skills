#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# This is the portable other-project adoption smoke. It intentionally reuses the
# full real-entrypoint E2E because that test creates a temporary external git
# repository, validates it through /plan and /review-plan, runs /orchestrate
# against the real /code-runner entrypoint with deterministic model output, proves
# source commit on success, proves revert on blind failure, preserves scratch
# files, and checks no stale worktree remains.
"$SCRIPT_DIR/run_plan_review_orchestrate_code_runner_mock_e2e.sh"
