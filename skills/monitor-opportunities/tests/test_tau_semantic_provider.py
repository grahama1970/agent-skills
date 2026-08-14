"""Provider semantic sidecar wiring tests."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

import monitor_opportunities.tau_semantic_provider as provider
from monitor_opportunities import service
from monitor_opportunities.cli import app
from monitor_opportunities.contracts import IMMUTABLE_GOAL
from monitor_opportunities.semantic_addenda import install_semantic_addendum
from monitor_opportunities.util import write_json

runner = CliRunner()


def _goal_hash() -> str:
    return "sha256:" + hashlib.sha256(IMMUTABLE_GOAL.encode("utf-8")).hexdigest()


def _input_payload() -> dict[str, object]:
    return {
        "schema": "monitor_opportunities.tau_semantic_input.v1",
        "run_id": "run:2026-08-14",
        "source_run_receipt_ref": "run-receipt:run:2026-08-14",
        "source_run_sha256": "sha256:run",
        "opportunity_id": "candidate:a:test",
        "rank": 1,
        "selected_at": "2026-08-14T22:30:00Z",
        "immutable_goal": {"text": IMMUTABLE_GOAL, "goal_hash": _goal_hash()},
        "goal_hash": _goal_hash(),
        "candidate_profile_version": "candidate-profile.v1",
        "candidate_profile_sha256": "sha256:profile",
        "allowed_fact_ledger": ["claim:arcos: Led ACERT architecture work for DARPA ARCOS."],
        "primary_opportunity_evidence_present": True,
        "primary_opportunity_evidence_ids": ["src:a:ashby:test"],
        "primary_source_classes": ["employer_ats"],
        "retained_artifact_hashes": ["sha256:manifest"],
        "source_receipt_hashes": ["sha256:source"],
        "fetched_at": "2026-08-14T22:29:00Z",
        "source_health_state": "OK",
        "relationship_status": "NO_RELATIONSHIP_EVIDENCE",
        "relationship_evidence": [],
        "meetup_evidence_present": False,
        "meetup_policy": "SUPPLEMENTAL_ONLY",
        "policy": {
            "external_effects": False,
            "allowed_output_types": ["semantic_addendum", "interview_addendum"],
            "timeout_seconds": 600,
            "max_concurrency": 1,
            "max_attempts": 1,
            "max_cost_usd": 2.5,
        },
    }


def test_tau_semantic_provider_requires_execute_for_live_call(tmp_path: Path) -> None:
    input_path = tmp_path / "input.json"
    write_json(input_path, _input_payload())

    result = runner.invoke(
        app,
        ["tau-semantic-provider-eval", "--input", str(input_path), "--out", str(tmp_path / "out")],
    )

    assert result.exit_code == 1
    receipt = json.loads(result.stdout)
    assert receipt["status"] == "EXECUTE_REQUIRED"
    assert receipt["provider_live"] is False
    assert receipt["external_effects"] is False


def test_tau_semantic_provider_admits_closed_json_response(
    tmp_path: Path,
    monkeypatch,
) -> None:
    input_path = tmp_path / "input.json"
    write_json(input_path, _input_payload())

    def run_stub(command, capture_output, text, timeout):  # type: ignore[no-untyped-def]
        del capture_output, text, timeout
        ask_id = command[command.index("--ask-id") + 1]
        ask_root = Path(command[command.index("--run-output-root") + 1])
        handler = command[command.index("--handler") + 1]
        node_dir = ask_root / ask_id / "node-artifacts" / f"handler-{handler}"
        node_dir.mkdir(parents=True)
        write_json(
            node_dir / "node-receipt.json",
            {
                "status": "PASS",
                "provider_live": True,
                "live": True,
                "mocked": False,
                "response_path": str(node_dir / "response.md"),
            },
        )
        write_json(
            node_dir / "response.provider_result.json",
            {"success": True, "proof_status": "response_proven", "status": "completed"},
        )
        (node_dir / "response.md").write_text(
            json.dumps(
                {
                    "schema": "monitor_opportunities.semantic_addendum.v1",
                    "opportunity_id": "candidate:a:test",
                    "verdict": "KEEP",
                    "semantic_summary": "The role is aligned with approved ARCOS evidence.",
                    "tailoring_guidance": "Use the ARCOS claim without adding new facts.",
                    "talking_points": ["Discuss receipt-gated document graph work."],
                    "interview_questions": ["How would you evaluate extraction quality?"],
                    "evidence_refs": ["src:a:ashby:test"],
                    "non_claims": ["Does not prove employer ranking behavior."],
                    "external_effects": False,
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout='{"status":"PASS"}\n', stderr="")

    monkeypatch.setattr(provider.subprocess, "run", run_stub)

    receipt = provider.run_provider_semantic_eval(
        input_path=input_path,
        out_dir=tmp_path / "out",
        execute=True,
        timeout_seconds=60,
        browser_lock_timeout=60,
    )

    assert receipt["status"] == "PASS"
    assert receipt["provider_live"] is True
    assert receipt["semantic_addendum"]
    addendum = json.loads(Path(receipt["semantic_addendum"]).read_text(encoding="utf-8"))
    assert addendum["verdict"] == "KEEP"


def test_tau_semantic_provider_rejects_unparseable_provider_response(
    tmp_path: Path,
    monkeypatch,
) -> None:
    input_path = tmp_path / "input.json"
    write_json(input_path, _input_payload())

    def run_stub(command, capture_output, text, timeout):  # type: ignore[no-untyped-def]
        del capture_output, text, timeout
        ask_id = command[command.index("--ask-id") + 1]
        ask_root = Path(command[command.index("--run-output-root") + 1])
        handler = command[command.index("--handler") + 1]
        node_dir = ask_root / ask_id / "node-artifacts" / f"handler-{handler}"
        node_dir.mkdir(parents=True)
        write_json(node_dir / "node-receipt.json", {"status": "PASS", "provider_live": True})
        write_json(
            node_dir / "response.provider_result.json",
            {"success": True, "proof_status": "response_proven", "status": "completed"},
        )
        (node_dir / "response.md").write_text("not json\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout='{"status":"PASS"}\n', stderr="")

    monkeypatch.setattr(provider.subprocess, "run", run_stub)

    receipt = provider.run_provider_semantic_eval(
        input_path=input_path,
        out_dir=tmp_path / "out",
        execute=True,
        timeout_seconds=60,
        browser_lock_timeout=60,
    )

    assert receipt["status"] == "FAIL"
    assert receipt["provider_live"] is True
    assert receipt["parse_errors"]


def test_tau_semantic_install_projects_addendum_into_interview_page(tmp_path: Path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures" / "discovery"
    run_dir = tmp_path / "run"
    run_result = runner.invoke(app, ["run", "--fixture-dir", str(fixture_dir), "--out", str(run_dir)])
    assert run_result.exit_code == 0, run_result.output
    manifest = json.loads((run_dir / "report-manifest.json").read_text(encoding="utf-8"))
    opportunity_id = manifest["opportunities"][0]["opportunity_id"]

    addendum = {
        "schema": "monitor_opportunities.semantic_addendum.v1",
        "opportunity_id": opportunity_id,
        "verdict": "NEEDS_REVIEW",
        "semantic_summary": "Provider says human review is required.",
        "tailoring_guidance": "Use only approved claim-bound wording.",
        "talking_points": ["Discuss receipt-gated evidence work."],
        "interview_questions": ["Which evidence is source-bound?"],
        "evidence_refs": [manifest["opportunities"][0]["source_receipt_ids"][0]],
        "non_claims": ["Does not authorize application."],
        "external_effects": False,
    }
    addendum_path = tmp_path / "semantic-addendum.json"
    write_json(addendum_path, addendum)
    provider_receipt = {
        "schema": "monitor_opportunities.tau_semantic_provider_receipt.v1",
        "status": "PASS",
        "opportunity_id": opportunity_id,
        "handler": "webgpt",
        "semantic_addendum": str(addendum_path),
        "provider_live": True,
        "live": True,
        "mocked": False,
        "external_effects": False,
    }
    receipt_path = tmp_path / "provider-receipt.json"
    write_json(receipt_path, provider_receipt)

    receipt = install_semantic_addendum(run_dir=run_dir, provider_receipt_path=receipt_path)
    page = service._render_page(run_dir, "test-token")

    assert receipt["status"] == "PASS"
    assert "Provider Semantic Addendum" in page
    assert "Provider says human review is required." in page
    assert "Does not authorize application." in page
