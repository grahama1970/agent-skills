"""Tau semantic input materialization tests."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from monitor_opportunities.cli import app
from monitor_opportunities.contracts import validate_tau_semantic_input
from monitor_opportunities.tau_semantic_prepare import prepare_tau_semantic_inputs
from monitor_opportunities.util import read_json, write_json

runner = CliRunner()


def _stage_fixture_run(tmp_path: Path) -> Path:
    fixture_dir = Path(__file__).parent / "fixtures" / "discovery"
    run_dir = tmp_path / "run"
    result = runner.invoke(app, ["run", "--fixture-dir", str(fixture_dir), "--out", str(run_dir)])
    assert result.exit_code == 0, result.output
    return run_dir


def test_tau_semantic_prepare_writes_validated_inputs(tmp_path: Path) -> None:
    run_dir = _stage_fixture_run(tmp_path)
    out_dir = tmp_path / "tau"

    result = runner.invoke(
        app,
        ["tau-semantic-prepare", "--run", str(run_dir), "--out", str(out_dir), "--top-n", "2"],
    )

    assert result.exit_code == 0, result.output
    receipt = json.loads(result.stdout)
    assert receipt["status"] == "PASS"
    assert receipt["mocked"] is False
    assert receipt["provider_live"] is False
    assert receipt["external_effects"] is False
    assert receipt["selected_count"] == 2
    assert receipt["rejected_count"] == 0

    for selected in receipt["selected"]:
        payload = validate_tau_semantic_input(read_json(Path(selected["artifact"])))
        assert payload.primary_opportunity_evidence_present is True
        assert payload.policy.external_effects is False
        assert payload.meetup_evidence_present is False


def test_tau_semantic_prepare_includes_direct_relationship_evidence(tmp_path: Path) -> None:
    run_dir = _stage_fixture_run(tmp_path)
    manifest_path = run_dir / "report-manifest.json"
    manifest = read_json(manifest_path)
    opportunity_id = manifest["opportunities"][0]["opportunity_id"]
    receipt_id = manifest["opportunities"][0]["source_receipt_ids"][0]
    manifest["relationship_signals"].append(
        {
            "signal_id": "rel-direct-test",
            "source_opportunity_id": opportunity_id,
            "signal_type": "direct_contact",
            "subject": "Redacted direct contact",
            "organization": manifest["opportunities"][0]["organization"],
            "relationship_path": ["Graham Anderson", "redacted contact"],
            "evidence_refs": ["memory://redacted-direct-test"],
            "source_receipt_ids": [receipt_id],
            "provenance": "Direct report-visible relationship path exists.",
            "memory_recall_found": True,
            "memory_recall_degraded": False,
            "recommended_action": "human_decide_reconnect_or_defer",
            "contact_channel_risk": "corporate_email_may_be_blocked_after_long_gap",
            "preferred_human_channels": ["LINKEDIN_HUMAN_HANDOFF"],
            "channel_guidance": ["Human-transmitted reconnect only."],
            "external_effects": False,
            "action_worthy": True,
            "visible_in_report": True,
        }
    )
    manifest["artifact_accounting"]["action_worthy_total"] += 1
    manifest["artifact_accounting"]["visible_total"] += 1
    write_json(manifest_path, manifest)

    receipt = prepare_tau_semantic_inputs(run_dir=run_dir, out_dir=tmp_path / "tau", top_n=1)
    payload = validate_tau_semantic_input(read_json(Path(receipt["selected"][0]["artifact"])))

    assert payload.relationship_status == "HAS_RELATIONSHIP_EVIDENCE"
    assert payload.relationship_evidence[0].redacted_contact_ref == "relationship_signal:rel-direct-test"


def test_tau_semantic_prepare_rejects_meetup_primary_input(tmp_path: Path) -> None:
    run_dir = _stage_fixture_run(tmp_path)
    manifest_path = run_dir / "report-manifest.json"
    manifest = read_json(manifest_path)
    selected_receipt_id = manifest["opportunities"][0]["source_receipt_ids"][0]
    for receipt in manifest["source_receipts"]:
        if receipt["receipt_id"] == selected_receipt_id:
            receipt["provider"] = "meetup"
            receipt["source_class"] = "meetup_surf_capture"
            receipt["required_source_id"] = "meetup"
    write_json(manifest_path, manifest)

    receipt = prepare_tau_semantic_inputs(run_dir=run_dir, out_dir=tmp_path / "tau", top_n=1)

    assert receipt["status"] == "FAIL"
    assert receipt["selected_count"] == 0
    assert receipt["rejected"] == [
        {
            "opportunity_id": manifest["opportunities"][0]["opportunity_id"],
            "reason": "NO_NON_MEETUP_PRIMARY_RECEIPT",
        }
    ]
