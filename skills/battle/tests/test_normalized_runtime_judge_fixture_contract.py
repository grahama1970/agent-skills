from __future__ import annotations

import hashlib
import json
from pathlib import Path

import jsonschema
import pytest

from battle_skill.normalized_runtime_judge_fixture import normalize_runtime_judge_fixture, validate_normalized_runtime_judge_fixture


SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"


def _schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def test_runtime_judge_fixture_normalizes_docker_receipts_without_judge_overclaim(tmp_path: Path) -> None:
    proof = _write_runtime_source(tmp_path)
    out = tmp_path / "local" / "battle-004-pr4-runtime-judge"
    public = tmp_path / "public" / "battle-004-pr4-runtime-judge"

    fixture = normalize_runtime_judge_fixture(
        proof_dir=proof,
        out_dir=out,
        public_out_dir=public,
        generated_at="2026-07-10T20:30:00Z",
    )

    jsonschema.validate(fixture, _schema("battle.normalized_runtime_judge_fixture.v1.schema.json"))
    report = validate_normalized_runtime_judge_fixture(fixture)
    assert report["status"] == "PASS"
    assert fixture["fixture_kind"] == "pr4_runtime_judge"
    assert fixture["runtime"]["docker"]["image"] == "python:3.12-slim"
    assert fixture["runtime"]["docker"]["network"] == "none"
    assert fixture["runtime"]["docker"]["timeout_seconds"] == 30
    assert fixture["runtime"]["summary"]["target_contact_unproven"] == 1
    assert fixture["runtime"]["specimen_runs"][0]["runtime_status"] == "TARGET_CONTACT_UNPROVEN"
    assert fixture["runtime"]["specimen_runs"][0]["target_contact"]["observed"] is True
    assert fixture["judge"] == {
        "judge_status": "NOT_RUN",
        "judge_progression": ["JUDGE_NOT_RUN"],
        "judge_verified_exploits": 0,
        "does_not_prove": ["exploit success", "Blue block", "Blue bypass", "target contact as exploit success"],
    }
    assert "target_contact_unproven" in fixture["claim_boundary"]["may_claim"]
    assert "exploit_success" in fixture["claim_boundary"]["must_not_claim"]
    assert fixture["claim_boundary"]["target_contact_is_not_exploit_success"] is True
    serialized = json.dumps(fixture, sort_keys=True)
    for marker in ["command-loop", "command-artifacts", "/tmp/", "/mnt/", "/workspace", "provider-workspace"]:
        assert marker not in serialized
    assert _sha256((out / "battle.normalized_runtime_judge_fixture.json").read_bytes()) == _sha256(
        (public / "battle.normalized_runtime_judge_fixture.json").read_bytes()
    )


def test_runtime_judge_fixture_rejects_exploit_success_source_claim(tmp_path: Path) -> None:
    proof = _write_runtime_source(tmp_path, bad_claim=True)

    with pytest.raises(ValueError, match="exploit success"):
        normalize_runtime_judge_fixture(proof_dir=proof, out_dir=tmp_path / "out")


def test_runtime_judge_fixture_rejects_path_leakage() -> None:
    fixture = _minimal_valid_fixture()
    fixture["copy"]["subhead"] = "Leaked /tmp/command-loop path"

    with pytest.raises(ValueError, match="forbidden marker"):
        validate_normalized_runtime_judge_fixture(fixture)


def _write_runtime_source(tmp_path: Path, *, bad_claim: bool = False) -> Path:
    proof = tmp_path / "combiner"
    specimen = proof / "specimens" / "specimen-0004"
    specimen.mkdir(parents=True)
    (specimen / "stdout.txt").write_text("TARGET_CONTACT_UNPROVEN entrypoint=/api/import-zip\n", encoding="utf-8")
    (specimen / "stderr.txt").write_text("debug path /tmp/raw/workspace should redact\n", encoding="utf-8")
    run_receipt = {
        "schema": "battle.exploit_combiner_proof.v1",
        "status": "PASS",
        "battle_id": "battle-004",
        "claims": {"proves": ["Battle ran exploit specimen code in Docker."], "does_not_prove": ["The runnable specimen exploited the target."]},
    }
    scoreboard = {
        "schema": "battle.exploit_combiner_scoreboard.v1",
        "battle_id": "battle-004",
        "generated_specimens": 1,
        "compile_failed": 0,
        "runtime_failed": 0,
        "target_contact_unproven": 1,
        "runnable_unproven": 1,
        "judge_verified_exploits": 0,
        "best_specimen_id": "specimen-0004",
        "verdict": "RUNNABLE_UNPROVEN",
    }
    specimen_receipt = {
        "schema": "battle.exploit_specimen_run.v1",
        "specimen_id": "specimen-0004",
        "status": "SPECIMEN_RUNNABLE_UNPROVEN",
        "compile_ok": True,
        "runtime_ok": True,
        "exit_code": 0,
        "elapsed_seconds": 1.25,
        "stdout_path": "specimens/specimen-0004/stdout.txt",
        "stderr_path": "specimens/specimen-0004/stderr.txt",
        "target_contact": {"observed": True, "entrypoint": "/api/import-zip", "does_not_prove": ["the specimen exploited the target"]},
        "docker_command": [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--user",
            "1000:1000",
            "-v",
            "/tmp/raw:/workspace:rw",
            "-w",
            "/workspace",
            "python:3.12-slim",
            "python",
            "-c",
            "compile-and-run",
        ],
        "proves": ["specimen code was executed in Docker", "specimen contacted the local target surface"],
        "does_not_prove": ["exploit success", "the specimen exploited the target"],
    }
    if bad_claim:
        specimen_receipt["proves"].append("exploit success")
    _write_json(proof / "run-receipt.json", run_receipt)
    _write_json(proof / "scoreboard.json", scoreboard)
    _write_json(specimen / "run-receipt.json", specimen_receipt)
    return proof


def _minimal_valid_fixture() -> dict:
    return {
        "schema": "battle.normalized_runtime_judge_fixture.v1",
        "fixture_kind": "pr4_runtime_judge",
        "battle_id": "battle-004",
        "run_id": "battle-004-pr4-runtime-judge",
        "generated_at": "2026-07-10T20:30:00Z",
        "status": "PASS",
        "mocked": False,
        "live": "local_docker_specimen_fixture",
        "proof_mode": "local_docker_specimen_fixture",
        "runtime": {
            "docker": {"image": "python:3.12-slim", "network": "none", "timeout_seconds": 30},
            "specimen_runs": [
                {
                    "specimen_id": "specimen-0004",
                    "runtime_status": "TARGET_CONTACT_UNPROVEN",
                    "exit_code": 0,
                    "compile_ok": True,
                    "runtime_ok": True,
                    "target_contact": {"observed": True, "status": "TARGET_CONTACT_UNPROVEN", "does_not_prove": ["exploit success"]},
                    "stdout_summary": {},
                    "stderr_summary": {},
                }
            ],
            "summary": {},
        },
        "judge": {"judge_status": "NOT_RUN", "judge_progression": ["JUDGE_NOT_RUN"], "judge_verified_exploits": 0},
        "claim_boundary": {"may_claim": ["docker_specimen_execution_attempted", "container_image_recorded", "container_network_policy_recorded", "timeout_recorded", "exit_code_recorded", "stdout_summary_recorded", "stderr_summary_recorded", "runtime_failed", "runnable_unproven", "target_contact_unproven", "judge_not_run"], "must_not_claim": ["exploit_success", "target_contact_is_exploit_success", "runnable_is_exploit_success", "blue_detection", "blue_bypass", "blue_kill", "blue_block", "judge_success", "packet_level_behavior", "memory_promotion"]},
        "receipt_refs": [],
        "provenance": {"raw_paths_redacted": True},
        "copy": {"headline": "Docker runtime receipts captured", "subhead": "No leak", "status_label": "Runtime unproven; Judge not run", "boundary_notice": "Judge required."},
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()
