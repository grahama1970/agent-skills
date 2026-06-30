#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DEFAULT="${HOME}/workspace/experiments/pi-mono/.pi/skills"
WORKTREE_BASE_DEFAULT="${HOME}/workspace/experiments/pi-mono/.pi/.worktrees/skills-ci"
FIXTURE_ROOT="$SCRIPT_DIR/tests/fixtures/skills_root"

if command -v uv &> /dev/null; then
  EXEC=(uv run python)
else
  EXEC=(python3)
fi

MODE="scan"
if [ "$1" == "--apply" ]; then
  MODE="apply"
  shift
fi

if [ "$MODE" == "scan" ]; then
  mkdir -p "$SCRIPT_DIR/.artifacts"
  "${EXEC[@]}" "$SCRIPT_DIR/skills_ci.py" --mode scan --root "$ROOT_DEFAULT" --report-json "$SCRIPT_DIR/.artifacts/report.json" --report-md "$SCRIPT_DIR/.artifacts/report.md"
  if [ ! -s "$SCRIPT_DIR/.artifacts/report.json" ]; then
    echo "report.json missing" >&2
    exit 1
  fi
  if [ ! -s "$SCRIPT_DIR/.artifacts/skills-ci-scan.state.json" ]; then
    echo "task-monitor state missing" >&2
    exit 1
  fi
  echo "PASS: skills-ci scan"
  exit 0
fi

BRANCH="skills-ci-sanity-$(date +%Y%m%d%H%M%S)"
mkdir -p "$SCRIPT_DIR/.artifacts"
APPLY_EXIT=0
"${EXEC[@]}" "$SCRIPT_DIR/skills_ci.py" --mode apply --root "$FIXTURE_ROOT" --best-practices best-practices-skills,best-practices-python --worktree-base "$WORKTREE_BASE_DEFAULT" --branch "$BRANCH" --copy-root --lint --lint-scope changed --report-json "$SCRIPT_DIR/.artifacts/report_apply.json" --report-md "$SCRIPT_DIR/.artifacts/report_apply.md" --per-skill --per-skill-dir "$SCRIPT_DIR/.artifacts/skills" || APPLY_EXIT=$?

if [ ! -s "$SCRIPT_DIR/.artifacts/report_apply.json" ]; then
  echo "report_apply.json missing" >&2
  exit 1
fi

if [ ! -s "$SCRIPT_DIR/.artifacts/skills-ci-apply.state.json" ]; then
  echo "task-monitor state missing" >&2
  exit 1
fi

if [ ! -s "$SCRIPT_DIR/.artifacts/skills/skill-a/report.json" ]; then
  echo "per-skill report missing" >&2
  exit 1
fi
if [ "$APPLY_EXIT" -ne 0 ]; then
  echo "NOTE: skills-ci apply reported violations (expected for fixtures)"
fi

echo "PASS: skills-ci apply"
