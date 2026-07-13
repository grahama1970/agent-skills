"""Focused tests for WebGPT's code-deliverable execution gate."""

from pathlib import Path
import zipfile

from test_execution_lock import MODULE


VALID_GATE = """
current_gate: fix explicit tab preservation
blocking_defect: submit always creates a new tab
allowed_files: skills/webgpt/scripts/webgpt_cli.py
required_live_proof: explicit tab receives the request
stop_condition: code patch is returned and applied
forbidden_adjacent_scope: Battle UI and sprite work
"""


def test_code_gate_accepts_one_complete_gate() -> None:
    assert MODULE.validate_code_gate(VALID_GATE) == []


def test_code_gate_rejects_missing_and_duplicate_fields() -> None:
    text = VALID_GATE.replace("required_live_proof: explicit tab receives the request\n", "")
    text += "blocking_defect: second defect\n"
    assert MODULE.validate_code_gate(text) == [
        "duplicate_blocking_defect",
        "missing_required_live_proof",
    ]


def test_code_deliverable_rejects_prose_only(tmp_path: Path) -> None:
    assert MODULE.code_deliverable_errors(
        "Here is a plan.", tmp_path / "missing.zip", VALID_GATE
    ) == ["code_deliverable_missing"]


def test_code_deliverable_accepts_diff_or_nonempty_zip(tmp_path: Path) -> None:
    archive = tmp_path / "solution.zip"
    diff = "diff --git a/skills/webgpt/scripts/webgpt_cli.py b/skills/webgpt/scripts/webgpt_cli.py"
    assert MODULE.code_deliverable_errors(diff, archive, VALID_GATE) == []
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("skills/webgpt/scripts/webgpt_cli.py", "print('done')\n")
    assert MODULE.code_deliverable_errors("prose", archive, VALID_GATE) == []


def test_code_deliverable_rejects_scope_expansion(tmp_path: Path) -> None:
    diff = "diff --git a/skills/battle/README.md b/skills/battle/README.md"
    assert MODULE.code_deliverable_errors(diff, tmp_path / "missing.zip", VALID_GATE) == [
        "path_outside_allowed_files:skills/battle/README.md"
    ]


def test_zipped_bundle_requires_execution_gate_member(tmp_path: Path) -> None:
    archive = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("execution-gate.md", VALID_GATE)
    assert MODULE.read_code_gate_text(archive) == VALID_GATE


def test_explicit_tab_requires_exact_url() -> None:
    tabs = [{"id": "837358116", "url": "https://chatgpt.com/c/right"}]
    assert MODULE.validate_explicit_tab("837358116", "", tabs) == [
        "explicit_tab_requires_expect_url"
    ]
    assert MODULE.validate_explicit_tab(
        "837358116", "https://chatgpt.com/c/wrong", tabs
    ) == ["explicit_tab_url_mismatch"]
    assert MODULE.validate_explicit_tab(
        "837358116", "https://chatgpt.com/c/right", tabs
    ) == []


def test_explicit_tab_target_never_creates_or_remembers_tab() -> None:
    args = MODULE.submission_target_args(
        "837358116", "https://chatgpt.com/c/right", {"tab_id": "other"}
    )
    assert args == [
        "--tab-id",
        "837358116",
        "--expect-url",
        "https://chatgpt.com/c/right",
        "--no-remember",
    ]
    assert "--create-tab" not in args
