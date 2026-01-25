#!/bin/bash
set -euo pipefail

# Rate Limit Recovery Skill Runner
# Collects recent transcripts and logging information from rate-limited agent platforms

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_NAME="rate-limit-recovery"
PYTHON_SCRIPT="${SCRIPT_DIR}/rate_limit_recovery.py"

# Source common utilities
source "${SCRIPT_DIR}/../common.sh" 2>/dev/null || {
    echo "Warning: common.sh not found, continuing without shared utilities"
}

# Function to show usage
show_usage() {
    cat << EOF
Usage: ./run.sh recover [OPTIONS]

Collect recent transcripts and logging information from agent platforms that were rate-limited mid-task.

OPTIONS:
    --platform PLATFORM     Specific platform to recover from (codex, claude, pi, antigravity)
    --session-id ID         Session ID for recovery
    --workspace PATH        Workspace path for Claude recovery
    --task-id ID           Task ID for Antigravity recovery
    --since TIME           Start time for recovery (YYYY-MM-DD HH:MM)
    --until TIME           End time for recovery (YYYY-MM-DD HH:MM)
    --verbose              Include verbose output
    --include-debug        Include debug logs
    --format FORMAT        Output format: json, markdown, txt (default: markdown)
    --output FILE          Output file path
    --help                 Show this help message

EXAMPLES:
    # Auto-detect platform and recover
    ./run.sh recover

    # Recover from specific platform
    ./run.sh recover --platform codex
    ./run.sh recover --platform claude --workspace /path/to/project
    ./run.sh recover --platform pi --session-id recent
    ./run.sh recover --platform antigravity --task-id task456

    # Export to specific format
    ./run.sh recover --format json --output recovery_report.json
    ./run.sh recover --format markdown --verbose

    # Time-based recovery
    ./run.sh recover --since "2024-01-20 14:30" --until "2024-01-20 15:00"

EOF
}

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required but not installed."
    exit 1
fi

# Check if the Python script exists
if [[ ! -f "${PYTHON_SCRIPT}" ]]; then
    echo "Error: Python script not found at ${PYTHON_SCRIPT}"
    exit 1
fi

# Parse command line arguments
COMMAND=""
ARGS=()

while [[ $# -gt 0 ]]; do
    case $1 in
        recover)
            COMMAND="recover"
            shift
            ;;
        --help|-h)
            show_usage
            exit 0
            ;;
        *)
            ARGS+=("$1")
            shift
            ;;
    esac
done

# Default to recover command if none specified
if [[ -z "${COMMAND}" ]]; then
    COMMAND="recover"
fi

# Run the Python script with the provided arguments
echo "Running rate limit recovery skill..."
echo "Platform: ${ARGS[*]}"

# Change to the skill directory to ensure relative paths work correctly
cd "${SCRIPT_DIR}"

# Execute the Python script
python3 "${PYTHON_SCRIPT}" "${COMMAND}" "${ARGS[@]}"

EXIT_CODE=$?

if [[ $EXIT_CODE -eq 0 ]]; then
    echo "Rate limit recovery completed successfully."
else
    echo "Rate limit recovery failed with exit code $EXIT_CODE."
    exit $EXIT_CODE
fi