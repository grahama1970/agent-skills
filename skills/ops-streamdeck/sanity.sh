#!/bin/bash
# Stream Deck Skill - Sanity Check
# Verifies that the skill is properly configured and functional

set -e

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Get skill name from directory name
SKILL_NAME="$(basename "$SCRIPT_DIR")"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Log function
log() {
    echo -e "${GREEN}[$SKILL_NAME]${NC} $*"
}

# Error function
error() {
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

# Success function
success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
}

# Warning function
warning() {
    echo -e "${YELLOW}[WARNING]${NC} $*"
}

# Test counter
TESTS_PASSED=0
TESTS_FAILED=0

# Test function
run_test() {
    local test_name="$1"
    local test_command="$2"
    
    log "Running test: $test_name..."
    
    if eval "$test_command"; then
        success "$test_name"
        ((TESTS_PASSED++))
    else
        error "$test_name"
        ((TESTS_FAILED++))
    fi
}

# Check if required commands are available
log "Checking required commands..."

# Check for uvx
if ! command -v uvx &> /dev/null; then
    error "uvx not found"
    exit 1
fi
success "uvx is available"

# Check for python3
if ! command -v python3 &> /dev/null; then
    error "python3 not found"
    exit 1
fi
success "python3 is available"

# Check for curl
if ! command -v curl &> /dev/null; then
    error "curl not found"
    exit 1
fi
success "curl is available"

# Check configuration directory
log "Checking configuration directory..."

CONFIG_DIR="$HOME/.streamdeck"
if [ ! -d "$CONFIG_DIR" ]; then
    warning "Config directory does not exist: $CONFIG_DIR"
    log "Creating config directory..."
    mkdir -p "$CONFIG_DIR"
    success "Config directory created"
else
    success "Config directory exists"
fi

# Check if streamdeck package is available
log "Checking streamdeck package..."

if python3 -c "import streamdeck" 2>/dev/null; then
    success "streamdeck package is installed"
else
    warning "streamdeck package not found"
    log "You may need to install streamdeck package first:"
    log "  cd /home/graham/workspace/streamdeck"
    log "  uv pip install -e ."
fi

# Check if streamdeck CLI works
log "Checking streamdeck CLI..."

if python3 -m streamdeck --help &> /dev/null; then
    success "streamdeck CLI is working"
else
    error "streamdeck CLI is not working"
    exit 1
fi

# Check for required Python packages
log "Checking required Python packages..."

REQUIRED_PACKAGES=("fastapi" "uvicorn" "pydantic")

for package in "${REQUIRED_PACKAGES[@]}"; do
    if python3 -c "import $package" 2>/dev/null; then
        success "$package is available"
    else
        warning "$package is not available"
    fi
done

# Check for Stream Deck hardware
log "Checking Stream Deck hardware..."

if command -v lsusb &> /dev/null; then
    if lsusb | grep -i "elgato" | grep -i "stream deck" &> /dev/null; then
        success "Stream Deck hardware detected"
    else
        warning "Stream Deck hardware not detected"
        log "This is normal if you don't have a Stream Deck connected"
    fi
else
    warning "lsusb not available, skipping hardware check"
fi

# Check network port availability
log "Checking network port availability..."

PORT="${STREAMDECK_DAEMON_PORT:-48970}"
HOST="${STREAMDECK_DAEMON_HOST:-127.0.0.1}"

if command -v lsof &> /dev/null; then
    if lsof -i :$PORT &> /dev/null; then
        warning "Port $PORT is already in use"
    else
        success "Port $PORT is available"
    fi
else
    warning "lsof not available, skipping port check"
fi

# Test basic HTTP connectivity
log "Testing HTTP connectivity..."

if command -v curl &> /dev/null; then
    if curl -s --connect-timeout 2 "http://${HOST}:${PORT}/status" &> /dev/null; then
        success "HTTP endpoint is accessible"
    else
        warning "HTTP endpoint is not accessible"
        log "This is expected if daemon is not running"
    fi
else
    warning "curl not available, skipping HTTP test"
fi

# Summary
log ""
log "=== Sanity Check Summary ==="
log "Tests passed: $TESTS_PASSED"
log "Tests failed: $TESTS_FAILED"
log ""

if [ $TESTS_FAILED -eq 0 ]; then
    success "All sanity checks passed!"
    exit 0
else
    error "Some sanity checks failed"
    exit 1
fi
