from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import jsonschema
import pytest

from battle_skill.normalized_compile_fixture import normalize_pr3d_compile_fixture, validate_normalized_compile_fixture


SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"


def _schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def test_pr3d_compile_fixture_normalizes_compile_failure_without_runtime_paths(tmp_path: Path) -> None:
    live_tau = _write_pr3d_source_run(tmp_path)
    out = tmp_path / "local" / "battle-004-pr3d-compile"
    public = tmp_path / "public" / "battle-004-pr3d-compile"

    fixture = normalize_pr3d_compile_fixture(
        live_tau_canary=live_tau,
        out_dir=out,
        public_out_dir=public,
        generated_at="2026-07-10T19:00:00Z",
    )

    jsonschema.validate(fixture, _schema("battle.normalized_compile_fixture.v1.schema.json"))
    report = validate_normalized_compile_fixture(fixture)
    assert report["status"] == "PASS"
    assert fixture["fixture_kind"] == "pr3d_compile_repair"
    assert fixture["node_status"] == {
        "lineage-summarizer": "PASS",
        "research-scout": "PASS",
        "method-combiner": "PASS",
        "exploit-code-author": "PASS",
        "compile-repair": "BLOCKED",
    }
    assert fixture["compile"]["compile_attempted"] is True
    assert fixture["compile"]["compile_failed"] is True
    assert fixture["compile"]["compile_passed"] is False
    assert fixture["compile"]["status"] == "FAILED"
    assert fixture["compile"]["stderr_summary"]["available"] is True
    assert fixture["compile"]["stderr_summary"]["redacted"] is True
    assert "SyntaxError" in " ".join(fixture["compile"]["stderr_summary"]["lines"])
    assert fixture["repair"]["repair_attempted"] is True
    assert fixture["repair"]["repair_exhausted"] is False
    assert fixture["execution_boundary"] == {
        "runtime_status": "NOT_RUN",
        "target_contact": "NOT_RUN",
        "judge_status": "NOT_RUN",
        "judge_verified_exploits": 0,
        "packet_behavior": "NOT_RUN",
        "memory_promotion": "NOT_RUN",
    }
    assert "compile_attempted" in fixture["claim_boundary"]["may_claim"]
    assert "compile_failed" in fixture["claim_boundary"]["may_claim"]
    assert "runnable" in fixture["claim_boundary"]["must_not_claim"]
    assert "exploit_success" in fixture["claim_boundary"]["must_not_claim"]
    assert fixture["claim_boundary"]["compile_passed_is_not_runnable"] is True
    assert [item["version_id"] for item in fixture["specimen_versions"]] == ["v001", "v002"]
    assert fixture["specimen_versions"][0]["compile_status"] == "NOT_RUN"
    assert fixture["specimen_versions"][1]["compile_status"] == "FAILED"
    assert fixture["selected_version"]["version_id"] == "v002"

    serialized = json.dumps(fixture, sort_keys=True)
    for marker in ["command-loop", "command-artifacts", "/tmp/", "/mnt/", "provider-workspace", "pr3c-provider-workspaces"]:
        assert marker not in serialized
    assert "[redacted-path]" in serialized

    local_fixture = out / "battle.normalized_compile_fixture.json"
    public_fixture = public / "battle.normalized_compile_fixture.json"
    assert local_fixture.exists()
    assert public_fixture.exists()
    assert _sha256(local_fixture.read_bytes()) == _sha256(public_fixture.read_bytes())
    source_index = json.loads((out / "source-receipt-index.json").read_text(encoding="utf-8"))
    source_serialized = json.dumps(source_index, sort_keys=True)
    assert source_index["source_receipt_count"] == len(fixture["receipt_refs"])
    assert "command-loop" not in source_serialized
    assert "/tmp/" not in source_serialized


def test_pr3d_compile_fixture_rejects_runtime_claim(tmp_path: Path) -> None:
    live_tau = _write_pr3d_source_run(tmp_path, runtime_status="RUN")

    with pytest.raises(ValueError, match="runtime_status must be NOT_RUN"):
        normalize_pr3d_compile_fixture(live_tau_canary=live_tau, out_dir=tmp_path / "out")


def test_pr3d_compile_fixture_rejects_path_leakage() -> None:
    fixture = _minimal_valid_fixture()
    fixture["copy"]["subhead"] = "Leaked /tmp/command-loop path"

    with pytest.raises(ValueError, match="forbidden marker"):
        validate_normalized_compile_fixture(fixture)


def test_pr3d_compile_fixture_normalizes_live_compile_pass_spelling(tmp_path: Path) -> None:
    live_tau = _write_pr3d_source_run(
        tmp_path,
        compile_receipt_status="PASS",
        compile_verdict="PASS",
        compile_status="PASS",
        compile_errors=[],
        repaired_text="print('candidate only')\n",
    )

    fixture = normalize_pr3d_compile_fixture(
        live_tau_canary=live_tau,
        out_dir=tmp_path / "local" / "battle-004-pr3d-compile",
        generated_at="2026-07-17T12:00:00Z",
    )

    assert fixture["node_status"]["compile-repair"] == "PASS"
    assert fixture["compile"]["status"] == "PASSED"
    assert fixture["compile"]["compile_passed"] is True
    assert fixture["compile"]["compile_failed"] is False
    assert fixture["specimen_versions"][1]["compile_status"] == "PASSED"
    assert validate_normalized_compile_fixture(fixture)["status"] == "PASS"


def _write_pr3d_source_run(
    tmp_path: Path,
    *,
    runtime_status: str = "NOT_RUN",
    compile_receipt_status: str = "BLOCKED",
    compile_verdict: str = "COMPILE_FAILED",
    compile_status: str = "FAILED",
    compile_errors: list[str] | None = None,
    repaired_text: str | None = None,
) -> Path:
    live_tau = tmp_path / "live-tau"
    tau_run = live_tau / "tau-dag-run"
    command_root = tau_run / "command-loop" / "command-artifacts"
    provider_root = Path(tempfile.mkdtemp(prefix="pr3d-provider-workspace-")) / "outputs"
    receipts_root = provider_root.parent / "receipts"
    provider_root.mkdir(parents=True)
    receipts_root.mkdir(parents=True)

    code = "print('candidate only')\n"
    code_path = provider_root / "exploit_specimen.py"
    code_path.write_text(code, encoding="utf-8")
    code_sha = _sha256(code_path.read_bytes())
    repaired = repaired_text if repaired_text is not None else "content = b\"BATTLE-004 CHILD SPECIMEN — UNVERIFIED\"\n"
    repaired_path = command_root / "command-loop-step-005" / "repaired_exploit_specimen.py"
    repaired_path.parent.mkdir(parents=True)
    repaired_path.write_text(repaired, encoding="utf-8")
    repaired_sha = _sha256(repaired_path.read_bytes())

    _write_json(
        live_tau / "live-tau-child-dag-canary-receipt.json",
        {
            "schema": "battle.live_tau_child_dag_canary_receipt.v1",
            "status": "BLOCKED",
            "battle_id": "battle-004",
            "proof_mode": "live_tau_child_dag_canary",
            "reason": "unexpected_edge",
            "tau_receipt_status": "BLOCKED",
        },
    )
    _write_json(tau_run / "dag-receipt.json", {"schema": "tau.dag_receipt.v1", "status": "BLOCKED", "verdict": "UNEXPECTED_EDGE"})

    for step, node_id in [
        ("command-loop-step-001", "lineage-summarizer"),
        ("command-loop-step-002", "research-scout"),
        ("command-loop-step-003", "method-combiner"),
    ]:
        _write_json(
            command_root / step / f"{node_id}-node-receipt.json",
            {"schema": "battle.child_dag_node_receipt.v1", "node_id": node_id, "status": "PASS", "verdict": "PASS", "evidence": []},
        )

    authorship = {
        "schema": "battle.provider_authorship_receipt.v1",
        "status": "PASS",
        "mocked": False,
        "agentic": True,
        "provider_live": True,
        "fixture_fallback_used": False,
        "authored_by": "tau_provider",
        "battle_id": "battle-004",
        "observed_provider": "opencode-go",
        "observed_model": "opencode-go/kimi-k2.6",
        "code_artifact_sha256": code_sha,
        "compile_status": "NOT_RUN",
        "runtime_status": "NOT_RUN",
        "judge_status": "NOT_RUN",
        "judge_verified_exploits": 0,
    }
    specimen = {
        "schema": "battle.exploit_specimen.v2",
        "specimen_id": "payload-857-child-dag-001-provider-specimen-0001",
        "language": "python",
        "code_sha256": code_sha,
        "selected_method_ids": ["child_archive_traversal_baseline"],
    }
    compile_receipt = {
        "schema": "battle.child_compile_receipt.v1",
        "status": compile_receipt_status,
        "verdict": compile_verdict,
        "compiler": "py_compile",
        "compile_status": compile_status,
        "mocked": False,
        "live": "local_py_compile",
        "fixture_fallback_used": False,
        "source_code_artifact": str(code_path),
        "repaired_code_artifact": str(repaired_path),
        "runtime_status": runtime_status,
        "target_contact": "NOT_RUN",
        "judge_status": "NOT_RUN",
        "errors": compile_errors if compile_errors is not None else [
            f"  File \"{repaired_path}\", line 1\n"
            "    content = b\"BATTLE-004 CHILD SPECIMEN — UNVERIFIED\"\n"
            "              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n"
            "SyntaxError: bytes can only contain ASCII literal characters\n"
        ],
        "claims": {
            "proves": ["Battle captured compiler failure for the provider-authored specimen artifact."],
            "does_not_prove": ["The specimen runs.", "The specimen exploits the target."],
        },
    }
    _write_json(receipts_root / "provider-authorship-receipt.json", authorship)
    _write_json(receipts_root / "specimen.json", specimen)
    _write_json(command_root / "command-loop-step-005" / "compile_receipt.json", compile_receipt)

    _write_json(
        command_root / "command-loop-step-004" / "exploit-code-author-node-receipt.json",
        {
            "schema": "battle.child_dag_node_receipt.v1",
            "node_id": "exploit-code-author",
            "status": "PASS",
            "verdict": "PASS",
            "evidence": [
                {"kind": "provider-authorship-receipt.json", "path": str(receipts_root / "provider-authorship-receipt.json")},
                {"kind": "specimen.json", "path": str(receipts_root / "specimen.json")},
                {"kind": "exploit_specimen.py", "path": str(code_path)},
            ],
        },
    )
    _write_json(
        command_root / "command-loop-step-005" / "compile-repair-node-receipt.json",
        {
            "schema": "battle.child_dag_node_receipt.v1",
            "node_id": "compile-repair",
            "status": compile_receipt_status,
            "verdict": compile_verdict,
            "evidence": [
                {"kind": "exploit_specimen.py", "path": str(code_path)},
                {"kind": "repaired_exploit_specimen.py", "path": str(repaired_path)},
                {"kind": "compile_receipt.json", "path": str(command_root / "command-loop-step-005" / "compile_receipt.json")},
            ],
        },
    )
    assert repaired_sha.startswith("sha256:")
    return live_tau


def _minimal_valid_fixture() -> dict:
    return {
        "schema": "battle.normalized_compile_fixture.v1",
        "fixture_kind": "pr3d_compile_repair",
        "battle_id": "battle-004",
        "run_id": "battle-004-pr3d-compile",
        "generated_at": "2026-07-10T19:00:00Z",
        "proof_mode": "live_tau_child_dag_canary",
        "status": "PASS",
        "mocked": False,
        "live": "local_py_compile",
        "agentic": True,
        "provider_live": True,
        "fixture_fallback_used": False,
        "stage_scope": {"included_through": "compile-repair", "included_nodes": ["lineage-summarizer", "research-scout", "method-combiner", "exploit-code-author", "compile-repair"], "excluded_nodes": ["artifact-reviewer", "battle-handoff-writer"]},
        "source_run": {},
        "node_status": {"lineage-summarizer": "PASS", "research-scout": "PASS", "method-combiner": "PASS", "exploit-code-author": "PASS", "compile-repair": "BLOCKED"},
        "node_verdict": {},
        "provider_authorship": {"status": "PASS", "provider_live": True, "agentic": True, "authored_by": "tau_provider", "observed_provider": "opencode-go", "observed_model": "opencode-go/kimi-k2.6", "code_sha256": "sha256:" + "1" * 64},
        "compile": {"status": "FAILED", "compiler": "py_compile", "compile_attempted": True, "compile_failed": True, "compile_passed": False, "stderr_summary": {"available": True, "lines": ["SyntaxError"], "redacted": False}, "source_version_id": "v001", "compiled_version_id": "v002"},
        "repair": {"repair_attempted": False, "repair_exhausted": False, "attempt_count": 0},
        "specimen_versions": [
            {"version_id": "v001", "role": "provider_authored", "code_sha256": "sha256:" + "1" * 64, "code_bytes": 10, "compile_attempted": False, "compile_status": "NOT_RUN", "compile_failed": False, "compile_passed": False},
            {"version_id": "v002", "role": "compile_repair_selected", "code_sha256": "sha256:" + "2" * 64, "code_bytes": 10, "compile_attempted": True, "compile_status": "FAILED", "compile_failed": True, "compile_passed": False},
        ],
        "selected_version": {"version_id": "v002"},
        "execution_boundary": {"runtime_status": "NOT_RUN", "target_contact": "NOT_RUN", "judge_status": "NOT_RUN", "judge_verified_exploits": 0, "packet_behavior": "NOT_RUN", "memory_promotion": "NOT_RUN"},
        "claim_boundary": {"may_claim": ["provider_authored_specimen_existed", "compile_attempted", "compile_failed", "compile_passed", "repair_attempted", "repair_exhausted", "specimen_version_hashes"], "must_not_claim": ["runnable", "runtime_success", "target_contact", "exploit_success", "blue_detection", "blue_bypass", "blue_kill", "blue_block", "judge_success", "packet_level_behavior", "memory_promotion"], "compile_passed_is_not_runnable": True},
        "receipt_refs": [],
        "provenance": {"raw_paths_redacted": True},
        "copy": {"headline": "Compile attempt captured", "subhead": "No leak", "status_label": "Compile failed", "boundary_notice": "Compile is not runtime proof."},
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()
