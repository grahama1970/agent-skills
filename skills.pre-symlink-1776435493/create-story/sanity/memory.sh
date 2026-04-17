#!/usr/bin/env bash
#
# Sanity script: Memory skill availability
# Purpose: Verify /memory skill is available for story storage
# Exit codes: 0=PASS, 1=FAIL
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
PI_SKILLS_DIR="$(dirname "$SKILL_DIR")"

echo "Checking /memory skill availability..."

# Check memory skill exists
if [[ ! -f "${PI_SKILLS_DIR}/memory/run.sh" ]]; then
    echo "FAIL: /memory skill not found at ${PI_SKILLS_DIR}/memory/"
    exit 1
fi

# Check memory skill is executable
if [[ ! -x "${PI_SKILLS_DIR}/memory/run.sh" ]]; then
    echo "FAIL: /memory skill not executable"
    exit 1
fi

echo "PASS: /memory skill is available"
exit 0
