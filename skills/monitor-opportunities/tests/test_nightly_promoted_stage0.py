from __future__ import annotations

import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from monitor_opportunities.cli import app


runner = CliRunner()


class _HealthResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_promoted_stage0_nightly_writes_publication_receipts(
    tmp_path: Path, monkeypatch
) -> None:
    out = tmp_path / "nightly"

    monkeypatch.setattr(
        "monitor_opportunities.run_attestation.attest",
        lambda skill_dir: {
            "ok": True,
            "code": {
                "git_revision": "abc123",
                "git_revision_full": "abc123def456",
                "skill_tree_dirty": False,
            },
            "runtime": {"environment": "test"},
            "credentials": {"missing_required": []},
        },
    )

    def capture_ok(path: Path | None = None):
        evidence = None
        if path is not None:
            path.mkdir(parents=True, exist_ok=True)
            evidence = path / "evidence.json"
            evidence.write_text("{}\n", encoding="utf-8")
        return {
            "status": "OK",
            "opportunities_captured": 1,
            "prospects_captured": 1,
            "groups_captured": 1,
            "warm_paths_found": 0,
            "category_ids": [405, 546],
            "evidence_path": str(evidence) if evidence else None,
        }

    monkeypatch.setattr(
        "monitor_opportunities.browser_capture.capture_sam",
        lambda capture_dir: capture_ok(capture_dir),
    )
    monkeypatch.setattr(
        "monitor_opportunities.browser_capture.capture_linkedin_advanced_search",
        lambda capture_dir: capture_ok(capture_dir),
    )
    monkeypatch.setattr(
        "monitor_opportunities.browser_capture.capture_linkedin_top_applicant",
        lambda capture_dir: capture_ok(capture_dir),
    )
    monkeypatch.setattr(
        "monitor_opportunities.browser_capture.capture_linkedin_premium",
        lambda capture_dir: {"status": "NO_MATCHES", "opportunities_captured": 0},
    )
    monkeypatch.setattr(
        "monitor_opportunities.browser_capture.capture_sales_navigator_saved",
        lambda capture_dir: {"status": "NO_MATCHES", "prospects_captured": 0},
    )
    monkeypatch.setattr(
        "monitor_opportunities.browser_capture.capture_meetup_buffalo_isolated",
        lambda capture_dir: capture_ok(capture_dir),
    )
    monkeypatch.setattr(
        "monitor_opportunities.browser_capture.capture_ats_form",
        lambda apply_url, out_dir: {"status": "DEFERRED", "field_count": 0},
    )

    def fake_digest(run_dir, skill_dir, capture_dir, memory_url, steps, **kwargs):
        del skill_dir, capture_dir, memory_url, kwargs
        (run_dir / "morning-digest.json").write_text(
            '{"schema":"digest","counts":{"employment":1}}\n', encoding="utf-8"
        )
        steps["digest"] = {"status": "PASS"}

    monkeypatch.setattr("monitor_opportunities.nightly_digest.run_digest_phase", fake_digest)
    monkeypatch.setattr(
        "monitor_opportunities.nightly_digest.lane_health_phase",
        lambda run_dir, steps: steps.setdefault("lane_health", {"status": "PASS"}),
    )
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: _HealthResponse())

    def fake_subprocess_run(cmd, **kwargs):
        del kwargs
        action = cmd[1]
        if action == "run":
            (out / "report").mkdir(parents=True, exist_ok=True)
            (out / "report" / "report.json").write_text(
                '{"schema":"report","opportunities":[]}\n', encoding="utf-8"
            )
            (out / "report" / "index.html").write_text("<html></html>\n", encoding="utf-8")
            (out / "run-receipt.json").write_text(
                '{"external_effects":false,"degraded_contracts":[]}\n', encoding="utf-8"
            )
            return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")
        if action == "memory-sync":
            (out / "memory-sync-receipt.json").write_text(
                json.dumps(
                        {
                            "readback_found": True,
                            "relationship_readback_found": True,
                            "readback_external_effects_false": True,
                            "readback_missing_keys": [],
                            "relationship_signals_included": True,
                            "stored_keys": ["morning_opportunities/test"],
                            "external_effects": False,
                        }
                )
                + "\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")
        if action == "buzz-summary":
            receipt = out / "buzz-summary" / "buzz-summary-receipt.json"
            receipt.parent.mkdir(parents=True, exist_ok=True)
            receipt.write_text(
                json.dumps(
                    {
                        "posted": True,
                        "live": True,
                        "dry_run": False,
                        "external_effects": False,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")
        raise AssertionError(f"unexpected subprocess command: {cmd!r}")

    monkeypatch.setattr("subprocess.run", fake_subprocess_run)

    result = runner.invoke(app, ["nightly", "--promoted-stage0", "--out", str(out)])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["mode"] == "PROMOTED_STAGE_0"
    assert payload["external_effects"] is False
    assert Path(payload["artifacts"]["effect_policy"]).is_file()
    assert Path(payload["artifacts"]["memory"]).is_file()
    assert Path(payload["artifacts"]["buzz"]).is_file()
    effect_policy = json.loads(Path(payload["artifacts"]["effect_policy"]).read_text())
    assert effect_policy["publications"]["memory_summary"] == "ENABLED"
    assert effect_policy["publications"]["relationship_graph"] == "ENABLED"
    assert effect_policy["publications"]["buzz_summary"] == "ENABLED"
    assert effect_policy["separately_gated"]["tracker"] == "SKIPPED"
    assert effect_policy["separately_gated"]["ats_memory"] == "SKIPPED"
    assert effect_policy["forbidden_effects"]["gmail_send"] == "FORBIDDEN"
    assert effect_policy["forbidden_effects"]["linkedin_action"] == "FORBIDDEN"
    assert effect_policy["forbidden_effects"]["ats_submit"] == "FORBIDDEN"
