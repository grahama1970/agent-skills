#!/usr/bin/env bash
# Combined plain-text watchdog monitor: queue table + phart live DAG.
# Renders in any terminal (iPad/Blink safe: no graphics protocol).
#
# One frame:  monitor-text.sh
# Live pane:  watch -n 15 -t monitor-text.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python3 "$HERE/queue-view.py"
echo
"$HERE/watch-live.sh" --once --no-chart 2>/dev/null || "$HERE/watch-live.sh" --once 2>/dev/null | head -12
