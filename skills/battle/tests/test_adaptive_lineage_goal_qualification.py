from __future__ import annotations

import json
from pathlib import Path

from battle_skill import adaptive_lineage as al
from battle_skill import arena_live_battle_proof as alb
from battle_skill.adaptive_lineage_goal_qualification import (
    qualify_recovered_adaptive_lineage_run,
)
from test_adaptive_lineage_backend_verifier import _sha, _write_json, _write_minimal_run


def _write_qualifiable_run(root: Path) -> Path:
    run_dir = _write_minimal_run(root)
    campaign_path = run_dir / "campaign-receipt.json"
    campaign = json.loads(campaign_path.read_text(encoding="utf-8"))
    campaign["battle_id"] = "battle-004"
    _write_json(campaign_path, campaign)
    _write_json(
        run_dir / "backend-verification.json",
        {
            "schema": "battle.adaptive_lineage_backend_verification.v1",
            "status": "PASS",
            "mocked": False,
            "live": True,
            "slot_hashes_matched": 4,
            "slot_hashes_required": 4,
            "exact_replays_matched": 2,
            "exact_replays_required": 2,
            "errors": [],
        },
    )
    return run_dir


def test_goal_qualification_writes_deterministic_bound_artifacts(
    tmp_path: Path,
) -> None:
    run_dir = _write_qualifiable_run(tmp_path / "run")
    first = qualify_recovered_adaptive_lineage_run(
        source_root=run_dir,
        proof_dir=tmp_path / "proof-a",
        battle_id="battle-004",
        require_live=True,
        forbid_mock=True,
        require_exact_replay=True,
    )
    second = qualify_recovered_adaptive_lineage_run(
        source_root=run_dir,
        proof_dir=tmp_path / "proof-b",
        battle_id="battle-004",
        require_live=True,
        forbid_mock=True,
        require_exact_replay=True,
    )
    assert first["status"] == "PASS"
    assert second["status"] == "PASS"
    first_qualification = Path(first["qualification_path"]).read_bytes()
    second_qualification = Path(second["qualification_path"]).read_bytes()
    assert first_qualification == second_qualification
    qualification = json.loads(first_qualification)
    assert qualification["schema"] == "battle.adaptive_lineage_goal_qualification.v1"
    assert qualification["status"] == "PASS"
    assert qualification["battle_id"] == "battle-004"
    assert qualification["counts"]["slot_hashes_matched"] == 4
    assert qualification["counts"]["exact_replays_matched"] == 2
    assert {
        "campaign_path",
        "integrity_path",
        "prior_backend_path",
        "verification_path",
    } == {item["name"] for item in qualification["input_receipts"]}


def test_goal_qualification_rejects_slot_tamper(tmp_path: Path) -> None:
    run_dir = _write_qualifiable_run(tmp_path / "slot-tamper")
    slot = (
        run_dir
        / "generation-1"
        / "reviewed"
        / "immutable-slots"
        / "generation-1-red.py"
    )
    slot.write_text("tampered\n", encoding="utf-8")
    result = qualify_recovered_adaptive_lineage_run(
        source_root=run_dir,
        proof_dir=tmp_path / "proof",
        battle_id="battle-004",
        require_live=True,
        forbid_mock=True,
        require_exact_replay=True,
    )
    assert result["status"] == "FAIL"
    verification = json.loads(Path(result["verification_path"]).read_text(encoding="utf-8"))
    assert "slot_hash_mismatch:generation-1:red" in verification["errors"]


def test_goal_qualification_rejects_replay_input_tamper(tmp_path: Path) -> None:
    run_dir = _write_qualifiable_run(tmp_path / "replay-input-tamper")
    blue_exec = next(
        run_dir.glob("generation-2/judge/replays/red-0__blue-0/patched/app.py")
    )
    blue_exec.write_text("def import_zip(): return 'tampered'\n", encoding="utf-8")
    result = qualify_recovered_adaptive_lineage_run(
        source_root=run_dir,
        proof_dir=tmp_path / "proof",
        battle_id="battle-004",
        require_live=True,
        forbid_mock=True,
        require_exact_replay=True,
    )
    assert result["status"] == "FAIL"
    verification = json.loads(Path(result["verification_path"]).read_text(encoding="utf-8"))
    assert any(
        "execution_hash_mismatch:blue_patched_app" in error
        for error in verification["errors"]
    )


def test_goal_qualification_cli_fails_closed_without_source_root(tmp_path: Path) -> None:
    missing = tmp_path / "missing-run"
    proof = tmp_path / "proof"
    result = __import__("subprocess").run(
        [
            str(Path(__file__).resolve().parents[1] / "run.sh"),
            "arena-adaptive-lineage-qualification",
            "battle-004",
            "--source-root",
            str(missing),
            "--proof-dir",
            str(proof),
            "--fresh",
            "--require-live",
            "--forbid-mock",
            "--require-exact-replay",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert (proof / "adaptive-lineage-qualification.json").is_file()
    assert (proof / "adaptive-lineage-verification.json").is_file()
    receipt = json.loads((proof / "adaptive-lineage-qualification.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "FAIL"
    assert any(item["name"] == "campaign_receipt_present" and item["status"] == "FAIL" for item in receipt["checks"])


def test_live_provider_preserves_prior_child_when_operator_retry_blocks(
    tmp_path: Path,
    monkeypatch,
) -> None:
    child_path = tmp_path / "child.py"
    child_path.write_text("print('child')\n", encoding="utf-8")
    parent_receipt = tmp_path / "parent-receipt.json"
    parent_receipt.write_text("{}\n", encoding="utf-8")
    calls = {"count": 0}

    def fake_spawn_child(**kwargs):
        attempt = calls["count"]
        calls["count"] += 1
        out_dir = Path(kwargs["out_dir"])
        manifest_path = out_dir / "tau-live" / "spawn-manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        if attempt == 0:
            manifest = {
                "teams": [
                    {
                        "team": "red",
                        "worker_id": "red-1",
                        "lane_id": "payload-857-red-1",
                        "subagent_receipt": str(tmp_path / "child-receipt.json"),
                        "materialized_artifact": {
                            "status": "PASS",
                            "path": str(child_path),
                            "technique_delta": "method_replace mutation",
                        },
                    }
                ]
            }
        else:
            manifest = {
                "teams": [
                    {
                        "team": "red",
                        "worker_id": "red-1",
                        "materialized_artifact": {
                            "status": "BLOCKED",
                            "path": None,
                            "reason": "red_artifact_missing_local_app_import",
                        },
                    }
                ]
            }
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return manifest_path

    def fake_delta(**kwargs):
        return {
            "status": "FAIL",
            "operator_consistent": False,
            "changed_dimensions": ["success_oracle"],
            "reasons": ["synthetic retry trigger"],
        }

    def fake_judge(self, *, red_entry, **kwargs):
        assert red_entry["path"] == str(child_path)
        return {
            "vulnerable_original_confirmed": True,
            "patched_bypass": False,
            "duration_seconds": 0.1,
        }

    monkeypatch.setattr(alb, "_run_tau_spawn_child", fake_spawn_child)
    monkeypatch.setattr(al, "validate_technique_delta", fake_delta)
    monkeypatch.setattr(al.LiveTauSpecimenProvider, "_judge", fake_judge)

    provider = al.LiveTauSpecimenProvider(
        out_dir=tmp_path,
        battle_id="battle-004",
        run_id="test-run",
        scenario_id="arena-zip-slip-import-001",
        context_path=tmp_path / "missing-context.json",
        max_operator_retries=1,
    )
    provider._blue_entry = {"path": str(tmp_path / "blue.py")}
    provider._materialized["G0"] = {
        "subagent_receipt": str(parent_receipt),
        "evidence_packet_ref": "test-run:battle.parent_evidence_packet.v1:G0",
    }

    result = provider.request(
        stage="G1-A",
        context={
            "parent_specimen": {
                "specimen_id": "G0",
                "exploit_py": "print('parent')\n",
                "source_sha256": "parent-sha",
                "mutation_operator": None,
                "technique_delta": "seed",
                "judge_outcome": {"vulnerable_original_confirmed": True},
            }
        },
    )

    assert result["specimen_id"] == "G1-A"
    assert result["operator_retries"] == 1
    assert result["exploit_py"] == "print('child')\n"


def test_live_provider_returns_blocked_specimen_when_first_spawn_has_no_artifact(
    tmp_path: Path,
    monkeypatch,
) -> None:
    parent_receipt = tmp_path / "parent-receipt.json"
    parent_receipt.write_text("{}\n", encoding="utf-8")

    def fake_spawn_child(**kwargs):
        out_dir = Path(kwargs["out_dir"])
        manifest_path = out_dir / "tau-live" / "spawn-manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest = {
            "teams": [
                {
                    "team": "red",
                    "worker_id": "red-1",
                    "materialized_artifact": {
                        "status": "BLOCKED",
                        "path": None,
                        "reason": "red_artifact_missing_local_app_import",
                    },
                }
            ]
        }
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return manifest_path

    monkeypatch.setattr(alb, "_run_tau_spawn_child", fake_spawn_child)

    provider = al.LiveTauSpecimenProvider(
        out_dir=tmp_path,
        battle_id="battle-004",
        run_id="test-run",
        scenario_id="arena-zip-slip-import-001",
        context_path=tmp_path / "missing-context.json",
        max_operator_retries=1,
    )
    provider._blue_entry = {"path": str(tmp_path / "blue.py")}
    provider._materialized["G0"] = {
        "subagent_receipt": str(parent_receipt),
        "evidence_packet_ref": "test-run:battle.parent_evidence_packet.v1:G0",
    }

    result = provider.request(
        stage="G1-A",
        context={
            "parent_specimen": {
                "specimen_id": "G0",
                "exploit_py": "print('parent')\n",
                "source_sha256": "parent-sha",
                "mutation_operator": None,
                "technique_delta": "seed",
                "judge_outcome": {"vulnerable_original_confirmed": True},
            }
        },
    )

    assert result["specimen_id"] == "G1-A"
    assert result["materialization_status"] == "BLOCKED"
    assert result["materialization_blocker"] == "red_artifact_missing_local_app_import"
    assert result["judge_attempts"] == 0
    assert result["exploit_py"] == ""
