from __future__ import annotations

import hashlib
import json
from pathlib import Path

from battle_skill.team_artifact_pipeline import run_team_artifact_pipeline


def test_team_artifact_pipeline_binds_red_hashes_through_docker(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    source.write_text("from app import import_zip\nprint(import_zip)\n", encoding="utf-8")
    provider = _json(tmp_path / "provider.json", {"schema": "tau.subagent_receipt.v1"})
    materialized = _json(tmp_path / "materialized.json", {"status": "PASS"})

    result = run_team_artifact_pipeline(
        battle_id="battle-004",
        run_id="run-1",
        generation=1,
        team="red",
        source_artifact=source,
        provider_receipt=provider,
        materialization_receipt=materialized,
        target_identity_sha256="target-sha",
        out_dir=tmp_path / "pipeline",
    )

    assert result["status"] == "PASS"
    handoff = json.loads(result["handoff_path"].read_text(encoding="utf-8"))
    compile_receipt = json.loads(result["compile_receipt_path"].read_text(encoding="utf-8"))
    selected_sha = hashlib.sha256(result["selected_artifact_path"].read_bytes()).hexdigest()
    assert handoff["selected_artifact_sha256"] == selected_sha
    assert compile_receipt["selected_artifact_sha256"] == selected_sha
    assert handoff["target_identity_sha256"] == "target-sha"
    assert compile_receipt["live"] == "docker_python_compile"


def test_team_artifact_pipeline_blocks_blue_without_public_interface(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    source.write_text("def unrelated():\n    return True\n", encoding="utf-8")
    provider = _json(tmp_path / "provider.json", {"schema": "tau.subagent_receipt.v1"})
    materialized = _json(tmp_path / "materialized.json", {"status": "PASS"})

    result = run_team_artifact_pipeline(
        battle_id="battle-004",
        run_id="run-1",
        generation=1,
        team="blue",
        source_artifact=source,
        provider_receipt=provider,
        materialization_receipt=materialized,
        target_identity_sha256="target-sha",
        out_dir=tmp_path / "pipeline",
    )

    assert result["status"] == "BLOCKED"
    review = json.loads(result["review_receipt_path"].read_text(encoding="utf-8"))
    assert "blue artifact does not preserve import_zip interface" in review["errors"]


def _json(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path
