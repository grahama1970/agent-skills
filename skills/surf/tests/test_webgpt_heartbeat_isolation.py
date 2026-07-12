import json
from pathlib import Path

from skills.surf.scripts.lib.webgpt_heartbeat import write_heartbeat


def test_new_sentinel_discards_stale_assistant_observation(tmp_path: Path) -> None:
    path = tmp_path / "webgpt_heartbeat.json"
    path.write_text(json.dumps({
        "schema": "surf.webgpt_heartbeat.v1",
        "sentinel": "old-sentinel",
        "assistant_tail_excerpt": "stale response",
        "assistant_observation": {"message_id": "old-turn"},
    }))

    write_heartbeat(
        tmp_path,
        phase="prompt_prepared",
        page_state="waiting",
        sentinel="new-sentinel",
    )

    payload = json.loads(path.read_text())
    assert payload["sentinel"] == "new-sentinel"
    assert "assistant_tail_excerpt" not in payload
    assert "assistant_observation" not in payload


def test_explicit_heartbeat_path_isolates_runs_in_same_directory(tmp_path: Path) -> None:
    first = tmp_path / "first.meta.heartbeat.json"
    second = tmp_path / "second.meta.heartbeat.json"

    write_heartbeat(tmp_path, heartbeat_path=first, phase="submitted", page_state="generating", sentinel="first")
    write_heartbeat(tmp_path, heartbeat_path=second, phase="submitted", page_state="generating", sentinel="second")

    assert json.loads(first.read_text())["sentinel"] == "first"
    assert json.loads(second.read_text())["sentinel"] == "second"
