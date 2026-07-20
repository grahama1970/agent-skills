"""Tests for the opt-in WebClaude sanity eval runner."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "webclaude_sanity_eval.py"
SPEC = importlib.util.spec_from_file_location("webclaude_sanity_eval", SCRIPT_PATH)
assert SPEC and SPEC.loader
webclaude_sanity_eval = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = webclaude_sanity_eval
SPEC.loader.exec_module(webclaude_sanity_eval)


def test_plan_result_lists_required_webclaude_eval_cases(tmp_path: Path) -> None:
    result = webclaude_sanity_eval.build_plan(
        run_dir=tmp_path,
        project="webclaude",
        tab_id="837359291",
        expect_url="https://claude.ai/chat/demo",
    )

    assert result["schema"] == "ask.webclaude_sanity_eval.v1"
    assert result["status"] == "planned"
    assert result["mocked"] is False
    assert result["live"] is False
    assert {case["name"] for case in result["cases"]} == {
        "browser_oracle_binding",
        "surf_tab_identity",
        "text_roundtrip",
        "zip_bundle_local",
        "zip_upload_visible",
        "zip_response_markers",
        "visual_receipt",
    }
    assert "plan-only" in result["failures"][0]


def test_zip_response_validator_requires_files_and_markers() -> None:
    markers = {
        "zip_response": "WEBCLAUDE_ZIP_UPLOAD_RESPONSE_TEST",
        "md": "WEBCLAUDE_MD_SENTINEL_TEST",
        "image": "WEBCLAUDE_IMAGE_SENTINEL_TEST",
    }
    filenames = ["webclaude-sanity-proof.md", "webclaude-sanity-proof-image.png"]
    response = "\n".join([markers["zip_response"], *filenames, markers["md"], markers["image"]])

    assert webclaude_sanity_eval.validate_zip_response(response, markers, filenames) == []
    assert webclaude_sanity_eval.validate_zip_response(response.replace(markers["image"], ""), markers, filenames) == [
        markers["image"]
    ]


def test_render_markdown_preserves_claim_scope(tmp_path: Path) -> None:
    result = webclaude_sanity_eval.build_plan(
        run_dir=tmp_path,
        project="webclaude",
        tab_id="",
        expect_url="https://claude.ai/chat/demo",
    )

    markdown = webclaude_sanity_eval.render_markdown(result)

    assert "a reusable surf claude.submit/webclaude.submit wrapper exists" in markdown
    assert "Markdown file and one PNG" in markdown
