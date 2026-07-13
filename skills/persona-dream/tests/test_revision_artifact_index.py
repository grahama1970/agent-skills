from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from phase_artifact_contract import load_phase_artifact_contract  # noqa: E402
from write_revision_artifact_index import verify_index, write_index  # noqa: E402


def write_revision(root: Path) -> None:
    contract = load_phase_artifact_contract()
    for phase_id, phase in contract["phases"].items():
        phase_root = root / f"phase_{phase_id}"
        phase_root.mkdir(parents=True, exist_ok=True)
        for requirement in phase["required_artifacts"]:
            value: dict[str, object] = {}
            if requirement["artifact_id"] == "storyboard_packet":
                value = {
                    "schema": "persona_dream.storyboard_packet.v1",
                    "status": "PASS_PANEL_REVIEWED",
                    "accepted": True,
                    "panel_count": 1,
                    "panels": [{"panel_id": "sb_001"}],
                }
            (phase_root / requirement["basenames"][0]).write_text(
                json.dumps(value), encoding="utf-8"
            )
    frames = root / "phase_07" / "generated_storyboard_frames"
    frames.mkdir(parents=True)
    (frames / "sb_001_start_frame.png").write_bytes(b"png-fixture")


def test_index_binds_required_and_media_artifacts(tmp_path: Path) -> None:
    write_revision(tmp_path)
    index_path = tmp_path / "revision_artifact_index.json"
    index = write_index(tmp_path, index_path, "pipeline-complete", "rev_test")
    assert index["required_artifact_count"] == 16
    assert index["artifacts"]["storyboard_packet"]["consumer_contract"] == "dream_storyboard_workspace_v1"
    frame = next(value for value in index["artifacts"].values() if value["relative_path"].endswith("sb_001_start_frame.png"))
    assert "accepted_frame" in frame["roles"]
    receipt = verify_index(tmp_path, index_path)
    assert receipt["status"] == "PASS_REVISION_ARTIFACT_INDEX"


def test_index_verification_blocks_tampered_artifact(tmp_path: Path) -> None:
    write_revision(tmp_path)
    index_path = tmp_path / "revision_artifact_index.json"
    write_index(tmp_path, index_path, "pipeline-complete", "rev_test")
    (tmp_path / "phase_02" / "story_contract.json").write_text('{"tampered":true}', encoding="utf-8")
    with pytest.raises(ValueError, match="BLOCKED_REVISION_ARTIFACT_INDEX_MISMATCH"):
        verify_index(tmp_path, index_path)


def test_index_writer_blocks_semantically_invalid_storyboard(tmp_path: Path) -> None:
    write_revision(tmp_path)
    (tmp_path / "phase_07" / "storyboard_packet.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="BLOCKED_REVISION_ARTIFACT_CONTRACT"):
        write_index(tmp_path, tmp_path / "revision_artifact_index.json", "pipeline-complete", "rev_test")
