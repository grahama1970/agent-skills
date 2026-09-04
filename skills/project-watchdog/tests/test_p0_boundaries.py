"""Regressions for the 2026-09-04 WebGPT P0 boundary fixes."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from watchdog import alerts, receipt_schema  # noqa: E402


def test_minted_triage_code_from_watchdog_layer_passes_receipt_validator():
    # triage-error mints from the layer; the code it produces for
    # 'project-watchdog' must satisfy the receipt validator, not be rejected.
    assert receipt_schema.is_valid_failure_code(
        "project_watchdog_unclassified_abcd1234"
    )
    # the pre-fix hyphenated shape must NOT validate (proves the fix matters)
    assert not receipt_schema.is_valid_failure_code(
        "project-watchdog_unclassified_abcd1234"
    )


def _run_alert(monkeypatch, tmp_path, notify_stdout, returncode, dry):
    import subprocess

    monkeypatch.setenv("PROJECT_WATCHDOG_STATE_ROOT", str(tmp_path))

    class _Proc:
        def __init__(self):
            self.stdout = notify_stdout
            self.stderr = ""
            self.returncode = returncode

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc())
    fake_run_sh = tmp_path / "ops-discord-run.sh"
    fake_run_sh.write_text("#!/bin/sh\n")
    monkeypatch.setattr(alerts, "OPS_DISCORD_RUN_SH", fake_run_sh)
    receipt = {
        "schema": "agent_skills.project_watchdog.tick_receipt.v1",
        "run_id": "r", "status": "BLOCKED", "apply": not dry, "project": "p",
        "handled_issues": [],
    }
    alerts.maybe_alert(receipt)
    return receipt["alert"], alerts._alerts_state_path()


def test_dry_run_exit_zero_does_not_advance_dedupe(monkeypatch, tmp_path):
    alert, state_path = _run_alert(
        monkeypatch, tmp_path, '{"status":"DRY_RUN"}', 0, dry=True)
    assert alert["delivered"] is False
    assert not state_path.exists(), "dry run must not write a dedupe timestamp"


def test_unverified_send_without_message_ref_does_not_advance_dedupe(monkeypatch, tmp_path):
    alert, state_path = _run_alert(
        monkeypatch, tmp_path, '{"status":"SENT"}', 0, dry=False)
    assert alert["delivered"] is False, "SENT without message_id/url is unverified"
    assert not state_path.exists()


def test_verified_sent_with_message_id_advances_dedupe(monkeypatch, tmp_path):
    alert, state_path = _run_alert(
        monkeypatch, tmp_path,
        '{"status":"SENT","message_id":"123","message_url":"https://x/1"}',
        0, dry=False)
    assert alert["delivered"] is True
    assert state_path.exists(), "a verified delivery must record the dedupe timestamp"


def test_worktree_lease_registered_on_exit_code_zero(monkeypatch, tmp_path):
    # The registration branch read added.get("returncode"), but git()/run_cmd
    # record exit_code, so the lease NEVER registered (stranded-worktree root
    # cause, memory#158). Prove it fires on exit_code 0 now.
    from watchdog import registry

    calls = {"registered": 0}
    monkeypatch.setattr(
        registry, "_register_worktree_lease",
        lambda *a, **k: calls.__setitem__("registered", calls["registered"] + 1))

    # git() is a nested closure over run_cmd; mock run_cmd so every git
    # subcommand reports exit_code 0 with empty output.
    monkeypatch.setattr(
        registry, "run_cmd",
        lambda *a, **k: {"exit_code": 0, "stdout": "", "stderr": ""})
    repo = tmp_path / "repo"
    repo.mkdir()
    wt = tmp_path / "wt"
    result = registry.prepare_repair_worktree(repo, wt, 42)
    assert result["ok"] is True
    assert calls["registered"] == 1, "lease must register when worktree add exits 0"


def _tick_env(monkeypatch, tmp_path, state_doc, registry_doc):
    import json as _json
    (tmp_path / "state.json").write_text(_json.dumps(state_doc))
    reg = tmp_path / "projects.json"
    reg.write_text(_json.dumps(registry_doc))
    monkeypatch.setenv("PROJECT_WATCHDOG_STATE_ROOT", str(tmp_path))
    monkeypatch.setenv("PROJECT_WATCHDOG_PROJECTS_PATH", str(reg))


def test_invalid_global_state_blocks_whole_tick(monkeypatch, tmp_path):
    from watchdog import commands
    _tick_env(monkeypatch, tmp_path,
              {"schema": "agent_skills.project_watchdog.state.v1",
               "global": {"state": "banana"}, "projects": {}},
              {"schema": "agent_skills.project_watchdog.registry.v1",
               "projects": [{"project_id": "p", "repo": "o/n", "worktree": str(tmp_path)}]})
    rc = commands.tick(apply=False, project_id="all", max_tickets=1)
    assert rc == 1, "an invalid global.state literal must block the tick fail-closed"


def test_invalid_registry_envelope_blocks_whole_tick(monkeypatch, tmp_path):
    # Envelope failure (projects is not a list) means project boundaries cannot
    # be trusted -> block the whole tick.
    from watchdog import commands
    _tick_env(monkeypatch, tmp_path,
              {"schema": "agent_skills.project_watchdog.state.v1",
               "global": {"state": "active"}, "projects": {}},
              {"schema": "agent_skills.project_watchdog.registry.v1",
               "projects": "not-a-list"})
    rc = commands.tick(apply=False, project_id="all", max_tickets=1)
    assert rc == 1, "an invalid registry envelope must block the tick fail-closed"


def test_one_malformed_entry_quarantines_not_blocks(monkeypatch, tmp_path, capsys):
    # One malformed ProjectEntry (bad repo) must NOT deny service to the fleet:
    # it is quarantined INVALID_CONFIG, fleet_health flips to NEEDS_ATTENTION,
    # and the tick proceeds past the registry boundary rather than blocking on
    # invalid_registry_document.
    import json as _json
    from watchdog import commands
    _tick_env(monkeypatch, tmp_path,
              {"schema": "agent_skills.project_watchdog.state.v1",
               "global": {"state": "active"}, "projects": {}},
              {"schema": "agent_skills.project_watchdog.registry.v1",
               "projects": [
                   {"project_id": "bad", "repo": "not-owner-name", "worktree": str(tmp_path)},
                   {"project_id": "good", "repo": "o/n", "worktree": str(tmp_path)},
               ]})
    commands.tick(apply=False, project_id="all", max_tickets=1)
    out = capsys.readouterr().out
    receipt = _json.loads(out[out.find("{"):])
    assert receipt.get("stop_reason") != "invalid_registry_document", \
        "a single bad entry must not block the whole registry"
    q = receipt.get("quarantined_projects") or []
    assert any(item.get("project_id") == "bad" and item.get("reason") == "INVALID_CONFIG"
               for item in q), "the malformed entry must be quarantined INVALID_CONFIG"
    assert receipt.get("fleet_health") == "NEEDS_ATTENTION"


def test_valid_docs_do_not_block_on_validation(monkeypatch, tmp_path):
    from watchdog import commands
    _tick_env(monkeypatch, tmp_path,
              {"schema": "agent_skills.project_watchdog.state.v1",
               "global": {"state": "active"}, "projects": {}},
              {"schema": "agent_skills.project_watchdog.registry.v1",
               "projects": []})
    rc = commands.tick(apply=False, project_id="all", max_tickets=1)
    assert rc == 0, "valid docs must not be blocked by the validation boundary"
