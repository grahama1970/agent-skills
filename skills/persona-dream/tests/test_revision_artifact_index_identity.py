from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import write_revision_artifact_index as artifact_index  # noqa: E402
from phase_artifact_contract import load_phase_artifact_contract  # noqa: E402


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_phase01_identity_artifacts_have_stable_index_ids(tmp_path: Path) -> None:
    revision_root = tmp_path / "rev_semantic_repair"
    contract = load_phase_artifact_contract()

    for phase_id, phase in contract["phases"].items():
        phase_root = revision_root / f"phase_{phase_id}"
        for requirement in phase["required_artifacts"]:
            path = phase_root / requirement["basenames"][0]
            if requirement.get("semantic_validator") == "storyboard_packet_v1":
                value = {
                    "schema": "persona_dream.storyboard_packet.v1",
                    "status": "PASS_PANEL_REVIEWED",
                    "accepted": True,
                    "panel_count": 1,
                    "panels": [{"panel_id": "sb_001"}],
                }
            else:
                value = {
                    "schema": requirement.get("schema")
                    or f"fixture.{requirement['artifact_id']}.v1",
                    "status": "PASS",
                }
            write_json(path, value)

    write_json(
        revision_root / "revision_manifest.json",
        {
            "schema": "persona_dream.revision_manifest.v1",
            "runId": "pipeline-complete",
            "revisionId": "rev_semantic_repair",
        },
    )
    phase01 = revision_root / "phase_01_idea"
    human_path = phase01 / "human_idea.json"
    lineage_path = phase01 / "idea_lineage_manifest.json"
    write_json(
        human_path,
        {
            "schema": "persona_dream.human_idea.v1",
            "artifact_id": "human_idea",
        },
    )
    write_json(
        lineage_path,
        {
            "schema": "persona_dream.phase_idea_lineage_manifest.v1",
            "artifact_id": "idea_lineage_manifest",
        },
    )

    index = artifact_index.build_index(
        revision_root,
        "pipeline-complete",
        "rev_semantic_repair",
    )

    for artifact_id, path in {
        "human_idea": human_path,
        "idea_lineage_manifest": lineage_path,
    }.items():
        entry = index["artifacts"][artifact_id]
        assert entry["phase_id"] == "01"
        assert entry["relative_path"] == str(path.relative_to(revision_root))
        assert entry["sha256"] == artifact_index.sha256_file(path)
        assert entry["size_bytes"] == path.stat().st_size
