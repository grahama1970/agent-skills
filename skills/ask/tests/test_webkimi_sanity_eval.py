"""Tests for the opt-in WebKimi sanity eval runner."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "webkimi_sanity_eval.py"
SPEC = importlib.util.spec_from_file_location("webkimi_sanity_eval", SCRIPT_PATH)
assert SPEC and SPEC.loader
webkimi_sanity_eval = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = webkimi_sanity_eval
SPEC.loader.exec_module(webkimi_sanity_eval)


def test_plan_result_lists_required_webkimi_eval_cases(tmp_path: Path) -> None:
    result = webkimi_sanity_eval.build_plan(
        run_dir=tmp_path,
        project="webkimi",
        tab_id="837359704",
        expect_url="https://www.kimi.com/chat/demo",
    )

    assert result["schema"] == "ask.webkimi_sanity_eval.v1"
    assert result["status"] == "planned"
    assert result["mocked"] is False
    assert result["live"] is False
    assert {case["name"] for case in result["cases"]} == {
        "browser_oracle_binding",
        "surf_tab_identity",
        "text_roundtrip_no_activate",
        "markdown_attachment_roundtrip",
        "image_attachment_roundtrip",
        "visual_receipt",
    }
    assert "plan-only" in result["failures"][0]


def test_submit_response_validator_requires_markers_and_clean_meta() -> None:
    marker = "WEBKIMI_TEXT_SENTINEL_TEST"
    meta = {
        "status": "completed",
        "clean_contains_sentinel": False,
        "clean_contamination_markers": [],
        "controlled_tab_id_mismatch": False,
        "activation_violation": False,
    }

    assert webkimi_sanity_eval.validate_submit_response(marker, meta, [marker]) == []

    contaminated = {**meta, "clean_contamination_markers": ["Completion contract for browser automation:"]}
    assert "clean output must not contain contamination markers" in webkimi_sanity_eval.validate_submit_response(
        marker, contaminated, [marker]
    )
    assert webkimi_sanity_eval.validate_submit_response("no marker", meta, [marker]) == [marker]


def test_render_markdown_preserves_attachment_scope(tmp_path: Path) -> None:
    result = webkimi_sanity_eval.build_plan(
        run_dir=tmp_path,
        project="webkimi",
        tab_id="",
        expect_url="https://www.kimi.com/chat/demo",
    )

    markdown = webkimi_sanity_eval.render_markdown(result)

    assert "attachment support when the attachment gates fail" in markdown
    assert "Markdown with a hidden sentinel" in markdown
