from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from monitor_opportunities.cli import app
from monitor_opportunities.contracts import IMMUTABLE_GOAL
from monitor_opportunities.util import sha256_json

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
        "linkedin profile/recommendation-based relevance evidence" in " ".join(row["why_candidate"]).lower()
        for row in manifest["opportunities"]
    )
    assert all(action["effects_external"] is False for action in manifest["decision_actions"])


def test_run_with_ops_linkedin_capture_ranks_relevant_jobs_and_rejects_irrelevant(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "discovery" / "ops-linkedin-jobs-capture.json"
    out = tmp_path / "nightly-ops-linkedin"
    result = runner.invoke(app, ["run", "--linkedin-evidence", str(fixture), "--out", str(out)])
    assert result.exit_code == 0, result.output
    receipt = json.loads((out / "run-receipt.json").read_text(encoding="utf-8"))
    assert receipt["external_effects"] is False
    manifest = json.loads((out / "report-manifest.json").read_text(encoding="utf-8"))
    linkedin_receipts = [
        row for row in manifest["source_receipts"] if row["source_class"] == "ops_linkedin_authorized_read_only"
    ]
    assert linkedin_receipts
    assert linkedin_receipts[0]["automation_policy"] == "linkedin_authorized_read_only_no_actions"
    assert any(row["title"] == "GenAI Python Systems Engineer - Senior Manager" for row in manifest["opportunities"])
    linked = next(row for row in manifest["opportunities"] if row["title"] == "GenAI Python Systems Engineer - Senior Manager")
    assert linked["primary_evidence_url"] == "https://www.linkedin.com/jobs/search-results/?currentJobId=4419087753"
    assert linked["posting_url"] == "https://www.linkedin.com/jobs/search-results/?currentJobId=4419087753"
    assert linked["apply_url"] is None
    assert not any(row["title"] == "Founders Associate" for row in manifest["opportunities"])
    assert any(
        row["title"] == "Founders Associate" and row["reason_code"] == "HUMAN_REVIEW_LOCATION_AMBIGUOUS"
        for row in manifest["eligibility_rejections"]
    )


def test_run_renders_reviewed_gmail_draft_receipt(tmp_path: Path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures" / "discovery"
    baseline = tmp_path / "baseline"
    baseline_result = runner.invoke(app, ["run", "--fixture-dir", str(fixture_dir), "--out", str(baseline)])
    assert baseline_result.exit_code == 0, baseline_result.output
    baseline_manifest = json.loads((baseline / "report-manifest.json").read_text(encoding="utf-8"))
    gmail_packet = next(
        packet for packet in baseline_manifest["outreach_packets"] if packet["channel"] == "GMAIL"
    )
    roundtable_receipt = {
        "schema": "monitor_opportunities.outreach_roundtable_receipt.v1",
        "receipt_key": f"{gmail_packet['opportunity_id']}:GMAIL",
        "immutable_goal": IMMUTABLE_GOAL,
        "topology": "concurrent",
        "rounds": 1,
        "attributed_synthesis": True,
        "packet_digest": gmail_packet["payload_digest"],
        "verdict": "SEND_AS_IS",
        "seats": [
            {"handler": "gpt-5.5-high", "status": "PASS"},
            {"handler": "gpt-5.5-xhigh", "status": "PASS"},
        ],
        "dissent": [],
    }
    effect_payload = {
        "schema": "monitor_opportunities.outreach_effect_receipt.v1",
        "effect_id": "effect:test",
        "packet_id": gmail_packet["packet_id"],
        "channel": "GMAIL",
        "state": "DRAFT_CREATED_NOT_SENT",
        "draft_id": "draft:test",
        "idempotency_key": "same",
        "idempotency_marker": "marker:test",
        "subject_digest": sha256_json(gmail_packet["subject"]),
        "body_digest": sha256_json(gmail_packet["body"]),
        "gmail_sent": False,
        "linkedin_automated": False,
        "external_effects": True,
        "created_at": "2026-08-04T00:00:00+00:00",
    }
    effect_payload["receipt_digest"] = sha256_json(effect_payload)
    receipts = tmp_path / "roundtable.json"
    effects = tmp_path / "effects.json"
    receipts.write_text(
        json.dumps({roundtable_receipt["receipt_key"]: roundtable_receipt}),
        encoding="utf-8",
    )
    effects.write_text(json.dumps([effect_payload]), encoding="utf-8")

    out = tmp_path / "reviewed"
    result = runner.invoke(
        app,
        [
            "run",
            "--fixture-dir",
            str(fixture_dir),
            "--roundtable-receipts",
            str(receipts),
            "--outreach-effects",
            str(effects),
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    manifest = json.loads((out / "report-manifest.json").read_text(encoding="utf-8"))
    reviewed = next(packet for packet in manifest["outreach_packets"] if packet["packet_id"] == gmail_packet["packet_id"])
    assert reviewed["roundtable_status"] == "PASS"
    assert reviewed["readiness_state"] == "REVIEW_PERMITTED"
    assert reviewed["effect_status"] == "DRAFT_CREATED_NOT_SENT"
    assert reviewed["draft_id"] == "draft:test"
    assert reviewed["mailbox_draft_ref"] == "gmail:draft:draft:test"
    assert reviewed["sendable"] is False
    assert "gmail:draft:draft:test" in (out / "report" / "index.html").read_text(encoding="utf-8")
