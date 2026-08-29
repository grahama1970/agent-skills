from __future__ import annotations

import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from monitor_opportunities.cli import app
from monitor_opportunities.pipeline import run_stage0

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
        "monitor_opportunities.browser_capture.capture_linkedin_who_viewed",
        lambda capture_dir: {"status": "EMPTY", "viewers_captured": 0},
    )
    monkeypatch.setattr(
        "monitor_opportunities.browser_capture.capture_linkedin_actively_hiring",
        lambda capture_dir: {"status": "EMPTY", "contacts_captured": 0},
    )
    monkeypatch.setattr(
        "monitor_opportunities.browser_capture.capture_indeed_jobs",
        lambda capture_dir: {**capture_ok(capture_dir), "records_captured": 1},
    )
    monkeypatch.setattr(
        "monitor_opportunities.browser_capture.capture_hiddenjobs",
        lambda capture_dir: {**capture_ok(capture_dir), "records_captured": 1},
    )
    monkeypatch.setattr(
        "monitor_opportunities.browser_capture.capture_g2i_slack_jobs",
        lambda capture_dir: {**capture_ok(capture_dir), "records_captured": 1},
    )
    monkeypatch.setattr(
        "monitor_opportunities.browser_capture.capture_sales_navigator_saved",
        lambda capture_dir: {"status": "NO_MATCHES", "prospects_captured": 0},
    )
    monkeypatch.setattr(
        "monitor_opportunities.browser_capture.capture_meetup_buffalo_isolated",
        lambda capture_dir, **_kwargs: capture_ok(capture_dir),
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
    semantic_prepare_calls = []

    def fake_semantic_prepare(*, run_dir: Path, out_dir: Path, top_n: int):
        semantic_prepare_calls.append({"run_dir": run_dir, "out_dir": out_dir, "top_n": top_n})
        out_dir.mkdir(parents=True, exist_ok=True)
        receipt = {
            "schema": "monitor_opportunities.tau_semantic_prepare_receipt.v1",
            "status": "PASS",
            "selected_count": 2,
            "rejected_count": 0,
            "selected": [
                {
                    "rank": 1,
                    "opportunity_id": "candidate:a:first",
                    "artifact": str(out_dir / "semantic-inputs" / "01-candidate-a-first.json"),
                },
                {
                    "rank": 2,
                    "opportunity_id": "candidate:a:second",
                    "artifact": str(out_dir / "semantic-inputs" / "02-candidate-a-second.json"),
                }
            ],
            "provider_live": False,
            "mocked": False,
            "live": True,
            "external_effects": False,
        }
        (out_dir / "tau-semantic-prepare-receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return receipt

    monkeypatch.setattr(
        "monitor_opportunities.cli.prepare_tau_semantic_inputs",
        fake_semantic_prepare,
    )
    def fake_provider_eval(**kwargs):
        input_path = Path(str(kwargs["input_path"]))
        if "first" in input_path.name:
            raise subprocess.TimeoutExpired(["ask", "tau-dag"], 60)
        return {
            "schema": "monitor_opportunities.tau_semantic_provider_receipt.v1",
            "status": "PASS",
            "opportunity_id": "candidate:a:second",
            "provider_live": True,
            "live": True,
            "mocked": False,
            "external_effects": False,
        }

    monkeypatch.setattr(
        "monitor_opportunities.cli.run_provider_semantic_eval",
        fake_provider_eval,
    )

    def fake_semantic_install(*, run_dir: Path, provider_receipt_path: Path):
        del provider_receipt_path
        index = run_dir / "semantic-addenda" / "index.json"
        index.parent.mkdir(parents=True, exist_ok=True)
        index.write_text(
            json.dumps(
                {
                    "schema": "monitor_opportunities.semantic_addenda_index.v1",
                    "addenda": [{"opportunity_id": "candidate:a:second"}],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return {"status": "PASS", "provider_live": True, "external_effects": False}

    monkeypatch.setattr("monitor_opportunities.cli.install_semantic_addendum", fake_semantic_install)
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: _HealthResponse())

    def fake_subprocess_run(cmd, **kwargs):
        del kwargs
        action = cmd[1]
        if action == "run":
            run_stage0(
                Path(__file__).parents[1],
                out,
                fixture_dir=Path(__file__).parent / "fixtures" / "discovery",
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
        if action == "notify":
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=json.dumps(
                    {
                        "schema": "ops_discord.notification_receipt.v1",
                        "status": "SENT",
                        "webhook": "discord",
                        "source": "env:DISCORD_WEBHOOK_URL",
                        "message_url": "https://discord.com/channels/1/2/3",
                    }
                ),
                stderr="",
            )
        raise AssertionError(f"unexpected subprocess command: {cmd!r}")

    monkeypatch.setattr("subprocess.run", fake_subprocess_run)

    result = runner.invoke(app, ["nightly", "--promoted-stage0", "--out", str(out)])

    assert result.exit_code == 0, result.output
    assert "MONITOR-OPPORTUNITIES TERMINAL REPORT" in result.output
    payload = json.loads((out / "nightly-receipt.json").read_text(encoding="utf-8"))
    assert payload["mode"] == "PROMOTED_STAGE_0"
    assert payload["external_effects"] is False
    assert Path(payload["artifacts"]["effect_policy"]).is_file()
    assert Path(payload["artifacts"]["memory"]).is_file()
    assert payload["artifacts"]["buzz"] is None
    assert Path(payload["artifacts"]["discord_handoff"]).is_file()
    assert Path(payload["artifacts"]["tau_semantic_prepare"]).is_file()
    assert Path(payload["artifacts"]["receipt_consistency"]).is_file()
    assert Path(payload["artifacts"]["zero_effect_replay"]).is_file()
    assert Path(payload["artifacts"]["report_acceptance"]).is_file()
    assert payload["receipt_consistency_status"] == "PASS"
    assert payload["report_acceptance_status"] == "PASS"
    assert payload["artifact_hashes"]["report_acceptance"]
    consistency = json.loads(Path(payload["artifacts"]["receipt_consistency"]).read_text())
    assert consistency["schema"] == "monitor_opportunities.receipt_consistency.v1"
    assert consistency["required_nulls"] == 0
    assert consistency["count_mismatches"] == 0
    states = {row["destination"]: row for row in consistency["publication_states"]}
    assert states["memory_summary"]["effect_class"] == "INTERNAL_DESTINATION_WRITTEN"
    assert states["memory_summary"]["status"] == "WRITTEN"
    assert states["buzz_summary"]["status"] == "NOT_ATTEMPTED"
    assert states["discord_handoff"]["evidence_field"] == "morning-discord-receipt.status"
    assert states["discord_handoff"]["effect_class"] == "INTERNAL_DESTINATION_WRITTEN"
    assert states["discord_handoff"]["status"] == "WRITTEN"
    assert payload["steps"]["discord_handoff"]["status"] == "PASS"
    assert payload["steps"]["discord_handoff"]["ops_discord_status"] == "SENT"
    assert payload["steps"]["discord_handoff"]["external_effects"] is True
    assert payload["steps"]["tau_semantic"]["status"] == "PASS"
    assert payload["steps"]["tau_semantic"]["selected_count"] == 2
    assert payload["steps"]["tau_semantic"]["provider_live"] is True
    assert payload["steps"]["tau_semantic"]["installed_addenda"] == 1
    assert [row["status"] for row in payload["steps"]["tau_semantic"]["provider_results"]] == [
        "ERROR",
        "PASS",
    ]
    assert payload["steps"]["zero_effect_replay"]["status"] == "PASS"
    zero_effect_replay = json.loads(Path(payload["artifacts"]["zero_effect_replay"]).read_text())
    assert zero_effect_replay["schema"] == "monitor_opportunities.zero_effect_replay_receipt.v1"
    assert zero_effect_replay["status"] == "PASS"
    assert zero_effect_replay["mode"] == "PROMOTED_STAGE_0"
    assert zero_effect_replay["checks"]["projection_external_effects_false"] is True
    assert zero_effect_replay["checks"]["run_receipt_external_effects_false"] is True
    assert zero_effect_replay["checks"]["receipt_consistency_pass"] is True
    assert zero_effect_replay["external_effects"] is False
    report_acceptance = json.loads(Path(payload["artifacts"]["report_acceptance"]).read_text())
    assert report_acceptance["schema"] == "monitor_opportunities.report_acceptance_receipt.v1"
    assert report_acceptance["status"] == "PASS"
    assert report_acceptance["checks"]["zero_effect_replay_binding_current"] is True
    run_receipt = json.loads((out / "run-receipt.json").read_text(encoding="utf-8"))
    assert run_receipt["report_acceptance_required"] is True
    assert run_receipt["promoted_stage0_final_gate"] == "report_acceptance"
    assert semantic_prepare_calls == [
        {"run_dir": out, "out_dir": out / "tau-semantic", "top_n": 3}
    ]
    effect_policy = json.loads(Path(payload["artifacts"]["effect_policy"]).read_text())
    assert effect_policy["publications"]["memory_summary"] == "ENABLED"
    assert effect_policy["publications"]["relationship_graph"] == "ENABLED"
    assert effect_policy["publications"]["buzz_summary"] == "SKIPPED"
    assert effect_policy["publications"]["discord_handoff"] == "ENABLED"
    assert effect_policy["read_only_checks"]["prior_application_history"] == "ENABLED"
    assert effect_policy["separately_gated"]["tracker"] == "SKIPPED"
    assert effect_policy["separately_gated"]["ats_selector_memory_write"] == "SKIPPED"
    assert effect_policy["forbidden_effects"]["gmail_send"] == "FORBIDDEN"
    assert effect_policy["forbidden_effects"]["linkedin_action"] == "FORBIDDEN"
    assert effect_policy["forbidden_effects"]["ats_submit"] == "FORBIDDEN"


def test_promoted_stage0_fails_on_zero_effect_replay_failure_and_replaces_stale_pass(
    tmp_path: Path, monkeypatch
) -> None:
    out = tmp_path / "nightly"
    stale_replay = out / "zero-effect-replay-receipt.json"
    stale_replay.parent.mkdir(parents=True)
    stale_replay.write_text(
        '{"schema":"monitor_opportunities.zero_effect_replay_receipt.v1","status":"PASS"}\n',
        encoding="utf-8",
    )

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
        "monitor_opportunities.browser_capture.capture_linkedin_who_viewed",
        lambda capture_dir: {"status": "EMPTY", "viewers_captured": 0},
    )
    monkeypatch.setattr(
        "monitor_opportunities.browser_capture.capture_linkedin_actively_hiring",
        lambda capture_dir: {"status": "EMPTY", "contacts_captured": 0},
    )
    monkeypatch.setattr(
        "monitor_opportunities.browser_capture.capture_indeed_jobs",
        lambda capture_dir: {**capture_ok(capture_dir), "records_captured": 1},
    )
    monkeypatch.setattr(
        "monitor_opportunities.browser_capture.capture_hiddenjobs",
        lambda capture_dir: {**capture_ok(capture_dir), "records_captured": 1},
    )
    monkeypatch.setattr(
        "monitor_opportunities.browser_capture.capture_g2i_slack_jobs",
        lambda capture_dir: {**capture_ok(capture_dir), "records_captured": 1},
    )
    monkeypatch.setattr(
        "monitor_opportunities.browser_capture.capture_sales_navigator_saved",
        lambda capture_dir: {"status": "NO_MATCHES", "prospects_captured": 0},
    )
    monkeypatch.setattr(
        "monitor_opportunities.browser_capture.capture_meetup_buffalo_isolated",
        lambda capture_dir, **_kwargs: capture_ok(capture_dir),
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

    def fake_semantic_prepare(*, run_dir: Path, out_dir: Path, top_n: int):
        del run_dir, top_n
        out_dir.mkdir(parents=True, exist_ok=True)
        receipt = {
            "schema": "monitor_opportunities.tau_semantic_prepare_receipt.v1",
            "status": "PASS",
            "selected_count": 1,
            "rejected_count": 0,
            "selected": [
                {
                    "rank": 1,
                    "opportunity_id": "candidate:a:test",
                    "artifact": str(out_dir / "semantic-inputs" / "01-candidate-a-test.json"),
                }
            ],
            "provider_live": False,
            "mocked": False,
            "live": True,
            "external_effects": False,
        }
        (out_dir / "tau-semantic-prepare-receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return receipt

    monkeypatch.setattr(
        "monitor_opportunities.cli.prepare_tau_semantic_inputs",
        fake_semantic_prepare,
    )
    monkeypatch.setattr(
        "monitor_opportunities.cli.run_provider_semantic_eval",
        lambda **kwargs: {
            "schema": "monitor_opportunities.tau_semantic_provider_receipt.v1",
            "status": "PASS",
            "opportunity_id": "candidate:a:test",
            "provider_live": True,
            "live": True,
            "mocked": False,
            "external_effects": False,
        },
    )

    def fake_semantic_install(*, run_dir: Path, provider_receipt_path: Path):
        del provider_receipt_path
        index = run_dir / "semantic-addenda" / "index.json"
        index.parent.mkdir(parents=True, exist_ok=True)
        index.write_text(
            json.dumps(
                {
                    "schema": "monitor_opportunities.semantic_addenda_index.v1",
                    "addenda": [{"opportunity_id": "candidate:a:test"}],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return {"status": "PASS", "provider_live": True, "external_effects": False}

    monkeypatch.setattr("monitor_opportunities.cli.install_semantic_addendum", fake_semantic_install)
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: _HealthResponse())
    monkeypatch.setattr(
        "monitor_opportunities.cli.replay_decisions",
        lambda run_dir: {
            "schema": "monitor_opportunities.decision_projection.v1",
            "run_dir": str(run_dir),
            "event_count": 0,
            "external_effects": True,
            "items": {},
            "projection_digest": "poisoned",
        },
    )

    def fake_subprocess_run(cmd, **kwargs):
        del kwargs
        action = cmd[1]
        if action == "run":
            run_stage0(
                Path(__file__).parents[1],
                out,
                fixture_dir=Path(__file__).parent / "fixtures" / "discovery",
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
        if action == "notify":
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=json.dumps(
                    {
                        "schema": "ops_discord.notification_receipt.v1",
                        "status": "SENT",
                        "webhook": "discord",
                        "source": "env:DISCORD_WEBHOOK_URL",
                        "message_url": "https://discord.com/channels/1/2/3",
                    }
                ),
                stderr="",
            )
        raise AssertionError(f"unexpected subprocess command: {cmd!r}")

    monkeypatch.setattr("subprocess.run", fake_subprocess_run)

    result = runner.invoke(app, ["nightly", "--promoted-stage0", "--out", str(out)])

    assert result.exit_code == 2
    assert "PROMOTED_STAGE0_ZERO_EFFECT_REPLAY_FAILED" in result.stderr
    replay_receipt = json.loads(stale_replay.read_text(encoding="utf-8"))
    assert replay_receipt["status"] == "FAIL"
    assert replay_receipt["checks"]["projection_external_effects_false"] is False
    assert replay_receipt["projection_digest"] == "poisoned"


def test_promoted_stage0_fails_on_report_acceptance_failure(
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
        "monitor_opportunities.browser_capture.capture_linkedin_who_viewed",
        lambda capture_dir: {"status": "EMPTY", "viewers_captured": 0},
    )
    monkeypatch.setattr(
        "monitor_opportunities.browser_capture.capture_linkedin_actively_hiring",
        lambda capture_dir: {"status": "EMPTY", "contacts_captured": 0},
    )
    monkeypatch.setattr(
        "monitor_opportunities.browser_capture.capture_indeed_jobs",
        lambda capture_dir: {**capture_ok(capture_dir), "records_captured": 1},
    )
    monkeypatch.setattr(
        "monitor_opportunities.browser_capture.capture_hiddenjobs",
        lambda capture_dir: {**capture_ok(capture_dir), "records_captured": 1},
    )
    monkeypatch.setattr(
        "monitor_opportunities.browser_capture.capture_g2i_slack_jobs",
        lambda capture_dir: {**capture_ok(capture_dir), "records_captured": 1},
    )
    monkeypatch.setattr(
        "monitor_opportunities.browser_capture.capture_sales_navigator_saved",
        lambda capture_dir: {"status": "NO_MATCHES", "prospects_captured": 0},
    )
    monkeypatch.setattr(
        "monitor_opportunities.browser_capture.capture_meetup_buffalo_isolated",
        lambda capture_dir, **_kwargs: capture_ok(capture_dir),
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

    def fake_semantic_prepare(*, run_dir: Path, out_dir: Path, top_n: int):
        del run_dir, top_n
        out_dir.mkdir(parents=True, exist_ok=True)
        receipt = {
            "schema": "monitor_opportunities.tau_semantic_prepare_receipt.v1",
            "status": "PASS",
            "selected_count": 1,
            "rejected_count": 0,
            "selected": [
                {
                    "rank": 1,
                    "opportunity_id": "candidate:a:test",
                    "artifact": str(out_dir / "semantic-inputs" / "01-candidate-a-test.json"),
                }
            ],
            "provider_live": False,
            "mocked": False,
            "live": True,
            "external_effects": False,
        }
        (out_dir / "tau-semantic-prepare-receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return receipt

    monkeypatch.setattr(
        "monitor_opportunities.cli.prepare_tau_semantic_inputs",
        fake_semantic_prepare,
    )
    monkeypatch.setattr(
        "monitor_opportunities.cli.run_provider_semantic_eval",
        lambda **kwargs: {
            "schema": "monitor_opportunities.tau_semantic_provider_receipt.v1",
            "status": "PASS",
            "opportunity_id": "candidate:a:test",
            "provider_live": True,
            "live": True,
            "mocked": False,
            "external_effects": False,
        },
    )

    def fake_semantic_install(*, run_dir: Path, provider_receipt_path: Path):
        del provider_receipt_path
        index = run_dir / "semantic-addenda" / "index.json"
        index.parent.mkdir(parents=True, exist_ok=True)
        index.write_text(
            json.dumps(
                {
                    "schema": "monitor_opportunities.semantic_addenda_index.v1",
                    "addenda": [{"opportunity_id": "candidate:a:test"}],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return {"status": "PASS", "provider_live": True, "external_effects": False}

    monkeypatch.setattr("monitor_opportunities.cli.install_semantic_addendum", fake_semantic_install)
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: _HealthResponse())

    def fake_acceptance(*args, **kwargs):
        del args, kwargs
        return {
            "schema": "monitor_opportunities.report_acceptance_receipt.v1",
            "status": "FAIL",
            "external_effects": False,
            "failures": [{"check": "test_acceptance", "detail": "forced failure"}],
        }

    monkeypatch.setattr(
        "monitor_opportunities.cli.validate_report_acceptance",
        fake_acceptance,
    )

    def fake_subprocess_run(cmd, **kwargs):
        del kwargs
        action = cmd[1]
        if action == "run":
            run_stage0(
                Path(__file__).parents[1],
                out,
                fixture_dir=Path(__file__).parent / "fixtures" / "discovery",
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
        if action == "notify":
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=json.dumps(
                    {
                        "schema": "ops_discord.notification_receipt.v1",
                        "status": "SENT",
                        "webhook": "discord",
                        "source": "env:DISCORD_WEBHOOK_URL",
                        "message_url": "https://discord.com/channels/1/2/3",
                    }
                ),
                stderr="",
            )
        raise AssertionError(f"unexpected subprocess command: {cmd!r}")

    monkeypatch.setattr("subprocess.run", fake_subprocess_run)

    result = runner.invoke(app, ["nightly", "--promoted-stage0", "--out", str(out)])

    assert result.exit_code == 2
    assert "PROMOTED_STAGE0_REPORT_ACCEPTANCE_FAILED" in result.stderr
    assert not (out / "nightly-receipt.json").exists()
