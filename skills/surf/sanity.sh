#!/usr/bin/env bash
# Sanity tests for surf skill
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

echo "=== Surf Skill Sanity Tests ==="
echo ""

# -----------------------------------------------------------------------------
# 1. CLI availability
# -----------------------------------------------------------------------------
echo "1. CLI availability"

SURF_AVAILABLE=false
if command -v surf &>/dev/null; then
    log_pass "surf CLI found: $(command -v surf)"
    SURF_AVAILABLE=true
else
    log_missing "surf CLI not found" "npm install -g @anthropic/surf-cli"
fi

# -----------------------------------------------------------------------------
# 2. Help command
# -----------------------------------------------------------------------------
echo "2. Help command"

if $SURF_AVAILABLE; then
    if surf --help &>/dev/null; then
        log_pass "surf --help"
    else
        log_fail "surf --help returns error"
    fi
fi

# -----------------------------------------------------------------------------
# 3. Documented commands exist
# -----------------------------------------------------------------------------
echo "3. Documented commands"

if $SURF_AVAILABLE; then
    HELP_OUTPUT=$(surf --help-full 2>&1 || true)

    COMMANDS=("navigate" "click" "type" "screenshot" "page.read" "wait" "js" "tab.list")
    for cmd in "${COMMANDS[@]}"; do
        if echo "$HELP_OUTPUT" | grep -qw "$cmd"; then
            log_pass "$cmd command documented"
        else
            log_fail "$cmd command not found in help"
        fi
    done
fi

# -----------------------------------------------------------------------------
# 4. Browser extension connection
# -----------------------------------------------------------------------------
echo "4. Browser extension connection"

if $SURF_AVAILABLE; then
    # Check native host manifest exists
    NATIVE_HOST="${HOME}/.config/google-chrome/NativeMessagingHosts/surf.browser.host.json"
    if [[ -f "$NATIVE_HOST" ]]; then
        log_pass "Native host manifest installed"
    else
        log_missing "Native host manifest not found" "surf install <chrome-extension-id>"
    fi

    # Test actual connection to Chrome
    if timeout 5 surf tab.list &>/dev/null; then
        log_pass "surf connected to Chrome"
    else
        log_missing "surf cannot connect to Chrome" "Restart Chrome with extension enabled"
    fi
fi

# -----------------------------------------------------------------------------
# 5. Browser availability
# -----------------------------------------------------------------------------
echo "5. Browser availability"

BROWSER_FOUND=false
for browser in google-chrome chromium chromium-browser; do
    if command -v "$browser" &>/dev/null; then
        log_pass "Browser found: $(command -v $browser)"
        BROWSER_FOUND=true
        break
    fi
done

if ! $BROWSER_FOUND; then
    log_missing "Chrome/Chromium not found in PATH" "Install Google Chrome or Chromium"
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
    exit 0
else
    echo "Result: PASS"
    exit 0
fi
