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
