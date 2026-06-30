#!/bin/bash
# Continue training from Phase 3 onwards after Phase 2 completes
# Run this after Phase 2 is done

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${HOME}/miniconda3/bin/python"
LOG="/tmp/all_phases_training.log"

cd "$SCRIPT_DIR"

echo "Continuing voice training pipeline at $(date)" | tee -a "$LOG"

# Phase 3: Writers
echo "=== Phase 3: Writers ===" | tee -a "$LOG"
$PYTHON batch_train.py train phase3_writers 2>&1 | tee -a "$LOG"

# Phase 4: Experts
echo "=== Phase 4: Experts ===" | tee -a "$LOG"
$PYTHON batch_train.py train phase4_experts 2>&1 | tee -a "$LOG"

# Phase 5: Historical Known
echo "=== Phase 5: Historical Known ===" | tee -a "$LOG"
$PYTHON batch_train.py train phase5_historical_known 2>&1 | tee -a "$LOG"

# Phase 7: Cinematographers
echo "=== Phase 7: Cinematographers ===" | tee -a "$LOG"
$PYTHON batch_train.py train phase7_cinematographers 2>&1 | tee -a "$LOG"

echo "=== All Phases Complete ===" | tee -a "$LOG"
echo "Completed at $(date)" | tee -a "$LOG"

# Show final status
$PYTHON batch_train.py status
