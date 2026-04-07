#!/usr/bin/env bash
# nightly_dream.sh — Scheduled nightly dream generation for personas
#
# Called by ~/.pi/scheduler to create a 30-second surreal dream video
# using day residue from memory. Output goes to 12TB storage per persona.
#
# Usage:
#   bash nightly_dream.sh                              # Horus (default)
#   bash nightly_dream.sh --persona embry              # Embry
#   bash nightly_dream.sh --duration 60                # override duration
#   bash nightly_dream.sh --persona horus --persona embry  # both
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATE="$(date +%Y-%m-%d)"

# Defaults
DURATION="${DURATION:-30}"
PERSONAS=()

# Parse CLI overrides
while [[ $# -gt 0 ]]; do
    case "$1" in
        --duration) DURATION="$2"; shift 2 ;;
        --persona) PERSONAS+=("$2"); shift 2 ;;
        *) shift ;;
    esac
done

# Default to Horus if no persona specified
if [[ ${#PERSONAS[@]} -eq 0 ]]; then
    PERSONAS=("horus")
fi

# Storage base on 12TB drive
STORAGE_BASE="/mnt/storage12tb/media/personas"

run_dream() {
    local persona="$1"
    local dreams_dir="${STORAGE_BASE}/${persona}/dreams"
    local work_dir="${dreams_dir}/${DATE}"

    mkdir -p "$work_dir"

    echo "[nightly-dream] Persona: ${persona}"
    echo "[nightly-dream] Date: ${DATE}"
    echo "[nightly-dream] Duration: ${DURATION}s"
    echo "[nightly-dream] Output: ${work_dir}"

    # dream.py is a single command (no subcommand) with the full persistence loop:
    #   fetch_day_residue → scenes → video → store_dream → reflection → archive
    uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/dream.py" \
        --persona "$persona" \
        --duration "$DURATION" \
        2>&1 | tee "${work_dir}/dream.log"

    local exit_code=${PIPESTATUS[0]}
    if [[ $exit_code -eq 0 ]]; then
        echo "[nightly-dream] ✓ ${persona} dream complete: ${work_dir}"
    else
        echo "[nightly-dream] ✗ ${persona} dream failed (exit ${exit_code})" >&2
    fi
    return $exit_code
}

# Run dreams for each persona
FAILED=0
for persona in "${PERSONAS[@]}"; do
    if ! run_dream "$persona"; then
        FAILED=$((FAILED + 1))
    fi
done

if [[ $FAILED -gt 0 ]]; then
    echo "[nightly-dream] ${FAILED}/${#PERSONAS[@]} dreams failed" >&2
    exit 1
fi

echo "[nightly-dream] All ${#PERSONAS[@]} dreams complete"
