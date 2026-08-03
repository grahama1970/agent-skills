from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from dewey_repair_queue import claim_one, load_latest, update_issue


def load_monitor_queue_module():
    path = Path("/home/graham/workspace/experiments/memory/scripts/validation/monitor_sparta_repair_queue.py")
    spec = importlib.util.spec_from_file_location("monitor_sparta_repair_queue", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_monitor_queue_output_can_be_claimed_and_updated(tmp_path: Path) -> None:
    monitor_queue = load_monitor_queue_module()
    queue = tmp_path / "repair_queue.jsonl"
    health = {
        "checks": [
            {
                "ok": False,
                "dimension": "inline_embedding_policy",
                "by_collection": [{"collection": "sparta_controls", "inline_embedding_arrays": 2}],
            },
            {
                "ok": False,
                "dimension": "embedding_gaps",
                "gaps": {"sparta_url_knowledge": {"missing": 3}},
            },
        ]
    }
    issues = monitor_queue.issues_from_health(health, source="unit", limit=1)
    monitor_queue.append_issues(queue, issues)

    claimed = claim_one(queue, run_id="run-compat")

    assert claimed is not None
    assert claimed["schema_version"] == 1
    assert claimed["lane"] == "inline_embedding_policy"
    update_issue(queue, claimed, status="DONE", result={"ok": True})
    latest = load_latest(queue)
    assert latest[claimed["issue_id"]]["status"] == "DONE"
    ready = [issue for issue in latest.values() if issue.get("status") == "READY"]
    assert len(ready) == 1
    assert ready[0]["lane"] == "missing_qdrant_embeddings"
