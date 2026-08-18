"""Tests for the Herdr file-viewer open path.

Split out of test_monitor_herdr.py alongside scripts/file_viewer.py so both stay
under the 800-line repo limit. `monitor` here is the file_viewer module, so the
existing assertions read unchanged.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "file_viewer.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("file_viewer", SCRIPT)
assert SPEC and SPEC.loader
monitor = importlib.util.module_from_spec(SPEC)
sys.modules["file_viewer"] = monitor
SPEC.loader.exec_module(monitor)


def test_split_line_reference_preserves_range() -> None:
    assert monitor.split_line_reference("src/app.py:10-20") == {
        "path": "src/app.py",
        "line_suffix": ":10-20",
    }
    assert monitor.split_line_reference("src/app.py:not-a-line") == {
        "path": "src/app.py:not-a-line",
        "line_suffix": "",
    }
def test_file_viewer_exact_absolute_target_builds_open_ref(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    target = repo / "src" / "file.py"
    target.parent.mkdir(parents=True)
    target.write_text("print('ok')\n", encoding="utf-8")

    plan = monitor.build_file_viewer_open_plan(
        target=f"{target}:12",
        query=None,
        root=repo,
    )

    assert plan["mode"] == "exact"
    assert plan["root"] == str(repo.resolve())
    assert plan["resolved_path"] == str(target.resolve())
    assert plan["open_ref"] == "src/file.py:12"
def test_file_viewer_fuzzy_query_resolves_best_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "prompt_builder.py").write_text("# prompt\n", encoding="utf-8")
    (repo / "scripts" / "monitor_herdr.py").write_text("# monitor\n", encoding="utf-8")

    plan = monitor.build_file_viewer_open_plan(
        target=None,
        query="prompt builder",
        root=repo,
    )

    assert plan["mode"] == "fuzzy"
    assert plan["open_ref"] == "scripts/prompt_builder.py"
    assert plan["fuzzy_matches"][0]["path"] == "scripts/prompt_builder.py"
def test_file_viewer_fuzzy_tied_top_match_fails_closed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "a").mkdir(parents=True)
    (repo / "b").mkdir(parents=True)
    (repo / "a" / "target.py").write_text("# a\n", encoding="utf-8")
    (repo / "b" / "target.py").write_text("# b\n", encoding="utf-8")

    try:
        monitor.build_file_viewer_open_plan(target=None, query="target.py", root=repo)
    except ValueError as exc:
        assert "ambiguous fuzzy query" in str(exc)
    else:
        raise AssertionError("ambiguous fuzzy query should fail closed")
def test_file_viewer_rejects_out_of_root_exact_target(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "outside.py"
    repo.mkdir()
    outside.write_text("# outside\n", encoding="utf-8")

    try:
        monitor.build_file_viewer_open_plan(target=str(outside), query=None, root=repo)
    except ValueError as exc:
        assert "not under" in str(exc)
    else:
        raise AssertionError("out-of-root target should fail closed")
def test_pane_id_from_cli_result_extracts_split_pane() -> None:
    stdout = '{"result":{"pane":{"pane_id":"w11:pX"}}}'

    assert monitor.pane_id_from_cli_result(stdout) == "w11:pX"
def test_file_viewer_visible_requires_rendered_frame_not_shell_command() -> None:
    shell_text = "herdr-file-viewer --open skills/monitor-herdr/SKILL.md\n"
    rendered = "┌SKILL.md────┐\n│ Opened skills/monitor-herdr/SKILL.md │\n└main────────┘"

    assert monitor.file_viewer_visible(shell_text) is False
    assert monitor.file_viewer_visible(rendered) is True
    assert monitor.open_target_visible(rendered, "skills/monitor-herdr/SKILL.md", "/repo/skills/monitor-herdr/SKILL.md")
