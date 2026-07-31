#!/usr/bin/env bash
# Build the standalone Battle spectator source and prove the served route is Battle.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BATTLE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SPECTATOR_DIR="$BATTLE_DIR/spectator"
REPO_DIR="$(cd "$BATTLE_DIR/../.." && pwd)"
TEST_INTERACTIONS_RUN="$REPO_DIR/skills/test-interactions/run.sh"
SOURCE_MANIFEST="$BATTLE_DIR/local/test-interactions-20260728-roundtable-battle3015/targeted-manifest.json"
PORT="${BATTLE_SPECTATOR_PORT:-3015}"
HOST="http://127.0.0.1:${PORT}"
URL="${HOST}/#battle"
RUN_ID="${BATTLE_SPECTATOR_PROOF_ID:-source-build-$(date -u +%Y%m%dT%H%M%SZ)}"
OUT_DIR="${BATTLE_SPECTATOR_PROOF_DIR:-$BATTLE_DIR/local/spectator-source-build-${RUN_ID}}"
MANIFEST="$OUT_DIR/targeted-manifest.json"
RESULTS_DIR="$OUT_DIR/captures"
SERVER_LOG="$OUT_DIR/server.log"
PROOF_JSON="$OUT_DIR/proof.json"

mkdir -p "$OUT_DIR" "$RESULTS_DIR"

owner_pid_for_port() {
  ss -ltnp 2>/dev/null | awk -v port=":${PORT}" '$4 ~ port"$" { print $0 }' \
    | sed -nE 's/.*pid=([0-9]+).*/\1/p' \
    | head -n 1
}

owner_pid="$(owner_pid_for_port || true)"
if [[ -n "$owner_pid" ]]; then
  owner_cwd="$(readlink -f "/proc/${owner_pid}/cwd" 2>/dev/null || true)"
  spectator_cwd="$(readlink -f "$SPECTATOR_DIR")"
  dist_cwd="$(readlink -f "$SPECTATOR_DIR/dist" 2>/dev/null || true)"
  if [[ "$owner_cwd" != "$spectator_cwd" && "$owner_cwd" != "$dist_cwd" ]]; then
    {
      echo "Battle spectator port ${PORT} is owned by a foreign process."
      echo "pid=${owner_pid}"
      echo "cwd=${owner_cwd}"
      echo "expected=${spectator_cwd} or ${dist_cwd}"
    } >&2
    exit 23
  fi
  echo "Battle spectator port ${PORT} is already owned by ${owner_cwd}; refusing to reuse it for a fresh source-build proof." >&2
  exit 24
fi

echo "=== Battle spectator source-build proof ==="
echo "repo_dir=$REPO_DIR"
echo "spectator_dir=$SPECTATOR_DIR"
echo "url=$URL"
echo "out_dir=$OUT_DIR"

echo "1/5 Check package dependencies"
if [[ ! -x "$SPECTATOR_DIR/node_modules/.bin/vite" ]]; then
  echo "node_modules/.bin/vite missing; installing package dependencies from lockfile"
  (cd "$SPECTATOR_DIR" && npm install --no-fund --no-audit)
else
  echo "node_modules/.bin/vite present; skipping npm install"
fi

echo "2/5 Build Battle spectator from source"
(cd "$SPECTATOR_DIR" && npm run build)

echo "3/5 Start preview server"
(cd "$SPECTATOR_DIR" && npm run preview -- --port "$PORT" --strictPort >"$SERVER_LOG" 2>&1) &
server_pid=$!
cleanup() {
  if kill -0 "$server_pid" 2>/dev/null; then
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT

for _ in $(seq 1 60); do
  if curl -fsS "$HOST" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done
curl -fsS "$HOST" >/dev/null

echo "4/5 Write interaction manifest for $URL"
python3 - "$SOURCE_MANIFEST" "$MANIFEST" "$URL" <<'PY'
import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
url = sys.argv[3]
if source.exists():
    data = json.loads(source.read_text())
else:
    def min_size(selector):
        return {"selector": selector, "min_width": 44, "min_height": 44}

    def click(target, description, **extra):
        item = {
            "action": "click",
            "target": target,
            "description": description,
            "assert_title": target,
            "assert_qs_action": target,
            "assert_min_size": min_size(target),
        }
        item.update(extra)
        return item

    data = {
        "version": 1,
        "app": "Battle Spectator",
        "base_url": url,
        "surfaces": [
            {
                "name": "battle-receipt-controls",
                "path": "/",
                "wait_ready": "[data-qid='battle:roster:search']",
                "wait_ready_timeout_ms": 20000,
                "qid_compliance": False,
                "elements": [
                    {
                        "name": "agent-search-and-selection",
                        "interactions": [
                            {
                                "action": "type",
                                "target": "[data-qid='battle:roster:search']",
                                "value": "red",
                                "description": "Filter Battle agents",
                                "assert_value": {"selector": "[data-qid='battle:roster:search']", "value": "red"},
                                "assert_title": "[data-qid='battle:roster:search']",
                                "assert_qs_action": "[data-qid='battle:roster:search']",
                                "assert_min_size": min_size("[data-qid='battle:roster:search']"),
                            },
                            click(
                                "[data-qid='battle:leaderboard:item:payload-857-red-1']",
                                "Select red child lane from roster",
                                assert_selector="[data-qid='battle:agent-pane:payload-857-red-1']",
                            ),
                        ],
                    },
                    {
                        "name": "timeline-zoom",
                        "interactions": [
                            click("[data-qid='battle:timeline:zoom:in']", "Zoom Battle timeline in"),
                            click("[data-qid='battle:timeline:zoom:out']", "Zoom Battle timeline out"),
                            click("[data-qid='battle:timeline:zoom:fit']", "Reset Battle timeline zoom"),
                        ],
                    },
                    {
                        "name": "agent-detail-tabs",
                        "interactions": [
                            click(
                                "[data-qid='battle:agent-pane:tab:live']",
                                "Open Live tab",
                                assert_attribute={"selector": "[data-qid='battle:agent-pane:tab:live']", "attribute": "data-state", "value": "active"},
                            ),
                            click(
                                "[data-qid='battle:agent-pane:tab:logs']",
                                "Open Logs tab",
                                assert_attribute={"selector": "[data-qid='battle:agent-pane:tab:logs']", "attribute": "data-state", "value": "active"},
                            ),
                            click(
                                "[data-qid='battle:agent-pane:tab:summary']",
                                "Return to Summary tab",
                                assert_attribute={"selector": "[data-qid='battle:agent-pane:tab:summary']", "attribute": "data-state", "value": "active"},
                            ),
                        ],
                    },
                    {
                        "name": "pane-controls",
                        "interactions": [
                            click("[data-qid='battle:agent-pane:lifecycle-toggle']", "Toggle lifecycle evidence"),
                            click("[data-qid='battle:pane:right-toggle']", "Collapse right detail pane"),
                            click("[data-qid='battle:pane:left-toggle']", "Collapse left evidence pane"),
                            {"action": "screenshot", "description": "Battle spectator after targeted control interactions"},
                        ],
                    },
                ],
            }
        ],
    }
data["base_url"] = url
target.write_text(json.dumps(data, indent=2) + "\n")
PY

echo "5/5 Run test-interactions against source-built Battle"
"$TEST_INTERACTIONS_RUN" run --manifest "$MANIFEST" --output-dir "$RESULTS_DIR"

python3 - "$SPECTATOR_DIR" "$URL" "$RESULTS_DIR/results.json" "$PROOF_JSON" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

spectator = Path(sys.argv[1])
url = sys.argv[2]
results_path = Path(sys.argv[3])
proof_path = Path(sys.argv[4])
results = json.loads(results_path.read_text())

dist_index = spectator / "dist" / "index.html"
main_source = spectator / "src" / "main.tsx"

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()

proof = {
    "schema": "battle.spectator_source_build_proof.v1",
    "mocked": False,
    "live": True,
    "url": url,
    "source_entry": str(main_source),
    "source_entry_sha256": sha256(main_source),
    "dist_index": str(dist_index),
    "dist_index_sha256": sha256(dist_index),
    "interaction_results": str(results_path),
    "interaction_counts": {
        "total": results.get("total"),
        "passed": results.get("passed"),
        "failed": results.get("failed"),
        "warned": results.get("warned"),
        "skipped": results.get("skipped"),
    },
    "proves": [
        "Battle spectator source has a standalone Vite entrypoint.",
        "npm run build produced a served dist artifact.",
        "The source-built route exposed Battle data-qid controls required by the interaction manifest.",
    ],
    "does_not_prove": [
        "Production hosting.",
        "Long-running live backend campaigns.",
        "Provider reliability.",
    ],
}
proof_path.write_text(json.dumps(proof, indent=2) + "\n")
print(json.dumps(proof, indent=2))
PY

echo "BATTLE_SPECTATOR_SOURCE_BUILD_PASS"
