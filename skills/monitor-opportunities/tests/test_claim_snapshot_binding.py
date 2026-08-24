"""Claim-bearing artifacts bind to one run-scoped snapshot."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from monitor_opportunities.cli import _nightly_subprocess_env, app
from monitor_opportunities.contracts import ContractError
from monitor_opportunities.pipeline import _resolve_claim_snapshot_path
from monitor_opportunities.util import sha256_json

runner = CliRunner()
SKILL_DIR = Path("skills/monitor-opportunities")


def test_live_run_cannot_resolve_claims_from_test_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture_claims = SKILL_DIR / "tests" / "fixtures" / "claims" / "approved-claims.json"
    monkeypatch.setenv("MONITOR_CLAIM_SNAPSHOT_PATH", str(fixture_claims))
    with pytest.raises(ContractError) as exc:
        _resolve_claim_snapshot_path(SKILL_DIR, None, True)
    assert exc.value.code == "TEST_FIXTURE_AUTHORITY_FORBIDDEN"


def test_nightly_uses_default_authority_claim_snapshot_when_env_is_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skill_dir = tmp_path / "monitor-opportunities"
    claim_snapshot = skill_dir / "local" / "nightly" / "authority" / "claim-snapshot.json"
    claim_snapshot.parent.mkdir(parents=True)
    claim_snapshot.write_text(
        json.dumps(
            {
                "schema": "monitor_opportunities.claim_snapshot.v1",
                "active": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("MONITOR_CLAIM_SNAPSHOT_PATH", raising=False)

    steps: dict[str, object] = {}
    env = _nightly_subprocess_env(skill_dir, steps)

    assert env["MONITOR_CLAIM_SNAPSHOT_PATH"] == str(claim_snapshot.resolve())
    assert steps["claim_snapshot_authority"] == {
        "source": "default_authority",
        "path": str(claim_snapshot.resolve()),
        "exists": True,
    }


def test_report_claim_artifacts_share_one_snapshot_digest(tmp_path: Path) -> None:
    fixture_dir = SKILL_DIR / "tests" / "fixtures" / "discovery"
    out = tmp_path / "run"
    result = runner.invoke(app, ["run", "--fixture-dir", str(fixture_dir), "--out", str(out)])
    assert result.exit_code == 0, result.output
    snapshot = json.loads((out / "claim-snapshot.json").read_text())
    digest = sha256_json(snapshot)
    manifest = json.loads((out / "report-manifest.json").read_text())
    assert {row["claim_snapshot_sha256"] for row in manifest["resume_variants"]} == {digest}
    assert {row["claim_snapshot_sha256"] for row in manifest["outreach_packets"]} == {digest}
    assert {row["claim_snapshot_digest"] for row in manifest["application_packets"]} == {digest}
