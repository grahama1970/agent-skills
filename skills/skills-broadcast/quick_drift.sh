#!/bin/bash
# DEPRECATED: This drift assessment tool is no longer needed.
# All skill directories are now symlinks to canonical (.pi/skills/).
# With symlinks, drift is impossible — all paths resolve to the same files.
# Deleted 2026-02-12 as part of symlink migration cleanup.
# Use: ./run.sh status  (to verify symlink health)
echo "DEPRECATED: Use ./run.sh status instead. Drift tools removed — symlinks make drift impossible."
exit 0
