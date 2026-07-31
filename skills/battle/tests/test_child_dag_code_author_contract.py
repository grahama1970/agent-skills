from __future__ import annotations

import hashlib
import json
from pathlib import Path

import jsonschema
import pytest

import battle_skill.child_dag_code_author as code_author
from battle_skill.child_dag_node_adapter import run_node
from battle_skill.exploit_combiner import run_exploit_combiner_proof
from battle_skill.provider_authorship import build_provider_authorship_receipt
from battle_skill.spawn_architect import run_spawn_architect_proof


SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"


@pytest.fixture(autouse=True)
def _isolated_provider_workspace_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(
        "BATTLE_PR3C_PROVIDER_WORKSPACE_ROOT", str(tmp_path / "provider-workspaces")
    )


def _schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def _start_payload(dag_path: Path) -> dict:
    return {
        "schema": "tau.agent_handoff.v1",
        "github": {"repo": "grahama1970/agent-skills", "target": "skills/battle"},
        "goal": {
            "goal_id": "battle-004-child-exploit-specimen",
            "goal_version": 1,
            "goal_hash": "sha256:test",
        },
        "previous_subagent": "human",
        "context": {"summary": "Dispatch test.", "artifacts": [str(dag_path)]},
        "result": {
            "status": "DAG_DISPATCH_REQUESTED",
            "summary": "dispatch",
            "evidence": [],
        },
        "rationale": "test",
        "next_agent": {
            "name": "lineage-summarizer",
            "executor": "local",
            "reason": "test",
        },
        "required_evidence": ["child_knowledge_packet.json"],
        "stop_condition": "test",
    }


def _spawn_architect_dir(tmp_path: Path) -> Path:
    combiner = tmp_path / "combiner"
    run_exploit_combiner_proof(
        battle_id="battle-004",
        out_dir=combiner,
        max_attempts=4,
        docker_image="python:3.12-slim",
        model="not-used",
        scillm_base_url="not-used",
    )
    spawn = tmp_path / "spawn-architect"
    run_spawn_architect_proof(
        battle_id="battle-004", out_dir=spawn, parent_combiner_proof=combiner
    )
    return spawn


def _run_to_method_combiner(tmp_path: Path, monkeypatch) -> dict:
    spawn = _spawn_architect_dir(tmp_path)
    lineage_dir = tmp_path / "artifacts" / "lineage-summarizer"
    monkeypatch.setenv("TAU_HANDOFF_SELECTED_AGENT", "lineage-summarizer")
    lineage_response, lineage_exit = run_node(
        node_id="lineage-summarizer",
        start_payload=_start_payload(spawn / "child-exploit-dag.yaml"),
        artifact_dir=lineage_dir,
    )
    assert lineage_exit == 0
    assert lineage_response is not None

    research_dir = tmp_path / "artifacts" / "research-scout"
    monkeypatch.setenv("TAU_HANDOFF_SELECTED_AGENT", "research-scout")
    research_response, research_exit = run_node(
        node_id="research-scout",
        start_payload=lineage_response,
        artifact_dir=research_dir,
    )
    assert research_exit == 0
    assert research_response is not None

    combiner_dir = tmp_path / "artifacts" / "method-combiner"
    monkeypatch.setenv("TAU_HANDOFF_SELECTED_AGENT", "method-combiner")
    combiner_response, combiner_exit = run_node(
        node_id="method-combiner",
        start_payload=research_response,
        artifact_dir=combiner_dir,
    )
    assert combiner_exit == 0
    assert combiner_response is not None
    return combiner_response


def _evidence_path(receipt: dict, kind: str) -> Path:
    for item in receipt.get("evidence", []):
        if item.get("kind") == kind:
            return Path(item["path"])
    raise AssertionError(f"missing evidence kind: {kind}")


def test_worker_prompt_closes_result_status_vocabulary() -> None:
    task = code_author._worker_task_text(
        {"schema": "battle.exploit_code_author_work_order.v1"}
    )
    assert "status to exactly PASS" in task
    assert "BLOCKED" in task
    assert "NEEDS_REVIEW" in task
    assert "do not use completed" in task
    assert (
        "schema, status, goal_hash, changed_files, artifacts, tests_run, findings"
        in task
    )


def test_code_author_blocks_without_provider_attestation(
    tmp_path: Path, monkeypatch
) -> None:
    combiner_response = _run_to_method_combiner(tmp_path, monkeypatch)

    def fake_launch(*, out_path: Path, **_: object) -> dict:
        payload = {
            "schema": "tau.scillm_worker_launch_receipt.v1",
            "status": "PASS",
            "live": True,
            "provider_live": False,
            "run_id": "run-test",
            "session_id": "session-test",
            "scillm_run_status": "completed",
            "model_provider_route": {
                "surface": "opencode_serve",
                "provider": "test",
                "model": "test-model",
            },
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    monkeypatch.setattr(code_author, "_run_tau_scillm_launch", fake_launch)
    monkeypatch.setenv("TAU_HANDOFF_SELECTED_AGENT", "exploit-code-author")
    artifact_dir = tmp_path / "artifacts" / "exploit-code-author"
    response, exit_code = run_node(
        node_id="exploit-code-author",
        start_payload=combiner_response,
        artifact_dir=artifact_dir,
    )

    assert exit_code == 1
    assert response is not None
    assert response["result"]["status"] == "BLOCKED"
    receipt = json.loads(
        (artifact_dir / "exploit-code-author-node-receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assert receipt["status"] == "BLOCKED"
    assert receipt["verdict"] == "PROVIDER_EXECUTION_ATTESTATION_MISSING"
    assert receipt["fixture_fallback_used"] is False
    assert receipt["agentic"] is False
    workspace = _evidence_path(receipt, "tau-scillm-worker-work-order.json").parents[1]
    assert not (workspace / "outputs" / "exploit_specimen.py").exists()
    boundary = json.loads(
        _evidence_path(receipt, "provider-code-author-boundary-receipt.json").read_text(
            encoding="utf-8"
        )
    )
    jsonschema.validate(
        boundary, _schema("battle.provider_code_author_boundary_receipt.v1.schema.json")
    )
    assert boundary["compile_status"] == "NOT_RUN"
    assert boundary["judge_verified_exploits"] == 0


def test_code_author_uses_configured_provider_workspace_root(
    tmp_path: Path, monkeypatch
) -> None:
    combiner_response = _run_to_method_combiner(tmp_path, monkeypatch)
    provider_root = tmp_path / "provider-workspaces"
    artifact_dir = tmp_path / "artifacts" / "exploit-code-author"
    stale_workspace = code_author._provider_workspace_for(artifact_dir)
    stale_output = stale_workspace / "outputs" / "exploit_specimen.py"
    stale_output.parent.mkdir(parents=True, exist_ok=True)
    stale_output.write_text("print('stale fixture')\n", encoding="utf-8")

    def fake_launch(*, work_order_path: Path, out_path: Path, **_: object) -> dict:
        work_order = json.loads(work_order_path.read_text(encoding="utf-8"))
        repo = Path(work_order["repo"])
        assert repo.is_relative_to(provider_root)
        assert not (repo / "outputs" / "exploit_specimen.py").exists()
        assert "model" not in work_order["model_provider_route"]
        payload = {
            "schema": "tau.scillm_worker_launch_receipt.v1",
            "status": "BLOCKED",
            "live": True,
            "provider_live": False,
            "alert_codes": ["scillm_http_error"],
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    monkeypatch.setenv("BATTLE_PR3C_PROVIDER_WORKSPACE_ROOT", str(provider_root))
    monkeypatch.setattr(code_author, "_run_tau_scillm_launch", fake_launch)
    monkeypatch.setenv("TAU_HANDOFF_SELECTED_AGENT", "exploit-code-author")
    response, exit_code = run_node(
        node_id="exploit-code-author",
        start_payload=combiner_response,
        artifact_dir=artifact_dir,
    )

    assert exit_code == 1
    assert response is not None
    receipt = json.loads(
        (artifact_dir / "exploit-code-author-node-receipt.json").read_text(
            encoding="utf-8"
        )
    )
    workspace = _evidence_path(receipt, "tau-scillm-worker-work-order.json").parents[1]
    assert workspace.is_relative_to(provider_root)
    work_order = json.loads(
        (workspace / "inputs" / "tau-scillm-worker-work-order.json").read_text(
            encoding="utf-8"
        )
    )
    assert Path(work_order["repo"]).is_relative_to(provider_root)


def test_code_author_passes_only_with_provider_bound_output(
    tmp_path: Path, monkeypatch
) -> None:
    combiner_response = _run_to_method_combiner(tmp_path, monkeypatch)
    source = "print('generated candidate')\n"
    source_sha = f"sha256:{hashlib.sha256(source.encode('utf-8')).hexdigest()}"

    def fake_launch(*, work_order_path: Path, out_path: Path, **_: object) -> dict:
        work_order = json.loads(work_order_path.read_text(encoding="utf-8"))
        repo = Path(work_order["repo"])
        outputs = repo / "outputs"
        outputs.mkdir(parents=True, exist_ok=True)
        (outputs / "exploit_specimen.py").write_text(source, encoding="utf-8")
        result = {
            "schema": "tau.scillm_worker_result.v1",
            "status": "PASS",
            "goal_hash": work_order["goal_hash"],
            "changed_files": ["outputs/exploit_specimen.py"],
            "artifacts": ["outputs/exploit_specimen.py"],
            "source_sha256": source_sha,
            "tests_run": [],
            "findings": [],
        }
        (outputs / "provider-worker-result.json").write_text(
            json.dumps(result), encoding="utf-8"
        )
        payload = {
            "schema": "tau.scillm_worker_launch_receipt.v1",
            "status": "PASS",
            "live": True,
            "provider_live": True,
            "run_id": "run-test",
            "session_id": "session-test",
            "provider_request_id": "request-test",
            "provider_response_id": "response-test",
            "provider_call_count": 1,
            "scillm_run_status": "completed",
            "model_provider_route": {
                "surface": "opencode_serve",
                "provider": "test",
                "model": "test-model",
            },
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    def fake_validate(
        *, out_path: Path, work_order_path: Path, result_path: Path, **_: object
    ) -> dict:
        work_order = json.loads(work_order_path.read_text(encoding="utf-8"))
        payload = {
            "schema": "tau.scillm_worker_receipt.v1",
            "status": "PASS",
            "live": True,
            "provider_live": True,
            "provider_request_id": "request-test",
            "provider_response_id": "response-test",
            "provider_call_count": 1,
            "source_sha256": source_sha,
            "goal_hash": work_order["goal_hash"],
            "result_artifacts": ["outputs/exploit_specimen.py"],
            "model_provider_route": {
                "surface": "opencode_serve",
                "provider": "test",
                "model": "test-model",
            },
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    monkeypatch.setattr(code_author, "_run_tau_scillm_launch", fake_launch)
    monkeypatch.setattr(code_author, "_run_tau_scillm_validate", fake_validate)
    monkeypatch.setenv("TAU_HANDOFF_SELECTED_AGENT", "exploit-code-author")
    artifact_dir = tmp_path / "artifacts" / "exploit-code-author"
    response, exit_code = run_node(
        node_id="exploit-code-author",
        start_payload=combiner_response,
        artifact_dir=artifact_dir,
    )

    assert exit_code == 0
    assert response is not None
    assert response["next_agent"]["name"] == "compile-repair"
    receipt = json.loads(
        (artifact_dir / "exploit-code-author-node-receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assert receipt["status"] == "PASS"
    assert receipt["provider_live"] is True
    assert receipt["agentic"] is True
    authorship = json.loads(
        _evidence_path(receipt, "provider-authorship-receipt.json").read_text(
            encoding="utf-8"
        )
    )
    jsonschema.validate(
        authorship, _schema("battle.provider_authorship_receipt.v1.schema.json")
    )
    specimen = json.loads(
        _evidence_path(receipt, "specimen.json").read_text(encoding="utf-8")
    )
    jsonschema.validate(specimen, _schema("battle.exploit_specimen.v2.schema.json"))
    assert specimen["compile_status"] == "NOT_RUN"
    assert "The code compiles." in authorship["claims"]["does_not_prove"]
    assert authorship["provider_request_id"] == "request-test"
    assert authorship["provider_response_id"] == "response-test"
    assert authorship["provider_call_count"] == 1
    assert authorship["transport_source_sha256"] == source_sha
    assert authorship["validation"]["transport_source_hash_matches"] is True


def test_provider_authorship_blocks_without_transport_response_id(
    tmp_path: Path,
) -> None:
    receipt = _provider_authorship_probe(
        tmp_path,
        launch_receipt={"provider_request_id": "request-test", "provider_call_count": 1},
        worker_validation={"provider_request_id": "request-test", "provider_call_count": 1},
    )

    assert receipt["status"] == "BLOCKED"
    assert "PROVIDER_RESPONSE_ID_MISSING" in receipt["errors"]
    assert receipt["claims"]["proves"] == []


def test_provider_authorship_blocks_multiple_provider_calls(
    tmp_path: Path,
) -> None:
    receipt = _provider_authorship_probe(
        tmp_path,
        launch_receipt={
            "provider_request_id": "request-test",
            "provider_response_id": "response-test",
            "provider_call_count": 2,
        },
        worker_validation={
            "provider_request_id": "request-test",
            "provider_response_id": "response-test",
            "provider_call_count": 2,
        },
    )

    assert receipt["status"] == "BLOCKED"
    assert "PROVIDER_CALL_COUNT_INVALID" in receipt["errors"]
    assert receipt["validation"]["provider_call_count_bound"] is False


def test_provider_authorship_blocks_transport_source_hash_mismatch(
    tmp_path: Path,
) -> None:
    receipt = _provider_authorship_probe(
        tmp_path,
        launch_receipt={
            "provider_request_id": "request-test",
            "provider_response_id": "response-test",
            "provider_call_count": 1,
        },
        worker_validation={
            "provider_request_id": "request-test",
            "provider_response_id": "response-test",
            "provider_call_count": 1,
            "source_sha256": "sha256:" + "2" * 64,
        },
    )

    assert receipt["status"] == "BLOCKED"
    assert "PROVIDER_SOURCE_HASH_MISMATCH" in receipt["errors"]
    assert receipt["validation"]["transport_source_hash_matches"] is False


def test_provider_authorship_accepts_tau_attestation_shape(tmp_path: Path) -> None:
    code_sha = "sha256:" + "1" * 64
    response_sha = "sha256:" + "2" * 64
    work_order_sha = "sha256:" + "3" * 64
    attestation = {
        "schema": "tau.provider_execution_attestation.v1",
        "run_id": "oc-test",
        "session_id": "ses-test",
        "work_order_sha256": work_order_sha,
        "result_sha256": "sha256:" + "4" * 64,
        "completion_status": "completed",
        "observed_provider": "opencode-go",
        "observed_model": "opencode-go/kimi-k2.6",
    }

    receipt = build_provider_authorship_receipt(
        out_path=tmp_path / "provider-authorship.json",
        battle_id="battle-004",
        dag_id="dag-1",
        node_id="exploit-code-author",
        child_lane_id="child-1",
        goal_hash="sha256:goal",
        battle_work_order_path=tmp_path / "battle-work-order.json",
        tau_work_order_path=tmp_path / "tau-work-order.json",
        launch_receipt_path=tmp_path / "launch.json",
        worker_result_path=tmp_path / "result.json",
        worker_validation_path=tmp_path / "validation.json",
        artifact_validation={
            "status": "PASS",
            "code_artifact_sha256": code_sha,
            "code_artifact_bytes": 24,
            "errors": [],
        },
        launch_receipt={
            "schema": "tau.scillm_worker_launch_receipt.v1",
            "status": "PASS",
            "live": True,
            "provider_live": True,
            "http_status": 200,
            "run_id": "oc-test",
            "session_id": "ses-test",
            "response_sha256": response_sha,
            "provider_execution_attestation": attestation,
            "model_provider_route": {
                "surface": "opencode_serve",
                "provider": "scillm",
            },
        },
        worker_result={"artifacts": ["outputs/exploit_specimen.py"]},
        worker_validation={
            "schema": "tau.scillm_worker_receipt.v1",
            "status": "PASS",
            "provider_live": True,
            "provider_execution_attestation": attestation,
        },
    )

    assert receipt["status"] == "PASS"
    assert receipt["provider_request_id"] == work_order_sha
    assert receipt["provider_response_id"] == response_sha
    assert receipt["provider_call_count"] == 1
    assert receipt["transport_source_sha256"] == code_sha
    assert receipt["validation"]["transport_source_hash_matches"] is True


def test_scillm_validation_command_binds_launch_receipt(
    tmp_path: Path, monkeypatch
) -> None:
    captured: dict[str, object] = {}

    def fake_run_tau_command(
        *, command: list[str], cwd: Path, expected_json: Path
    ) -> dict:
        captured.update(command=command, cwd=cwd, expected_json=expected_json)
        return {"status": "PASS"}

    monkeypatch.setattr(code_author, "_run_tau_command", fake_run_tau_command)
    launch_receipt = tmp_path / "launch-receipt.json"
    result = code_author._run_tau_scillm_validate(
        tau_root=tmp_path,
        work_order_path=tmp_path / "work-order.json",
        result_path=tmp_path / "worker-result.json",
        out_path=tmp_path / "validation.json",
        launch_receipt_path=launch_receipt,
    )

    assert result == {"status": "PASS"}
    command = captured["command"]
    assert isinstance(command, list)
    assert command[command.index("--launch-receipt") + 1] == str(launch_receipt)


def test_provider_authorship_distinguishes_validation_block_from_missing_attestation(
    tmp_path: Path,
) -> None:
    receipt = build_provider_authorship_receipt(
        out_path=tmp_path / "provider-authorship.json",
        battle_id="battle-004",
        dag_id="dag-1",
        node_id="exploit-code-author",
        child_lane_id="child-1",
        goal_hash="sha256:goal",
        battle_work_order_path=tmp_path / "battle-work-order.json",
        tau_work_order_path=tmp_path / "tau-work-order.json",
        launch_receipt_path=tmp_path / "launch.json",
        worker_result_path=tmp_path / "result.json",
        worker_validation_path=tmp_path / "validation.json",
        artifact_validation={
            "status": "BLOCKED",
            "errors": ["TAU_WORKER_VALIDATION_BLOCKED"],
        },
        launch_receipt={
            "status": "PASS",
            "live": True,
            "provider_live": True,
            "observed_provider": "opencode-go",
            "observed_model": "opencode-go/kimi-k2.6",
        },
        worker_result={"artifacts": ["outputs/exploit_specimen.py"]},
        worker_validation={"status": "BLOCKED", "provider_live": True},
    )

    assert receipt["status"] == "BLOCKED"
    assert receipt["provider_live"] is True
    assert "TAU_WORKER_VALIDATION_BLOCKED" in receipt["errors"]
    assert "PROVIDER_EXECUTION_ATTESTATION_MISSING" not in receipt["errors"]


def _provider_authorship_probe(
    tmp_path: Path,
    *,
    launch_receipt: dict[str, object],
    worker_validation: dict[str, object],
) -> dict[str, object]:
    code_sha = "sha256:" + "1" * 64
    launch = {
        "status": "PASS",
        "live": True,
        "provider_live": True,
        "observed_provider": "opencode-go",
        "observed_model": "opencode-go/kimi-k2.6",
        **launch_receipt,
    }
    validation = {
        "status": "PASS",
        "provider_live": True,
        "source_sha256": code_sha,
        **worker_validation,
    }
    return build_provider_authorship_receipt(
        out_path=tmp_path / "provider-authorship.json",
        battle_id="battle-004",
        dag_id="dag-1",
        node_id="exploit-code-author",
        child_lane_id="child-1",
        goal_hash="sha256:goal",
        battle_work_order_path=tmp_path / "battle-work-order.json",
        tau_work_order_path=tmp_path / "tau-work-order.json",
        launch_receipt_path=tmp_path / "launch.json",
        worker_result_path=tmp_path / "result.json",
        worker_validation_path=tmp_path / "validation.json",
        artifact_validation={
            "status": "PASS",
            "code_artifact_sha256": code_sha,
            "code_artifact_bytes": 24,
            "errors": [],
        },
        launch_receipt=launch,
        worker_result={"artifacts": ["outputs/exploit_specimen.py"]},
        worker_validation=validation,
    )
