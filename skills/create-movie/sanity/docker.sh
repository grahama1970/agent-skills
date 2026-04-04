#!/usr/bin/env bash
#
# Sanity script: Docker availability
# Purpose: Verify Docker is available for isolated code execution
# Exit codes: 0=PASS, 1=FAIL
#
set -e

echo "Checking Docker availability..."

# Check docker command exists
if ! command -v docker &> /dev/null; then
    echo "FAIL: Docker not installed"
    exit 1
fi

# Check docker daemon is running
if ! docker info &> /dev/null; then
    echo "FAIL: Docker daemon not running"
    exit 1
fi

# Check we can run a container
if ! docker run --rm hello-world &> /dev/null; then
    echo "FAIL: Cannot run Docker containers"
    exit 1
fi

echo "PASS: Docker is available and working"
exit 0
