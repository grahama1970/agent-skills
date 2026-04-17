#!/bin/bash
# Wait for Phase 2 to complete, then continue with remaining phases
# This runs in background and chains all remaining training

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG="/tmp/all_phases_training.log"

echo "Waiting for Phase 2 (PID 548861) to complete..." | tee -a "$LOG"

# Wait for Phase 2 batch_train to finish
while ps -p 548861 > /dev/null 2>&1; do
    sleep 60
done

echo "Phase 2 completed at $(date). Starting remaining phases..." | tee -a "$LOG"

# Run remaining phases
chmod +x "$SCRIPT_DIR/continue_training.sh"
"$SCRIPT_DIR/continue_training.sh"
