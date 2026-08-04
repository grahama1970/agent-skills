from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from monitor_opportunities.cli import app

runner = CliRunner()


def test_run_creates_one_report_and_receipt(tmp_path: Path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures" / "discovery"
    out = tmp_path / "nightly"
    result = runner.invoke(app, ["run", "--fixture-dir", str(fixture_dir), "--out", str(out)])
    assert result.exit_code == 0, result.output
    receipt = json.loads((out / "run-receipt.json").read_text(encoding="utf-8"))
    assert receipt["terminal_state"] == "AWAITING_HUMAN"
    assert receipt["external_effects"] is False
    assert (out / "report" / "index.html").exists()
    status = runner.invoke(app, ["resume", "--run", str(out)])
    assert status.exit_code == 0, status.output
    assert json.loads(status.stdout)["state"] == "AWAITING_HUMAN"
    run_status = runner.invoke(app, ["status", "--run", str(out), "--json"])
    assert run_status.exit_code == 0, run_status.output
    payload = json.loads(run_status.stdout)
    assert payload["state"] == "AWAITING_HUMAN"
    assert payload["external_effects"] is False
    assert payload["current_stale"] is False
    assert payload["dependency_readiness"] == {
        "discovery": "READY",
        "ranking": "READY",
        "tailoring": "READY",
        "report": "READY",
    }
    assert payload["artifact_accounting"]["hidden_total"] == 0
    assert len(payload["lane_health"]) == 3
    assert payload["budget"]["max"] == 10.0
    manifest = json.loads((out / "report-manifest.json").read_text(encoding="utf-8"))
    assert manifest["application_packets"]
    packet = manifest["application_packets"][0]
    assert packet["visible_in_report"] is True
    assert packet["action_worthy"] is True
    assert packet["approval_status"] == "NOT_AUTHORIZED"
    assert packet["resume_digest"]
    assert packet["claim_snapshot_digest"] == manifest["resume_variants"][0]["claim_snapshot_sha256"]
    assert packet["field_answer_digest"]
    assert packet["posting_digest"]
    assert packet["approval_payload_digest"]
    packet_json = json.loads(Path(packet["packet_ref"]).read_text(encoding="utf-8"))
    assert packet_json["packet_id"] == packet["packet_id"]
    application_id = packet["application_id"]
    authorize = runner.invoke(
        app,
        [
            "decision",
            "--run",
            str(out),
            "--item",
            application_id,
            "--action",
            "AUTHORIZE_APPLICATION_PAYLOAD",
            "--idempotency-key",
            "authorize-before-drift",
        ],
    )
    assert authorize.exit_code == 0, authorize.output
    Path(packet["resume_artifacts"][0]["path"]).write_text("tampered resume\n", encoding="utf-8")
    drifted = runner.invoke(
        app,
        [
            "decision",
            "--run",
            str(out),
            "--item",
            application_id,
            "--action",
            "AUTHORIZE_APPLICATION_PAYLOAD",
            "--idempotency-key",
            "authorize-after-drift",
        ],
    )
    assert drifted.exit_code == 2
    assert "APPLICATION_PACKET_DRIFT" in drifted.stderr


def test_run_with_linkedin_evidence_renders_no_automation_policy(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "discovery" / "linkedin-top-candidate.json"
    out = tmp_path / "nightly-linkedin"
    result = runner.invoke(app, ["run", "--linkedin-evidence", str(fixture), "--out", str(out)])
    assert result.exit_code == 0, result.output
    receipt = json.loads((out / "run-receipt.json").read_text(encoding="utf-8"))
    assert receipt["external_effects"] is False
    manifest = json.loads((out / "report-manifest.json").read_text(encoding="utf-8"))
    linkedin_receipts = [
        row for row in manifest["source_receipts"] if row["source_class"] == "human_supplied_linkedin"
    ]
    assert linkedin_receipts
    assert linkedin_receipts[0]["automation_policy"] == "linkedin_no_automation"
    assert any(
        "top-candidate" in " ".join(row["why_candidate"]).lower()
        for row in manifest["opportunities"]
    )
    assert all(action["effects_external"] is False for action in manifest["decision_actions"])
