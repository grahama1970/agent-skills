#!/bin/bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Hack Skill Sanity ==="

# Check run.sh
if [[ -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "  [PASS] run.sh exists and is executable"
else
    echo "  [FAIL] run.sh missing or not executable"
    exit 1
fi

# Check CLI Help
if "$SCRIPT_DIR/run.sh" --help >/dev/null 2>&1; then
    echo "  [PASS] run.sh --help works"
else
    echo "  [FAIL] run.sh --help failed"
    exit 1
fi

# Check Docker is available (required for this skill)
if command -v docker >/dev/null 2>&1; then
    echo "  [PASS] Docker is available"
else
    echo "  [FAIL] Docker not found - this skill requires Docker"
    exit 1
fi

# Check Docker daemon is running
if docker info >/dev/null 2>&1; then
    echo "  [PASS] Docker daemon is running"
else
    echo "  [FAIL] Docker daemon not running"
    exit 1
fi

# Check Dockerfile exists
if [[ -f "$SCRIPT_DIR/docker/Dockerfile.security" ]]; then
    echo "  [PASS] Security Dockerfile exists"
else
    echo "  [FAIL] docker/Dockerfile.security missing"
    exit 1
fi

# Check Tools Command
export TERM=dumb
TOOLS_OUT=$("$SCRIPT_DIR/run.sh" tools 2>&1)
if echo "$TOOLS_OUT" | grep -qi "docker\|tool\|container"; then
    echo "  [PASS] 'tools' command works"
else
    echo "  [FAIL] 'tools' command failed"
    echo "  Output was: $TOOLS_OUT"
    exit 1
fi

# Build Docker image (first-time setup)
echo "  [INFO] Building security Docker image..."
if docker build -t hack-skill-security:latest -f "$SCRIPT_DIR/docker/Dockerfile.security" "$SCRIPT_DIR/docker" >/dev/null 2>&1; then
    echo "  [PASS] Docker image builds successfully"
else
    echo "  [FAIL] Docker image build failed"
    exit 1
fi

# Test nmap in container (scanning localhost is safe)
echo "  [INFO] Testing nmap in container..."
if docker run --rm hack-skill-security:latest nmap --version 2>&1 | grep -q "Nmap"; then
    echo "  [PASS] nmap works in container"
else
    echo "  [FAIL] nmap not working in container"
    exit 1
fi

# Test semgrep in container
echo "  [INFO] Testing semgrep in container..."
if docker run --rm hack-skill-security:latest semgrep --version 2>&1 | grep -qE "[0-9]+\.[0-9]+"; then
    echo "  [PASS] semgrep works in container"
else
    echo "  [FAIL] semgrep not working in container"
    exit 1
fi

# Test bandit in container
echo "  [INFO] Testing bandit in container..."
if docker run --rm hack-skill-security:latest bandit --version 2>&1 | grep -qi "bandit"; then
    echo "  [PASS] bandit works in container"
else
    echo "  [FAIL] bandit not working in container"
    exit 1
fi

echo ""
echo "Result: PASS"
echo "All security tools are available in the Docker container."
