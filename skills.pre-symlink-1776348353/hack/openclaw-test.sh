#!/bin/bash
#
# OpenClaw Gateway Security Test Runner
# Wrapper for hack skill to test OpenClaw gateway security
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATEWAY_ATTACKS="${SCRIPT_DIR}/tools/openclaw/gateway_attacks.py"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_usage() {
    cat <<EOF
OpenClaw Gateway Security Testing

Usage:
  $0 test <gateway-url>          Run all security tests
  $0 token <gateway-url>         Test token security only
  $0 timing <gateway-url>        Test for timing attacks
  $0 tailscale <gateway-url>     Test Tailscale header spoofing
  $0 ip <gateway-url>            Test IP whitelist bypass

Examples:
  $0 test http://localhost:7777
  $0 token https://gateway.example.com

EOF
}

run_security_test() {
    local target="$1"
    
    echo -e "${YELLOW}[*] Starting OpenClaw Gateway Security Test${NC}"
    echo -e "${YELLOW}[*] Target: ${target}${NC}"
    echo ""
    
    # Run in Docker for isolation
    if command -v docker &> /dev/null; then
        echo "[*] Running in Docker container for isolation..."
        docker run --rm --network=host \
            -v "${SCRIPT_DIR}:/opt/hack" \
            -w /opt/hack \
            python:3.11-slim \
            bash -c "pip install -q requests && python /opt/hack/tools/openclaw/gateway_attacks.py '${target}'"
    else
        echo "[*] Docker not available, running directly..."
        python3 "${GATEWAY_ATTACKS}" "${target}"
    fi
    
    local exit_code=$?
    echo ""
    
    if [ $exit_code -eq 0 ]; then
        echo -e "${GREEN}✅ All security tests passed - no vulnerabilities found${NC}"
    else
        echo -e "${RED}❌ Security vulnerabilities detected - see report above${NC}"
    fi
    
    return $exit_code
}

# Main

if [ $# -lt 1 ]; then
    print_usage
    exit 1
fi

command="$1"
shift

case "$command" in
    test)
        if [ $# -lt 1 ]; then
            echo "Error: gateway URL required"
            print_usage
            exit 1
        fi
        run_security_test "$1"
        ;;
    token|timing|tailscale|ip)
        echo "Specific test modes not yet implemented"
        echo "Use 'test' command to run all tests"
        exit 1
        ;;
    *)
        echo "Unknown command: $command"
        print_usage
        exit 1
        ;;
esac
