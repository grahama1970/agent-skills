#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
cat > "$TMP_DIR/brief.md" <<'EOF'
# Sparta Chat
Create a chat-first operator interface with structured run cards, an artifact inspector,
and explicit approval controls. Avoid dashboard theater.
EOF
"$SCRIPT_DIR/run.sh" init \
  --brief "$TMP_DIR/brief.md" \
  --surface sparta-chat \
  --target-repo /tmp/sparta \
  --output "$TMP_DIR/run" >/dev/null
"$SCRIPT_DIR/run.sh" validate --run "$TMP_DIR/run" >/dev/null
"$SCRIPT_DIR/run.sh" record --run "$TMP_DIR/run" --node brief.normalize --state PASS --artifact brief/design-brief.md >/dev/null
python3 - "$TMP_DIR/run/pipeline.json" <<'PY'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["schema"] == "interface_design.run.v1"
assert any(node["id"] == "research.github" for node in payload["nodes"])
assert any(node["id"] == "research.brave" for node in payload["nodes"])
assert any(node["id"] == "human.approval" for node in payload["nodes"])
PY
echo "interface-design sanity: PASS"
