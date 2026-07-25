#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

uv run --project "$SCRIPT_DIR" python -m py_compile scripts/monitor_herdr.py scripts/herdr_terminal_control.py scripts/cron_support.py scripts/transcript_classifier.py scripts/goal_discovery.py scripts/prompt_builder.py evals/live_herdr_e2e.py evals/live_plugin_e2e.py
uv run --project "$SCRIPT_DIR" pytest -q tests/test_monitor_herdr.py evals/test_real_world_e2e.py
uv run --project "$SCRIPT_DIR" python scripts/monitor_herdr.py probe-text \
  --pane-id w11:pTEST \
  --agent codex \
  --reason early_stop \
  --cwd /tmp \
  --json >/tmp/monitor-herdr-probe.json
python3 - <<'PY'
import json
from pathlib import Path
payload = json.loads(Path("/tmp/monitor-herdr-probe.json").read_text())
assert payload["schema"] == "agent_skills.monitor_herdr.probe.v1"
assert "CAN_SELF_UNBLOCK_BRAVE_SEARCH" in payload["text"]
assert "CAN_SELF_UNBLOCK_WEBGPT" in payload["text"]
assert "Immutable Goal:" in payload["text"]
assert "Ticket Check:" in payload["text"]
assert "$ticket" in payload["text"]
PY
