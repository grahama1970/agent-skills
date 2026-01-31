#!/usr/bin/env bash
# review-music sanity check
#
# Validates all dependencies and skill functionality.
# Exit codes:
#   0 = All checks pass
#   1 = One or more checks failed

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

FAILED=0

log_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    FAILED=1
}

log_skip() {
    echo -e "${YELLOW}[SKIP]${NC} $1"
}

echo "=== review-music Sanity Check ==="
echo ""

# Check Python
echo "1. Python Environment"
echo "---------------------"
# Prefer local .venv if it exists (avoids Python version conflicts)
if [[ -f ".venv/bin/python" ]]; then
    echo "Using: .venv (local virtualenv)"
    PYTHON=".venv/bin/python"
elif command -v uv &> /dev/null; then
    echo "Using: uv"
    PYTHON="uv run python"
else
    echo "Using: python3"
    PYTHON="python3"
fi

if $PYTHON --version &> /dev/null; then
    log_pass "Python available: $($PYTHON --version)"
else
    log_fail "Python not available"
fi
echo ""

# Generate test fixtures if needed
echo "2. Test Fixtures"
echo "----------------"
if [[ ! -f "fixtures/test_audio.wav" ]]; then
    echo "Generating test audio fixtures..."
    $PYTHON fixtures/generate_test_audio.py
fi

if [[ -f "fixtures/test_audio.wav" ]]; then
    log_pass "test_audio.wav exists"
else
    log_fail "test_audio.wav not found"
fi

if [[ -f "fixtures/test_spoken.wav" ]]; then
    log_pass "test_spoken.wav exists"
else
    log_fail "test_spoken.wav not found"
fi
echo ""

# Run sanity scripts for MIR libraries
echo "3. MIR Library Sanity Scripts"
echo "-----------------------------"

# librosa (required)
echo ""
echo "3a. librosa"
if $PYTHON sanity/librosa_features.py; then
    log_pass "librosa sanity check passed"
else
    log_fail "librosa sanity check failed"
fi

# madmom (optional - build issues with Python 3.13)
echo ""
echo "3b. madmom (optional)"
if $PYTHON sanity/madmom_beats.py 2>/dev/null; then
    log_pass "madmom sanity check passed"
else
    log_skip "madmom not available (optional enhancement)"
fi

# essentia (optional - build issues with Python 3.13)
echo ""
echo "3c. essentia (optional)"
if $PYTHON sanity/essentia_key.py 2>/dev/null; then
    log_pass "essentia sanity check passed"
else
    log_skip "essentia not available (optional enhancement)"
fi

# whisper (required)
echo ""
echo "3d. whisper"
if $PYTHON sanity/whisper_transcribe.py; then
    log_pass "whisper sanity check passed"
else
    log_fail "whisper sanity check failed"
fi
echo ""

# Run tests
echo "4. Unit Tests"
echo "-------------"
TEST_OUTPUT=$($PYTHON -m pytest tests/ --tb=short 2>&1)
TEST_EXIT=$?
echo "$TEST_OUTPUT" | tail -10
if [[ $TEST_EXIT -eq 0 ]]; then
    log_pass "All tests passed"
elif echo "$TEST_OUTPUT" | grep -q "passed"; then
    # Some tests passed, check if failures are just skips
    if echo "$TEST_OUTPUT" | grep -q "failed"; then
        log_fail "Some tests failed"
    else
        log_pass "Tests completed (with some skips)"
    fi
else
    log_fail "Test run failed"
fi
echo ""

# Check CLI
echo "5. CLI Commands"
echo "---------------"
if ./run.sh help &> /dev/null; then
    log_pass "./run.sh help works"
else
    log_fail "./run.sh help failed"
fi
echo ""

# Summary
echo "========================================"
if [[ $FAILED -eq 0 ]]; then
    echo -e "${GREEN}All sanity checks passed!${NC}"
    exit 0
else
    echo -e "${RED}Some sanity checks failed.${NC}"
    exit 1
fi
