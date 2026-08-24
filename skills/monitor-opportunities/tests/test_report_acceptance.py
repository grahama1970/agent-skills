"""Run-level report acceptance gate tests."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from monitor_opportunities.cli import app

runner = CliRunner()


def _run_fixture(tmp_path: Path) -> Path:
    fixture_dir = Path(__file__).parent / "fixtures" / "discovery"
    out = tmp_path / "run"
    result = runner.invoke(app, ["run", "--fixture-dir", str(fixture_dir), "--out", str(out)])
    assert result.exit_code == 0, result.output
    return out


def test_report_acceptance_passes_for_receipt_backed_run(tmp_path: Path) -> None:
    out = _run_fixture(tmp_path)
    replay = runner.invoke(app, ["replay", "--run", str(out)])
    assert replay.exit_code == 0, replay.output

    result = runner.invoke(app, ["report-acceptance", "--run", str(out)])
    payload = json.loads(result.stdout)

    assert result.exit_code == 0, result.output
    assert payload["schema"] == "monitor_opportunities.report_acceptance_receipt.v1"
    assert payload["status"] == "PASS"
    assert payload["checks"]["manifest_contract_pass"] is True
    assert payload["checks"]["receipt_consistency_pass"] is True
    assert payload["checks"]["zero_effect_replay_pass"] is True
    assert payload["checks"]["run_external_effects_false"] is True
    assert payload["checks"]["application_packets_human_authorized_only"] is True
    assert payload["counts"]["opportunities"] <= 8
    assert (out / "report-acceptance-receipt.json").is_file()


def test_report_acceptance_fails_required_stage_ledger_violation(tmp_path: Path) -> None:
    out = _run_fixture(tmp_path)
    replay = runner.invoke(app, ["replay", "--run", str(out)])
    assert replay.exit_code == 0, replay.output
    (out / "stage-ledger.json").write_text(
        json.dumps(
            {
                "schema": "monitor_opportunities.stage_ledger.v1",
                "ok": False,
                "counts": {"discovered": 2, "accepted": 1, "unaccounted": 1},
                "violations": [
                    {
                        "rule": "no-silent-loss",
                        "candidate_id": "candidate:a:ghost",
                        "detail": "discovered record candidate:a:ghost has no disposition",
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["report-acceptance", "--run", str(out), "--require-stage-ledger"])
    payload = json.loads(result.stdout)

    assert result.exit_code == 1
    assert payload["status"] == "FAIL"
    assert payload["checks"]["stage_ledger_required"] is True
    assert payload["checks"]["stage_ledger_present"] is True
    assert payload["checks"]["stage_ledger_pass"] is False
    assert payload["counts"]["stage_ledger_violations"] == 1
    assert any(row["check"] == "stage_ledger_pass" for row in payload["failures"])


def test_report_acceptance_fails_without_required_zero_effect_replay(tmp_path: Path) -> None:
    out = _run_fixture(tmp_path)

    result = runner.invoke(app, ["report-acceptance", "--run", str(out)])
    payload = json.loads(result.stdout)

    assert result.exit_code == 1
    assert payload["status"] == "FAIL"
    assert payload["checks"]["zero_effect_replay_required"] is True
    assert payload["checks"]["zero_effect_replay_present"] is False
    assert any(row["check"] == "zero_effect_replay_present" for row in payload["failures"])


def test_report_acceptance_fails_degraded_receipt_without_limitations(tmp_path: Path) -> None:
    out = _run_fixture(tmp_path)
    replay = runner.invoke(app, ["replay", "--run", str(out)])
    assert replay.exit_code == 0, replay.output
    manifest_path = out / "report-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_receipts"].append(
        {
            **manifest["source_receipts"][0],
            "receipt_id": "src:degraded-without-limitations",
            "result_status": "RATE_LIMITED",
            "limitations": [],
        }
    )
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    result = runner.invoke(app, ["report-acceptance", "--run", str(out)])
    payload = json.loads(result.stdout)

    assert result.exit_code == 1
    assert payload["status"] == "FAIL"
    assert payload["checks"]["degraded_source_limitations_present"] is False
    assert any(row["check"] == "degraded_source_limitations" for row in payload["failures"])


def test_report_acceptance_fails_failed_zero_effect_replay(tmp_path: Path) -> None:
    out = _run_fixture(tmp_path)
    replay = runner.invoke(app, ["replay", "--run", str(out)])
    assert replay.exit_code == 0, replay.output
    replay_path = out / "zero-effect-replay-receipt.json"
    replay_receipt = json.loads(replay_path.read_text(encoding="utf-8"))
    replay_receipt["status"] = "FAIL"
    replay_path.write_text(json.dumps(replay_receipt, indent=2, sort_keys=True) + "\n")

    result = runner.invoke(app, ["report-acceptance", "--run", str(out)])
    payload = json.loads(result.stdout)

    assert result.exit_code == 1
    assert payload["status"] == "FAIL"
    assert any(row["check"] == "zero_effect_replay" for row in payload["failures"])


def test_report_acceptance_fails_foreign_zero_effect_replay(tmp_path: Path) -> None:
    out = _run_fixture(tmp_path / "one")
    other = _run_fixture(tmp_path / "two")
    replay = runner.invoke(app, ["replay", "--run", str(other)])
    assert replay.exit_code == 0, replay.output
    (out / "zero-effect-replay-receipt.json").write_text(
        (other / "zero-effect-replay-receipt.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["report-acceptance", "--run", str(out)])
    payload = json.loads(result.stdout)

    assert result.exit_code == 1
    assert payload["status"] == "FAIL"
    failure_checks = {row["check"] for row in payload["failures"]}
    assert "zero_effect_replay_run_dir_bound" in failure_checks
    assert "zero_effect_replay_artifacts_bound" in failure_checks
    assert "zero_effect_replay_binding_current" in failure_checks


def test_report_acceptance_fails_hash_mismatched_replay(tmp_path: Path) -> None:
    out = _run_fixture(tmp_path)
    replay = runner.invoke(app, ["replay", "--run", str(out)])
    assert replay.exit_code == 0, replay.output
    manifest_path = out / "report-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["relationship_signals"].append(
        {
            "schema": "monitor_opportunities.relationship_signal.v1",
            "signal_id": "relationship:test-stale",
            "source": "test",
            "person_name": "Stale Replay",
            "organization": "Example",
            "relationship_type": "adjacent_contact",
            "confidence": 0.1,
            "evidence_url": "https://example.test",
            "external_effects": False,
            "visible_in_report": True,
            "action_worthy": True,
        }
    )
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    result = runner.invoke(app, ["report-acceptance", "--run", str(out)])
    payload = json.loads(result.stdout)

    assert result.exit_code == 1
    assert payload["status"] == "FAIL"
    failure_checks = {row["check"] for row in payload["failures"]}
    assert "zero_effect_replay_binding_current" in failure_checks
    assert "run_manifest_hash_bound" in failure_checks


def test_report_acceptance_fails_effect_bearing_replay_receipt(tmp_path: Path) -> None:
    out = _run_fixture(tmp_path)
    replay = runner.invoke(app, ["replay", "--run", str(out)])
    assert replay.exit_code == 0, replay.output
    replay_path = out / "zero-effect-replay-receipt.json"
    replay_receipt = json.loads(replay_path.read_text(encoding="utf-8"))
    replay_receipt["external_effects"] = True
    replay_receipt["checks"]["projection_external_effects_false"] = False
    replay_path.write_text(json.dumps(replay_receipt, indent=2, sort_keys=True) + "\n")

    result = runner.invoke(app, ["report-acceptance", "--run", str(out)])
    payload = json.loads(result.stdout)

    assert result.exit_code == 1
    assert payload["checks"]["zero_effect_replay_external_effects_false"] is False
    assert payload["checks"]["zero_effect_replay_required_checks_true"] is False


def test_report_acceptance_fails_shortlist_overflow(tmp_path: Path) -> None:
    out = _run_fixture(tmp_path)
    replay = runner.invoke(app, ["replay", "--run", str(out)])
    assert replay.exit_code == 0, replay.output
    manifest_path = out / "report-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    template = manifest["opportunities"][0]
    while len(manifest["opportunities"]) <= 8:
        manifest["opportunities"].append(
            {
                **template,
                "opportunity_id": f"candidate:overflow:{len(manifest['opportunities'])}",
            }
        )
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    result = runner.invoke(app, ["report-acceptance", "--run", str(out)])
    payload = json.loads(result.stdout)

    assert result.exit_code == 1
    assert payload["checks"]["shortlist_bound"] is False
    assert any(row["check"] == "shortlist_bound" for row in payload["failures"])


def test_report_acceptance_fails_zero_opportunities(tmp_path: Path) -> None:
    out = _run_fixture(tmp_path)
    replay = runner.invoke(app, ["replay", "--run", str(out)])
    assert replay.exit_code == 0, replay.output
    manifest_path = out / "report-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["opportunities"] = []
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    result = runner.invoke(app, ["report-acceptance", "--run", str(out)])
    payload = json.loads(result.stdout)

    assert result.exit_code == 1
    assert payload["counts"]["opportunities"] == 0
    assert payload["checks"]["shortlist_nonempty"] is False
    assert any(row["check"] == "shortlist_nonempty" for row in payload["failures"])


def test_report_acceptance_fails_authorized_or_effectful_application_packet(
    tmp_path: Path,
) -> None:
    out = _run_fixture(tmp_path)
    replay = runner.invoke(app, ["replay", "--run", str(out)])
    assert replay.exit_code == 0, replay.output
    manifest_path = out / "report-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["application_packets"][0]["approval_status"] = "AUTHORIZED"
    manifest["application_packets"][0]["external_effects"] = True
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    result = runner.invoke(app, ["report-acceptance", "--run", str(out)])
    payload = json.loads(result.stdout)

    assert result.exit_code == 1
    assert payload["checks"]["application_packets_human_authorized_only"] is False
    assert any(
        row["check"] == "application_packets_human_authorized_only"
        for row in payload["failures"]
    )
