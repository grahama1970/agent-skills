from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "webgpt_cli.py"
SPEC = importlib.util.spec_from_file_location("webgpt_cli", MODULE_PATH)
assert SPEC and SPEC.loader
webgpt_cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(webgpt_cli)


def test_exact_submission_target_requires_tab_and_url() -> None:
    with pytest.raises(ValueError):
        webgpt_cli._exact_submission_target({"tab_id": "837"})
    with pytest.raises(ValueError):
        webgpt_cli._exact_submission_target({"conversation_url": "https://chatgpt.com/c/example"})


def test_exact_submission_target_preserves_human_binding() -> None:
    assert webgpt_cli._exact_submission_target(
        {"tab_id": 837358135, "conversation_url": "https://chatgpt.com/c/example"}
    ) == ("837358135", "https://chatgpt.com/c/example")


def test_exact_submission_target_prefers_human_overrides() -> None:
    assert webgpt_cli._exact_submission_target(
        {"tab_id": "wrong", "conversation_url": "https://chatgpt.com/c/wrong"},
        "837358116",
        "https://chatgpt.com/c/right",
    ) == ("837358116", "https://chatgpt.com/c/right")


def test_routing_meta_requires_exact_non_created_tab() -> None:
    exact = {
        "requested_tab_id": "837358135",
        "controlled_tab_id": "837358135",
        "controlled_tab_id_mismatch": False,
        "tab_was_created": False,
    }
    assert webgpt_cli._routing_meta_is_exact(exact, "837358135")
    assert not webgpt_cli._routing_meta_is_exact({**exact, "tab_was_created": True}, "837358135")
    assert not webgpt_cli._routing_meta_is_exact({**exact, "controlled_tab_id": "other"}, "837358135")


def test_code_deliverable_rejects_architecture_prose(tmp_path: Path) -> None:
    response = tmp_path / "response.md"
    solution = tmp_path / "solution.zip"
    response.write_text("Here is a staged architecture and future roadmap.\n")
    assert not webgpt_cli._has_code_deliverable(response, solution)


def test_code_deliverable_accepts_unified_diff_or_zip(tmp_path: Path) -> None:
    response = tmp_path / "response.md"
    solution = tmp_path / "solution.zip"
    response.write_text("diff --git a/server.ts b/server.ts\n")
    assert webgpt_cli._has_code_deliverable(response, solution)
    response.write_text("prose only\n")
    solution.write_bytes(b"PK\x03\x04")
    assert webgpt_cli._has_code_deliverable(response, solution)


def test_submit_source_never_creates_a_tab() -> None:
    source = MODULE_PATH.read_text()
    submit_source = source[source.index("def submit(") : source.index("def _latest_bundle")]
    assert '"--create-tab"' not in submit_source
    assert '"--tab-id", tab_id' in submit_source
    assert '"--expect-url", conversation_url' in submit_source


def test_output_contract_modes_are_defined() -> None:
    assert webgpt_cli.WEBGPT_MODES == {"assess", "plan", "code", "all", "none"}


def test_all_mode_is_human_gated_and_sequential() -> None:
    source = MODULE_PATH.read_text()
    submit_source = source[source.index("def submit(") : source.index("def _submit_stage")]
    assert 'output_contract in {"plan", "all"}' in submit_source
    assert '("assess", "plan", "code") if output_contract == "all"' in submit_source
    assert "--architecture-authorized" in submit_source


def test_submit_and_activate_expose_explicit_target_options() -> None:
    source = MODULE_PATH.read_text()
    submit_source = source[source.index("def submit(") : source.index("def _submit_stage")]
    activate_source = source[source.index("def activate(") : source.index("def navigate(")]
    for command_source in (submit_source, activate_source):
        assert '"--tab-id"' in command_source
        assert '"--expect-url"' in command_source
    assert "_verify_desktop" not in activate_source


def test_assess_deliverable_requires_diagnosis_and_ruling(tmp_path: Path) -> None:
    resp = tmp_path / "r.md"
    resp.write_text("some prose without a verdict\n")
    assert not webgpt_cli._has_assess_deliverable(resp)
    resp.write_text("DIAGNOSIS: agent is spiraling\nBLOCKED_CURRENT_GATE: asset 403\n")
    assert webgpt_cli._has_assess_deliverable(resp)


def test_plan_deliverable_requires_task_plan(tmp_path: Path) -> None:
    resp = tmp_path / "r.md"
    resp.write_text("just an idea, no plan\n")
    assert not webgpt_cli._has_plan_deliverable(resp)
    resp.write_text("TASK_PLAN:\n1. fix asset route (server/index.ts); proof: curl 200\n")
    assert webgpt_cli._has_plan_deliverable(resp)


def test_deliverable_ok_dispatches_by_mode(tmp_path: Path) -> None:
    resp = tmp_path / "r.md"
    zp = tmp_path / "s.zip"
    resp.write_text("prose only\n")
    assert webgpt_cli._deliverable_ok("none", resp, zp) is True
    assert webgpt_cli._deliverable_ok("code", resp, zp) is False
    resp.write_text("diff --git a/x b/x\n")
    assert webgpt_cli._deliverable_ok("code", resp, zp) is True


def test_augment_bundle_injects_research_and_contract(tmp_path: Path) -> None:
    bp = tmp_path / "bundle.md"
    bp.write_text("original request body\n")
    aug = webgpt_cli._augment_bundle(bp, "code")
    text = aug.read_text()
    assert "## Research directive" in text
    assert "use your own web search" in text
    assert "## Output contract: CODE" in text
    assert "original request body" in text


def test_augment_bundle_keeps_zip_as_attachment_and_generates_prompt(tmp_path: Path) -> None:
    bp = tmp_path / "bundle.zip"
    bp.write_bytes(b"PK\x03\x04")
    augmented = webgpt_cli._augment_bundle(bp, "code")
    assert augmented != bp
    assert "attached as `bundle.zip`" in augmented.read_text()
    assert bp.read_bytes() == b"PK\x03\x04"


def test_goal_lock_wraps_top_and_bottom(tmp_path: Path) -> None:
    bp = tmp_path / "bundle.md"
    bp.write_text("BODY_MARKER original request\n")
    text = webgpt_cli._augment_bundle(bp, "code").read_text()
    assert "GOAL LOCK - read first" in text
    assert "final check" in text
    assert "FORBIDDEN from drifting" in text
    # top lock precedes the body; bottom lock follows it (last instruction wins)
    assert text.index("GOAL LOCK - read first") < text.index("BODY_MARKER")
    assert text.index("BODY_MARKER") < text.index("final check")


def test_goal_lock_skipped_for_none_mode(tmp_path: Path) -> None:
    bp = tmp_path / "bundle.md"
    bp.write_text("free form\n")
    text = webgpt_cli._augment_bundle(bp, "none").read_text()
    assert "GOAL LOCK" not in text


def test_submit_runs_browser_oracle_before_provenance_and_surf() -> None:
    source = MODULE_PATH.read_text()
    submit_source = source[source.index("def submit(") : source.index("def _raise_deliverable_missing")]
    assert submit_source.index("_resolve_submission_target") < submit_source.index("_source_provenance")
    submit_stage = source[source.index("def _submit_stage(") : source.index("def _latest_bundle")]
    assert "webgpt.preflight" in submit_stage
    assert '"kimi.submit"' in submit_stage


def test_provider_is_inferred_from_authoritative_url() -> None:
    assert webgpt_cli._provider_for_url("https://chatgpt.com/c/example") == (
        "webgpt",
        "webgpt",
    )
    assert webgpt_cli._provider_for_url("https://www.kimi.com/chat/example") == (
        "webkimi",
        "kimi",
    )


def test_unsupported_provider_fails_loudly() -> None:
    with pytest.raises(webgpt_cli.TargetResolutionError) as captured:
        webgpt_cli._provider_for_url("https://example.com/chat")
    assert captured.value.code == "PROVIDER_UNSUPPORTED"


def test_explicit_tab_resolution_uses_live_url_and_oracle_backend(monkeypatch) -> None:
    kimi_url = "https://www.kimi.com/chat/example"
    monkeypatch.setattr(
        webgpt_cli,
        "_tab_identity",
        lambda tab_id: {"id": tab_id, "url": kimi_url},
    )
    monkeypatch.setattr(
        webgpt_cli,
        "_browser_oracle_binding_for_tab",
        lambda backend, tab_id, url: {
            "name": "kimi-tab",
            "backend": backend,
            "tab_id": tab_id,
            "conversation_url": url,
        },
    )
    binding, transport, tab_id, url = webgpt_cli._resolve_submission_target(
        "ignored", ".", "837357145", ""
    )
    assert binding["backend"] == "webkimi"
    assert (transport, tab_id, url) == ("kimi", "837357145", kimi_url)


def test_project_submit_preserves_browser_oracle_tab_and_desktop_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    bundle = tmp_path / "bundle.md"
    bundle.write_text("ping\n", encoding="utf-8")
    calls: list[tuple[str, ...]] = []
    binding = {
        "readiness": "ready",
        "project": "battle",
        "name": "battle",
        "backend": "webgpt",
        "tab_id": "837356871",
        "conversation_url": "https://chatgpt.com/c/battle",
        "human_name": "battle",
        "kde_desktop_index": 2,
    }

    def fake_run_browser_oracle(*args: str) -> subprocess.CompletedProcess:
        calls.append(("browser-oracle", *args))
        return subprocess.CompletedProcess(args, 0, json.dumps(binding), "")

    def fake_surf(*args: str | int, **kwargs) -> subprocess.CompletedProcess:
        str_args = tuple(str(arg) for arg in args)
        calls.append(("surf", *str_args))
        if str_args[0] == "webgpt.preflight":
            return subprocess.CompletedProcess(str_args, 0, '{"ok":true}\n', "")
        if str_args[0] == "webgpt.submit":
            meta_path = Path(str_args[str_args.index("--meta-output") + 1])
            output_path = Path(str_args[str_args.index("--output") + 1])
            raw_path = Path(str_args[str_args.index("--raw-output") + 1])
            receipt_path = Path(str_args[str_args.index("--receipt-output") + 1])
            meta_path.write_text(
                json.dumps(
                    {
                        "requested_tab_id": "837356871",
                        "controlled_tab_id": "837356871",
                        "controlled_tab_id_mismatch": False,
                        "tab_was_created": False,
                        "browser_oracle_human_name": binding["human_name"],
                        "browser_oracle_kde_desktop_index": binding["kde_desktop_index"],
                    }
                ),
                encoding="utf-8",
            )
            output_path.write_text("PONG\n", encoding="utf-8")
            raw_path.write_text("PONG\n", encoding="utf-8")
            receipt_path.write_text('{"ok":true}\n', encoding="utf-8")
            return subprocess.CompletedProcess(str_args, 0, "ok\n", "")
        raise AssertionError(f"unexpected surf call: {str_args}")

    monkeypatch.setattr(webgpt_cli, "_run_browser_oracle", fake_run_browser_oracle)
    monkeypatch.setattr(webgpt_cli, "_surf", fake_surf)

    webgpt_cli.submit(
        bundle=str(bundle),
        project="battle",
        repo_root=str(tmp_path),
        output_contract="none",
        tab_id_override="",
        expected_url_override="",
        source_paths=[],
        timeout=900,
    )

    doctor_call = calls[0]
    assert doctor_call[:2] == ("browser-oracle", "doctor")
    assert "--project" in doctor_call and "battle" in doctor_call
    preflight_call = next(call for call in calls if call[:2] == ("surf", "webgpt.preflight"))
    submit_call = next(call for call in calls if call[:2] == ("surf", "webgpt.submit"))
    for call in (preflight_call, submit_call):
        assert "--tab-id" in call
        assert call[call.index("--tab-id") + 1] == "837356871"
        assert "--expect-url" in call
        assert call[call.index("--expect-url") + 1] == "https://chatgpt.com/c/battle"
        assert "--no-activate" in call
        assert "--create-tab" not in call
    assert "--no-remember" in submit_call
    meta = json.loads((tmp_path / "bundle-response.meta.json").read_text(encoding="utf-8"))
    assert meta["controlled_tab_id"] == binding["tab_id"]
    assert meta["controlled_tab_id_mismatch"] is False
    assert meta["browser_oracle_human_name"] == "battle"
    assert meta["browser_oracle_kde_desktop_index"] == 2


def test_submit_failure_summary_promotes_surf_lock_meta(tmp_path: Path, capsys) -> None:
    meta = tmp_path / "response.meta.json"
    meta.write_text(
        json.dumps(
            {
                "failure": "browser_cdp_lock_timeout",
                "browser_lock_blocked": True,
                "agent_diagnosis": "Surf could not run the CDP pre-submit probe because the shared browser lock was held.",
                "agent_action": "Wait for the lock owner to finish.",
                "cdp_retry_stderr": "SURF_BROWSER_LOCK_BLOCKED owner_pid=123",
            }
        ),
        encoding="utf-8",
    )

    webgpt_cli._emit_submit_failure_summary(meta)

    captured = capsys.readouterr()
    assert "BLOCKED_WEBGPT_BROWSER_CDP_LOCK_TIMEOUT" in captured.err
    assert "shared browser lock was held" in captured.err
    assert "Wait for the lock owner to finish." in captured.err
    assert "SURF_BROWSER_LOCK_BLOCKED" in captured.err


def test_explicit_tab_url_assertion_fails_before_oracle(monkeypatch) -> None:
    monkeypatch.setattr(
        webgpt_cli,
        "_tab_identity",
        lambda tab_id: {"id": tab_id, "url": "https://www.kimi.com/chat/right"},
    )
    with pytest.raises(webgpt_cli.TargetResolutionError) as captured:
        webgpt_cli._resolve_submission_target(
            "ignored", ".", "837357145", "https://www.kimi.com/chat/wrong"
        )
    assert captured.value.code == "TAB_IDENTITY_MISMATCH"


def test_provenance_block_contains_clone_sha_and_relative_paths() -> None:
    provenance = {
        "schema": "webgpt.source_provenance.v1",
        "repository_url": "https://github.com/example/project.git",
        "branch": "main",
        "upstream": "origin/main",
        "commit_sha": "a" * 40,
        "source_paths": ["src/app.py"],
        "proof_cwd": ".",
    }
    block = webgpt_cli._source_provenance_block(provenance)
    assert "git clone --filter=blob:none https://github.com/example/project.git" in block
    assert f"checkout --detach {'a' * 40}" in block
    assert '"src/app.py"' in block


def test_webgpt_issue_autofile_suppresses_recent_duplicate(tmp_path: Path, monkeypatch) -> None:
    title = "webgpt: submit-webgpt failed - busy"
    monkeypatch.setenv("WEBGPT_ISSUE_STATE_DIR", str(tmp_path))
    webgpt_cli._write_issue_marker(title, "https://github.com/grahama1970/agent-skills/issues/974")

    def fail_run(*_args, **_kwargs):
        raise AssertionError("gh should not run for a recent duplicate")

    monkeypatch.setattr(webgpt_cli.subprocess, "run", fail_run)

    assert webgpt_cli._file_issue(title, "body") is False


def test_webgpt_issue_autofile_reuses_open_duplicate(tmp_path: Path, monkeypatch) -> None:
    title = "webgpt: submit-webgpt failed - busy"
    monkeypatch.setenv("WEBGPT_ISSUE_STATE_DIR", str(tmp_path))
    calls: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        calls.append(list(cmd))
        if "list" in cmd:
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=json.dumps(
                    [
                        {
                            "number": 974,
                            "title": title,
                            "url": "https://github.com/grahama1970/agent-skills/issues/974",
                        }
                    ]
                ),
                stderr="",
            )
        raise AssertionError("gh issue create should be skipped for an open duplicate")

    monkeypatch.setattr(webgpt_cli.subprocess, "run", fake_run)

    assert webgpt_cli._file_issue(title, "body") is False
    assert any("list" in call for call in calls)
    marker_payload = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert marker_payload["url"].endswith("/974")
