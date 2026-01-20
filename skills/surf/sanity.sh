#!/bin/bash
# Surf Skill - Setup Verification & Installation Guide
#
# This script checks if surf-cli is properly installed and guides
# the user through manual setup if needed.
#
# Usage: ./sanity.sh [--check-only]
#   --check-only: Only check status, don't prompt for setup

set -e

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN="$SKILL_DIR/run.sh"
SURF_CLI_PATH="/home/graham/workspace/experiments/surf-cli"
SOCKET_PATH="/tmp/surf.sock"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

print_header() {
    echo ""
    echo -e "${BOLD}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}  SURF SKILL - SETUP VERIFICATION${NC}"
    echo -e "${BOLD}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
}

print_step() {
    echo -e "${BLUE}[$1]${NC} $2"
}

print_ok() {
    echo -e "    ${GREEN}✓ $1${NC}"
}

print_fail() {
    echo -e "    ${RED}✗ $1${NC}"
}

print_warn() {
    echo -e "    ${YELLOW}⚠ $1${NC}"
}

print_instruction() {
    echo -e "    ${YELLOW}→ $1${NC}"
}

# ─────────────────────────────────────────────────────────────
# Check Functions
# ─────────────────────────────────────────────────────────────

check_chrome() {
    print_step "1/6" "Chrome Installation"
    if command -v google-chrome &>/dev/null; then
        print_ok "Google Chrome found: $(command -v google-chrome)"
        return 0
    elif command -v chromium &>/dev/null; then
        print_ok "Chromium found: $(command -v chromium)"
        return 0
    else
        print_fail "Chrome/Chromium not found"
        print_instruction "Install Google Chrome or Chromium"
        return 1
    fi
}

check_extension_built() {
    print_step "2/6" "Extension Built"
    if [[ -f "$SURF_CLI_PATH/dist/manifest.json" ]]; then
        local version=$(grep '"version"' "$SURF_CLI_PATH/dist/manifest.json" | head -1 | grep -oP '"\d+\.\d+\.\d+"' | tr -d '"')
        print_ok "Extension built: $SURF_CLI_PATH/dist (v$version)"
        return 0
    else
        print_fail "Extension not built at $SURF_CLI_PATH/dist"
        return 1
    fi
}

check_extension_loaded() {
    print_step "3/6" "Extension Loaded in Chrome"
    # Check if socket exists - indicates extension is communicating
    if [[ -S "$SOCKET_PATH" ]]; then
        print_ok "Socket exists: $SOCKET_PATH"
        return 0
    else
        print_fail "No socket at $SOCKET_PATH"
        print_instruction "Extension not loaded or not communicating"
        return 1
    fi
}

check_native_host() {
    print_step "4/6" "Native Host Installed"
    local host_file="$HOME/.config/google-chrome/NativeMessagingHosts/surf.browser.host.json"
    if [[ -f "$host_file" ]]; then
        local ext_id=$(grep -oP '"chrome-extension://\K[^/]+' "$host_file" 2>/dev/null || echo "unknown")
        print_ok "Native host configured for extension: $ext_id"
        return 0
    else
        print_fail "Native host not installed"
        print_instruction "Missing: $host_file"
        return 1
    fi
}

check_tab_list() {
    print_step "5/6" "CLI → Extension Communication"
    if [[ ! -S "$SOCKET_PATH" ]]; then
        print_fail "Cannot test - no socket"
        return 1
    fi

    local output
    output=$("$RUN" tab.list 2>&1) || true

    if echo "$output" | grep -qE '^[0-9]+\s+'; then
        local tab_count=$(echo "$output" | wc -l)
        print_ok "tab.list works ($tab_count tabs found)"
        return 0
    else
        print_fail "tab.list failed"
        echo "    Output: $output"
        return 1
    fi
}

check_read_command() {
    print_step "6/6" "Read Command"
    if [[ ! -S "$SOCKET_PATH" ]]; then
        print_fail "Cannot test - no socket"
        return 1
    fi

    local output
    output=$("$RUN" read 2>&1) || true

    if echo "$output" | grep -qE '\[e[0-9]+\]'; then
        print_ok "read command returns element refs"
        return 0
    elif [[ -n "$output" ]]; then
        print_warn "read command works but no element refs (page may be empty)"
        return 0
    else
        print_fail "read command returned nothing"
        return 1
    fi
}

# ─────────────────────────────────────────────────────────────
# Installation Guide
# ─────────────────────────────────────────────────────────────

print_setup_instructions() {
    echo ""
    echo -e "${BOLD}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}  MANUAL SETUP REQUIRED${NC}"
    echo -e "${BOLD}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "${YELLOW}Google Chrome blocks --load-extension for security.${NC}"
    echo -e "${YELLOW}You must manually load the extension. Follow these steps:${NC}"
    echo ""
}

guide_build_extension() {
    echo -e "${BOLD}STEP 1: Build the Extension${NC}"
    echo "─────────────────────────────────────────────────────────────────"
    echo ""
    echo "Run this command:"
    echo ""
    echo -e "  ${GREEN}cd $SURF_CLI_PATH && npm install && npm run build${NC}"
    echo ""
}

guide_load_extension() {
    echo -e "${BOLD}STEP 2: Load Extension in Chrome${NC}"
    echo "─────────────────────────────────────────────────────────────────"
    echo ""
    echo "1. Open Chrome and go to:"
    echo ""
    echo -e "     ${GREEN}chrome://extensions${NC}"
    echo ""
    echo "2. Enable ${BOLD}Developer mode${NC} (toggle in top-right corner)"
    echo ""
    echo "3. Click ${BOLD}Load unpacked${NC}"
    echo ""
    echo "4. Navigate to and select:"
    echo ""
    echo -e "     ${GREEN}$SURF_CLI_PATH/dist${NC}"
    echo ""
    echo "5. ${BOLD}IMPORTANT:${NC} Copy the Extension ID shown (e.g., lgamnnedgnehjplhndkkhojhbifgpcdp)"
    echo ""
}

guide_install_host() {
    echo -e "${BOLD}STEP 3: Install Native Host${NC}"
    echo "─────────────────────────────────────────────────────────────────"
    echo ""
    echo "Run this command with YOUR extension ID from Step 2:"
    echo ""
    echo -e "  ${GREEN}surf install <YOUR-EXTENSION-ID>${NC}"
    echo ""
    echo "Example:"
    echo ""
    echo -e "  ${GREEN}surf install lgamnnedgnehjplhndkkhojhbifgpcdp${NC}"
    echo ""
}

guide_verify() {
    echo -e "${BOLD}STEP 4: Verify Installation${NC}"
    echo "─────────────────────────────────────────────────────────────────"
    echo ""
    echo "Run:"
    echo ""
    echo -e "  ${GREEN}surf tab.list${NC}"
    echo ""
    echo "You should see a list of your browser tabs."
    echo ""
    echo "Then run this script again to confirm all checks pass:"
    echo ""
    echo -e "  ${GREEN}$SKILL_DIR/sanity.sh${NC}"
    echo ""
}

# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

main() {
    local check_only=0
    if [[ "$1" == "--check-only" ]]; then
        check_only=1
    fi

    print_header

    local all_passed=1
    local needs_build=0
    local needs_load=0
    local needs_host=0

    # Run all checks
    check_chrome || all_passed=0

    if ! check_extension_built; then
        all_passed=0
        needs_build=1
    fi

    if ! check_extension_loaded; then
        all_passed=0
        needs_load=1
    fi

    if ! check_native_host; then
        all_passed=0
        needs_host=1
    fi

    if ! check_tab_list; then
        all_passed=0
    fi

    if ! check_read_command; then
        all_passed=0
    fi

    echo ""

    if [[ $all_passed -eq 1 ]]; then
        echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
        echo -e "${GREEN}  ✓ ALL CHECKS PASSED - SURF-CLI IS FULLY OPERATIONAL${NC}"
        echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
        echo ""
        echo "You can now use:"
        echo "  surf tab.list          # List browser tabs"
        echo "  surf tab.new <url>     # Open new tab"
        echo "  surf read              # Read page with element refs"
        echo "  surf click e5          # Click element"
        echo ""
        exit 0
    fi

    if [[ $check_only -eq 1 ]]; then
        echo -e "${RED}═══════════════════════════════════════════════════════════════${NC}"
        echo -e "${RED}  ✗ SETUP INCOMPLETE${NC}"
        echo -e "${RED}═══════════════════════════════════════════════════════════════${NC}"
        echo ""
        echo "Run without --check-only for setup instructions."
        exit 1
    fi

    # Print setup instructions
    print_setup_instructions

    if [[ $needs_build -eq 1 ]]; then
        guide_build_extension
    fi

    if [[ $needs_load -eq 1 ]]; then
        guide_load_extension
    fi

    if [[ $needs_host -eq 1 ]]; then
        guide_install_host
    fi

    guide_verify

    echo -e "${BOLD}═══════════════════════════════════════════════════════════════${NC}"
    echo ""

    exit 1
}

main "$@"
