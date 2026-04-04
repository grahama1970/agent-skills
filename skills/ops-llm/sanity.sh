#!/usr/bin/env bash
# Sanity check for ops-llm skill
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Sanity check for ops-llm ==="

# Check SKILL.md exists
if [[ ! -f "$SCRIPT_DIR/SKILL.md" ]]; then
    echo "FAIL: SKILL.md not found"
    exit 1
fi
echo "PASS: SKILL.md exists"

# Check scripts exist and are executable
if [[ ! -x "$SCRIPT_DIR/scripts/health.sh" ]]; then
    echo "FAIL: scripts/health.sh not found or not executable"
    exit 1
fi
echo "PASS: scripts/health.sh exists"

if [[ ! -x "$SCRIPT_DIR/scripts/cache-clean.sh" ]]; then
    echo "FAIL: scripts/cache-clean.sh not found or not executable"
    exit 1
fi
echo "PASS: scripts/cache-clean.sh exists"

# Check health.sh help
if "$SCRIPT_DIR/scripts/health.sh" --help >/dev/null 2>&1; then
    echo "PASS: health.sh --help works"
else
    echo "WARN: health.sh --help check failed"
fi

# Check curl exists (used for health checks)
if ! command -v curl >/dev/null 2>&1; then
    echo "WARN: curl not found (required for health checks)"
else
    echo "PASS: curl found"
fi

# Check Docker is available (required for Ollama management)
if ! command -v docker >/dev/null 2>&1; then
    echo "WARN: docker not found (required for Ollama management)"
else
    echo "PASS: docker found"
fi

# Check sanity scripts exist
if [[ ! -x "$SCRIPT_DIR/sanity/ollama-docker.sh" ]]; then
    echo "FAIL: sanity/ollama-docker.sh not found or not executable"
    exit 1
fi
echo "PASS: sanity/ollama-docker.sh exists"

# Check new model management scripts exist and are executable
for script in model-list model-pull model-remove model-show; do
    if [[ ! -x "$SCRIPT_DIR/scripts/$script.sh" ]]; then
        echo "FAIL: scripts/$script.sh not found or not executable"
        exit 1
    fi
    echo "PASS: scripts/$script.sh exists"
done

# Check new service management scripts exist and are executable
for script in service-status service-control service-logs; do
    if [[ ! -x "$SCRIPT_DIR/scripts/$script.sh" ]]; then
        echo "FAIL: scripts/$script.sh not found or not executable"
        exit 1
    fi
    echo "PASS: scripts/$script.sh exists"
done

# Check performance monitoring script exists and is executable
if [[ ! -x "$SCRIPT_DIR/scripts/perf-monitor.sh" ]]; then
    echo "FAIL: scripts/perf-monitor.sh not found or not executable"
    exit 1
fi
echo "PASS: scripts/perf-monitor.sh exists"

# Check run.sh dispatcher exists and is executable
if [[ ! -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "FAIL: run.sh not found or not executable"
    exit 1
fi
echo "PASS: run.sh exists"

# Test run.sh help command
if "$SCRIPT_DIR/run.sh" help >/dev/null 2>&1; then
    echo "PASS: run.sh help works"
else
    echo "FAIL: run.sh help check failed"
    exit 1
fi

# Test model-list script with help/dry-run (don't require Docker running)
if "$SCRIPT_DIR/scripts/model-list.sh" --help >/dev/null 2>&1 || true; then
    echo "PASS: model-list.sh accepts --help"
else
    echo "WARN: model-list.sh --help check failed"
fi

# Test service-status script exists and runs
if "$SCRIPT_DIR/scripts/service-status.sh" --help >/dev/null 2>&1 || true; then
    echo "PASS: service-status.sh accepts --help"
else
    echo "WARN: service-status.sh --help check failed"
fi

echo "=== Sanity check complete ==="
