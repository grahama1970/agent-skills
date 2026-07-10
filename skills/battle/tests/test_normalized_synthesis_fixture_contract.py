from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import jsonschema
import pytest

from battle_skill.normalized_synthesis_fixture import normalize_pr3c_synthesis_fixture, validate_normalized_synthesis_fixture


SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"


def _schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def test_pr3c_synthesis_fixture_normalizes_provider_authorship_without_runtime_paths(tmp_path: Path) -> None:
    live_tau = _write_pr3c_source_run(tmp_path)
    out = tmp_path / "local" / "battle-004-pr3c-synthesis"
    public = tmp_path / "public" / "battle-004-pr3c-synthesis"

    fixture = normalize_pr3c_synthesis_fixture(
        live_tau_canary=live_tau,
        out_dir=out,
        public_out_dir=public,
        generated_at="2026-07-10T18:00:00Z",
    )

    jsonschema.validate(fixture, _schema("battle.normalized_synthesis_fixture.v1.schema.json"))
    report = validate_normalized_synthesis_fixture(fixture)
    assert report["status"] == "PASS"
    assert fixture["status"] == "PASS"
    assert fixture["fixture_kind"] == "pr3c_provider_code_author"
    assert fixture["node_status"] == {
        "lineage-summarizer": "PASS",
        "research-scout": "PASS",
        "method-combiner": "PASS",
        "exploit-code-author": "PASS",
    }
    assert fixture["stage_scope"]["excluded_nodes"] == ["compile-repair", "artifact-reviewer", "battle-handoff-writer"]
    assert fixture["stage_scope"]["downstream_receipts_ignored"] is True
    assert fixture["provider_authorship"]["provider_live"] is True
    assert fixture["provider_authorship"]["observed_provider"] == "opencode-go"
    assert fixture["provider_authorship"]["provider_run_id_present"] is True
    assert "provider_run_id" not in fixture["provider_authorship"]
    assert fixture["execution_boundary"] == {
        "compile_status": "NOT_RUN",
        "runtime_status": "NOT_RUN",
        "target_contact": "NOT_RUN",
        "judge_status": "NOT_RUN",
        "judge_verified_exploits": 0,
        "packet_behavior": "NOT_RUN",
        "memory_promotion": "NOT_RUN",
    }
    assert "provider_authored_specimen_materialized" in fixture["claim_boundary"]["may_claim"]
    assert "compile_passed" in fixture["claim_boundary"]["must_not_claim"]
    assert "exploit_success" in fixture["claim_boundary"]["must_not_claim"]
    serialized = json.dumps(fixture, sort_keys=True)
    assert "command-loop" not in serialized
    assert "provider-workspace" not in serialized
    assert "/tmp/" not in serialized
    assert "/mnt/" not in serialized
    assert "compile_receipt" not in serialized
    assert fixture["specimen"]["code_preview"]["lines"][0] == "import json"
    assert len(fixture["specimen"]["code_preview"]["lines"]) <= 80

    local_fixture = out / "battle.normalized_synthesis_fixture.json"
    public_fixture = public / "battle.normalized_synthesis_fixture.json"
    assert local_fixture.exists()
    assert public_fixture.exists()
    assert _sha256(local_fixture.read_bytes()) == _sha256(public_fixture.read_bytes())
    source_index = json.loads((out / "source-receipt-index.json").read_text(encoding="utf-8"))
    source_index_serialized = json.dumps(source_index, sort_keys=True)
    assert source_index["source_receipt_count"] == len(fixture["receipt_refs"])
    assert "command-loop" not in source_index_serialized
    assert "provider-workspace" not in source_index_serialized
    assert "/tmp/" not in source_index_serialized


def test_pr3c_synthesis_fixture_rejects_provider_live_false(tmp_path: Path) -> None:
    live_tau = _write_pr3c_source_run(tmp_path, provider_live=False)

    with pytest.raises(ValueError, match="provider authorship must be live and agentic"):
        normalize_pr3c_synthesis_fixture(live_tau_canary=live_tau, out_dir=tmp_path / "out")


def test_pr3c_synthesis_fixture_rejects_path_leakage() -> None:
    fixture = _minimal_valid_fixture()
    fixture["copy"]["subhead"] = "Leaked /tmp/provider-workspace path"

    with pytest.raises(ValueError, match="forbidden marker"):
        validate_normalized_synthesis_fixture(fixture)


def _write_pr3c_source_run(tmp_path: Path, *, provider_live: bool = True) -> Path:
    live_tau = tmp_path / "live-tau"
    tau_run = live_tau / "tau-dag-run"
    command_root = tau_run / "command-loop" / "command-artifacts"
    provider_root = tmp_path / "external-provider-workspace" / "outputs"
    receipts_root = provider_root.parent / "receipts"
    provider_root.mkdir(parents=True)
    receipts_root.mkdir(parents=True)

    code = "\n".join(
        [
            "import json",
            "",
            "def main():",
            "    payload = {'status': 'candidate only'}",
            "    print(json.dumps(payload))",
            "",
            "if __name__ == '__main__':",
            "    main()",
        ]
    )
    code_path = provider_root / "exploit_specimen.py"
    code_path.write_text(code + "\n", encoding="utf-8")
    code_sha = _sha256(code_path.read_bytes())

    research = {
        "schema": "battle.child_research_receipts.v1",
        "status": "PASS",
        "battle_id": "battle-004",
        "child_lane_id": "payload-857-child-dag-001",
        "mocked": False,
        "live": "tau_command_spec_node",
        "provider_live": False,
        "fixture_fallback_used": False,
        "query": {"method": "manual", "external_tool_called": False},
        "source_receipts": [{"schema": "tau.research_source_receipt.v1", "status": "PASS", "review_required": True}],
        "sources": [
            {
                "source_id": "source-001",
                "source_type": "web",
                "title": "Zip Slip Vulnerability - Snyk",
                "url": "https://security.snyk.io/research/zip-slip-vulnerability",
                "relevance": "HIGH",
                "claims_supported": ["Zip Slip is an archive extraction traversal pattern."],
                "used_for": ["candidate_method"],
                "limitations": ["Research is not proof of exploitability."],
            }
        ],
    }
    methods = {
        "schema": "battle.child_candidate_methods.v1",
        "status": "PASS",
        "methods": [
            {"method_id": "child_archive_traversal_baseline", "inherited": True},
            {"method_id": "child_archive_path_normalization_variants", "inherited": True},
            {"method_id": "child_drop_mitm_and_assembly", "inherited": False},
        ],
    }
    genome = {
        "schema": "battle.child_exploit_genome.v1",
        "status": "PASS",
        "created_by": "battle_deterministic_method_combiner",
        "agentic": False,
        "provider_live": False,
        "selected_method_ids": ["child_archive_traversal_baseline", "child_archive_path_normalization_variants"],
        "rejected_method_ids": ["child_drop_mitm_and_assembly"],
        "strategy": {
            "primary": "Prefer low-complexity archive traversal baseline.",
            "repair_bias": "Use path normalization variants after baseline.",
            "negative_filter": "Defer MITM and assembly ideas.",
        },
    }
    _write_json(command_root / "command-loop-step-002" / "research_receipts.json", research)
    _write_json(command_root / "command-loop-step-002" / "candidate_methods.json", methods)
    _write_json(command_root / "command-loop-step-003" / "exploit_genome.json", genome)
    _write_json(live_tau / "live-tau-child-dag-canary-receipt.json", {"schema": "battle.live_tau_child_dag_canary_receipt.v1", "status": "BLOCKED", "battle_id": "battle-004", "proof_mode": "live_tau_child_dag_canary", "reason": "node_blocked", "tau_receipt_status": "BLOCKED"})
    _write_json(tau_run / "dag-receipt.json", {"schema": "tau.dag_receipt.v1", "status": "BLOCKED", "verdict": "NODE_BLOCKED"})

    for step, node_id in [
        ("command-loop-step-001", "lineage-summarizer"),
        ("command-loop-step-002", "research-scout"),
        ("command-loop-step-003", "method-combiner"),
    ]:
        evidence = []
        if node_id == "research-scout":
            evidence = [
                {"kind": "research_receipts.json", "path": str(command_root / step / "research_receipts.json")},
                {"kind": "candidate_methods.json", "path": str(command_root / step / "candidate_methods.json")},
            ]
        if node_id == "method-combiner":
            evidence = [{"kind": "exploit_genome.json", "path": str(command_root / step / "exploit_genome.json")}]
        _write_json(command_root / step / f"{node_id}-node-receipt.json", {"schema": "battle.child_dag_node_receipt.v1", "node_id": node_id, "status": "PASS", "verdict": "PASS", "evidence": evidence})

    artifact_validation = {
        "schema": "battle.provider_artifact_validation.v1",
        "status": "PASS",
        "provider_live": provider_live,
        "code_artifact_sha256": code_sha,
        "code_artifact_bytes": code_path.stat().st_size,
        "code_artifact_path": str(code_path),
        "errors": [],
    }
    authorship = {
        "schema": "battle.provider_authorship_receipt.v1",
        "status": "PASS",
        "mocked": False,
        "agentic": provider_live,
        "provider_live": provider_live,
        "fixture_fallback_used": False,
        "live": "tau_provider_artifact_authoring",
        "authored_by": "tau_provider" if provider_live else "none",
        "battle_id": "battle-004",
        "child_lane_id": "payload-857-child-dag-001",
        "observed_provider": "opencode-go",
        "observed_model": "opencode-go/kimi-k2.6",
        "provider_run_id": "run-secret-value",
        "provider_session_id": "session-secret-value",
        "code_artifact_sha256": code_sha,
        "code_artifact_bytes": code_path.stat().st_size,
        "compile_status": "NOT_RUN",
        "runtime_status": "NOT_RUN",
        "target_contact": "NOT_RUN",
        "judge_status": "NOT_RUN",
        "judge_verified_exploits": 0,
        "validation": {
            "goal_hash_bound": True,
            "provider_route_bound": True,
            "output_declared_by_worker": True,
            "output_hash_bound": True,
            "output_inside_allowed_root": True,
            "private_reference_scan_passed": True,
            "claim_boundary_passed": True,
        },
    }
    boundary = {
        "schema": "battle.provider_code_author_boundary_receipt.v1",
        "status": "PASS",
        "mocked": False,
        "agentic": provider_live,
        "provider_live": provider_live,
        "fixture_fallback_used": False,
        "battle_id": "battle-004",
        "compile_status": "NOT_RUN",
        "runtime_status": "NOT_RUN",
        "judge_status": "NOT_RUN",
        "judge_verified_exploits": 0,
    }
    specimen = {
        "schema": "battle.exploit_specimen.v2",
        "specimen_id": "payload-857-child-dag-001-provider-specimen-0001",
        "child_lane_id": "payload-857-child-dag-001",
        "generation": 1,
        "language": "python",
        "created_by": "tau_provider",
        "agentic": provider_live,
        "provider_live": provider_live,
        "code_sha256": code_sha,
        "selected_method_ids": genome["selected_method_ids"],
        "inherited_method_ids": [],
    }
    _write_json(receipts_root / "provider-authorship-receipt.json", authorship)
    _write_json(receipts_root / "provider-code-author-boundary-receipt.json", boundary)
    _write_json(receipts_root / "provider-artifact-validation.json", artifact_validation)
    _write_json(provider_root / "specimen.json", specimen)

    exploit_evidence = [
        {"kind": "research_receipts.json", "path": str(command_root / "command-loop-step-002" / "research_receipts.json")},
        {"kind": "candidate_methods.json", "path": str(command_root / "command-loop-step-002" / "candidate_methods.json")},
        {"kind": "exploit_genome.json", "path": str(command_root / "command-loop-step-003" / "exploit_genome.json")},
        {"kind": "provider-authorship-receipt.json", "path": str(receipts_root / "provider-authorship-receipt.json")},
        {"kind": "provider-code-author-boundary-receipt.json", "path": str(receipts_root / "provider-code-author-boundary-receipt.json")},
        {"kind": "provider-artifact-validation.json", "path": str(receipts_root / "provider-artifact-validation.json")},
        {"kind": "specimen.json", "path": str(provider_root / "specimen.json")},
        {"kind": "exploit_specimen.py", "path": str(code_path)},
    ]
    _write_json(
        command_root / "command-loop-step-004" / "exploit-code-author-node-receipt.json",
        {
            "schema": "battle.child_dag_node_receipt.v1",
            "node_id": "exploit-code-author",
            "status": "PASS",
            "verdict": "PASS",
            "provider_live": provider_live,
            "agentic": provider_live,
            "authored_by": "tau_provider" if provider_live else "none",
            "evidence": exploit_evidence,
        },
    )
    _write_json(command_root / "command-loop-step-005" / "compile_receipt.json", {"schema": "battle.child_compile_receipt.v1", "status": "PASS"})
    return live_tau


def _minimal_valid_fixture() -> dict:
    root = Path(tempfile.mkdtemp(prefix="battle-normalized-synthesis-minimal-test-"))
    live_tau = _write_pr3c_source_run(root)
    return normalize_pr3c_synthesis_fixture(live_tau_canary=live_tau, out_dir=root / "out", generated_at="2026-07-10T18:00:00Z")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()
