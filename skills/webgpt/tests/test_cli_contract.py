from __future__ import annotations

import importlib.util
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


def test_submit_activate_and_download_expose_explicit_target_options() -> None:
    source = MODULE_PATH.read_text()
    submit_source = source[source.index("def submit(") : source.index("def _submit_stage")]
    activate_source = source[source.index("def activate(") : source.index("def navigate(")]
    download_source = source[source.index("def download(") : source.index("def listen(")]
    for command_source in (submit_source, activate_source, download_source):
        assert '"--tab-id"' in command_source
        assert '"--expect-url"' in command_source
    assert "_verify_desktop" not in activate_source
    assert "_active_chatgpt_tab" not in download_source


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


def test_augment_bundle_leaves_zip_untouched(tmp_path: Path) -> None:
    bp = tmp_path / "bundle.zip"
    bp.write_bytes(b"PK\x03\x04")
    assert webgpt_cli._augment_bundle(bp, "code") == bp
