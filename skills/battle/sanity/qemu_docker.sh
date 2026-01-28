#!/bin/bash
# Sanity Script: QEMU inside Docker
# PURPOSE: Verify Docker can run QEMU for isolated battles
# DEPENDENCIES: docker
# EXIT CODES: 0=PASS, 1=FAIL, 42=CLARIFY

set -e

echo "============================================================"
echo "SANITY CHECK: QEMU inside Docker"
echo "============================================================"

# Check Docker installed
echo ""
echo "Checking for Docker..."

if command -v docker &> /dev/null; then
    DOCKER_VERSION=$(docker --version 2>&1 || echo "unknown")
    echo "✅ Found Docker: $DOCKER_VERSION"
else
    echo "❌ FAIL: Docker not found"
    echo "   Install Docker: https://docs.docker.com/engine/install/"
    exit 1
fi

# Check Docker daemon running
echo ""
echo "Checking Docker daemon..."

if docker info &> /dev/null; then
    echo "✅ Docker daemon is running"
else
    echo "❌ FAIL: Docker daemon not running"
    echo "   Start with: sudo systemctl start docker"
    exit 1
fi

# Test if we can run a container
echo ""
echo "Testing container execution..."

if docker run --rm hello-world &> /dev/null; then
    echo "✅ Can run containers"
else
    echo "❌ FAIL: Cannot run containers"
    echo "   Check Docker permissions: sudo usermod -aG docker $USER"
    exit 1
fi

# Test if we can run QEMU inside Docker
echo ""
echo "Testing QEMU inside Docker..."

# Create a minimal Dockerfile in temp directory
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

cat > "$TEMP_DIR/Dockerfile" << 'EOF'
FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends \
    qemu-system-arm qemu-utils \
    && rm -rf /var/lib/apt/lists/*
CMD ["qemu-system-arm", "--version"]
EOF

echo "  Building test image..."
if docker build -t battle-qemu-test "$TEMP_DIR" &> /dev/null; then
    echo "  ✅ Image built successfully"
else
    echo "  ❌ Failed to build image"
    exit 1
fi

echo "  Running QEMU version check in container..."
QEMU_OUTPUT=$(docker run --rm battle-qemu-test 2>&1)
if echo "$QEMU_OUTPUT" | grep -q "QEMU"; then
    echo "  ✅ QEMU runs inside container"
    echo "     $QEMU_OUTPUT" | head -1
else
    echo "  ❌ QEMU failed to run in container"
    exit 1
fi

# Cleanup test image
echo ""
echo "Cleaning up..."
docker rmi battle-qemu-test &> /dev/null || true

echo ""
echo "============================================================"
echo "✅ PASS: QEMU can run inside Docker containers"
echo "============================================================"
echo ""
echo "Ready for containerized battle operations."
exit 0
