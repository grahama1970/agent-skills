#!/usr/bin/env bash
# GOAL_V5: 15 autonomous dream cycles, sequential. Operator-authorized 2026-07-23.
cd "$(dirname "$0")/.."
for i in $(seq 1 15); do
  echo "=== batch cycle $i/15 $(date -u +%FT%TZ) ==="
  .venv/bin/python scripts/autonomous_dream_cycle.py || echo "cycle $i FAILED (continuing)"
done
echo "CYCLE_BATCH_COMPLETE"
