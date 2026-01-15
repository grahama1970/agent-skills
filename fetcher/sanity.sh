#!/usr/bin/env bash
# Sanity tests for fetcher skill
# Run: ./sanity.sh
# Exit codes: 0 = all pass, 1 = failures

set -euo pipefail

# Load environment from common .env files
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../common.sh" 2>/dev/null || true

PASS=0
FAIL=0
MISSING_DEPS=()

log_pass() { echo "  [PASS] $1"; ((++PASS)); }
log_fail() { echo "  [FAIL] $1"; ((++FAIL)); }
log_missing() {
    echo "  [MISS] $1"
    MISSING_DEPS+=("$2")
}

echo "=== Fetcher Skill Sanity Tests ==="
echo ""

# -----------------------------------------------------------------------------
# 1. CLI availability
# -----------------------------------------------------------------------------
echo "1. CLI availability"

FETCHER_AVAILABLE=false
if command -v fetcher &>/dev/null; then
    log_pass "fetcher CLI found: $(command -v fetcher)"
    FETCHER_AVAILABLE=true
else
    log_missing "fetcher CLI not found" "pip install fetcher-cli"
fi

if command -v fetcher-etl &>/dev/null; then
    log_pass "fetcher-etl CLI found"
else
    log_missing "fetcher-etl CLI not found" "pip install fetcher[etl]"
fi

# -----------------------------------------------------------------------------
# 2. Help commands
# -----------------------------------------------------------------------------
echo "2. Help commands"

if $FETCHER_AVAILABLE; then
    if fetcher --help &>/dev/null 2>&1; then
        log_pass "fetcher --help"
    else
        log_fail "fetcher --help returns error"
    fi

    if fetcher get --help &>/dev/null 2>&1; then
        log_pass "fetcher get --help"
    else
        log_fail "fetcher get --help returns error"
    fi
fi

# -----------------------------------------------------------------------------
# 3. Python API
# -----------------------------------------------------------------------------
echo "3. Python API"

# Try to find the correct import path
PYTHON_API_FOUND=false
for import_path in \
    "from fetcher.workflows.web_fetch import URLFetcher" \
    "from fetcher.web_fetch import URLFetcher" \
    "from fetcher import URLFetcher"; do
    if python3 -c "$import_path" 2>/dev/null; then
        log_pass "URLFetcher import ($import_path)"
        PYTHON_API_FOUND=true
        break
    fi
done
if ! $PYTHON_API_FOUND; then
    log_missing "URLFetcher not importable" "pip install fetcher"
fi

FETCH_URL_FOUND=false
for import_path in \
    "from fetcher.workflows.fetcher import fetch_url" \
    "from fetcher.fetcher import fetch_url" \
    "from fetcher import fetch_url"; do
    if python3 -c "$import_path" 2>/dev/null; then
        log_pass "fetch_url import ($import_path)"
        FETCH_URL_FOUND=true
        break
    fi
done
if ! $FETCH_URL_FOUND; then
    log_missing "fetch_url not importable" "pip install fetcher"
fi

# -----------------------------------------------------------------------------
# 4. Dependencies
# -----------------------------------------------------------------------------
echo "4. Dependencies"

if python3 -c "import playwright" 2>/dev/null; then
    log_pass "playwright package installed"
else
    log_missing "playwright package not installed" "pip install playwright && playwright install chromium"
fi

if command -v playwright &>/dev/null; then
    log_pass "playwright CLI available"
else
    log_missing "playwright CLI not found" "pip install playwright"
fi

# -----------------------------------------------------------------------------
# 5. Environment variables
# -----------------------------------------------------------------------------
echo "5. Environment variables"

if [[ -n "${BRAVE_API_KEY:-}" ]]; then
    log_pass "BRAVE_API_KEY set (enables search fallbacks)"
else
    echo "  [INFO] BRAVE_API_KEY not set (optional - enables search fallbacks)"
fi

# -----------------------------------------------------------------------------
# 6. Functional test
# -----------------------------------------------------------------------------
echo "6. Functional test"

if $FETCHER_AVAILABLE; then
    if fetcher get --help 2>&1 | grep -q "dry-run\|dry_run"; then
        log_pass "fetcher get supports --dry-run"
    else
        echo "  [INFO] --dry-run flag not found in help"
    fi
fi

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo ""
echo "=== Summary ==="
echo "  Passed: $PASS"
echo "  Failed: $FAIL"
echo "  Missing: ${#MISSING_DEPS[@]}"

if [[ ${#MISSING_DEPS[@]} -gt 0 ]]; then
    echo ""
    echo "=== Missing Dependencies ==="
    echo "Run these commands to install missing components:"
    echo ""
    # Deduplicate
    printf '%s\n' "${MISSING_DEPS[@]}" | sort -u | while read -r cmd; do
        echo "  $cmd"
    done
fi

echo ""
if [[ $FAIL -gt 0 ]]; then
    echo "Result: FAIL ($FAIL failures)"
    exit 1
elif [[ ${#MISSING_DEPS[@]} -gt 0 ]]; then
    echo "Result: INCOMPLETE (missing dependencies)"
    exit 0  # Don't fail CI, but inform user
else
    echo "Result: PASS"
    exit 0
fi
