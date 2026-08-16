"""The DAG output tree grew to 2.2 GB because nothing pruned it.

`run_state.prune_runs` covers a different directory shape and would have
removed 1 of 325 entries here. These guard the pruner that covers this one --
and, more importantly, guard what it must refuse to touch.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from ask import prune_outputs

DAY = 86400


def _run(root: Path, name: str, *, age_days: float = 0.0, status: str | None = None,
         marker: str = "dag.json", extra: dict | None = None) -> Path:
    run = root / name
    run.mkdir(parents=True)
    (run / marker).write_text("{}", encoding="utf-8")
    for filename, payload in (extra or {}).items():
        (run / filename).write_text(payload, encoding="utf-8")
    if status is not None:
        (run / "execution-status.json").write_text(
            json.dumps({"status": status}), encoding="utf-8"
        )
    when = time.time() - age_days * DAY
    for path in list(run.rglob("*")) + [run]:
        import os

        os.utime(path, (when, when))
    return run


def test_an_old_finished_run_is_removable(tmp_path) -> None:
    _run(tmp_path, "old", age_days=30, status="PASS")
    decided = prune_outputs.plan(tmp_path)
    assert [Path(r["path"]).name for r in decided["removable"]] == ["old"]


def test_a_recent_run_is_kept(tmp_path) -> None:
    _run(tmp_path, "fresh", age_days=1, status="PASS")
    decided = prune_outputs.plan(tmp_path)
    assert decided["removable"] == []
    assert decided["kept"][0]["reason"] == "too_recent"


def test_a_non_terminal_run_is_pinned_regardless_of_age(tmp_path) -> None:
    """A BLOCKED run is the evidence for why it blocked."""
    _run(tmp_path, "blocked", age_days=400, status="RUNNING")
    decided = prune_outputs.plan(tmp_path)
    assert decided["removable"] == []
    assert decided["kept"][0]["reason"] == "execution_state:RUNNING"


def test_an_unreadable_status_is_not_permission_to_delete(tmp_path) -> None:
    run = _run(tmp_path, "corrupt", age_days=400, status="PASS")
    (run / "execution-status.json").write_text("{ truncated", encoding="utf-8")
    decided = prune_outputs.plan(tmp_path)
    assert decided["removable"] == []
    assert decided["kept"][0]["reason"] == "execution_state:unreadable"


def test_a_directory_that_is_not_a_run_is_never_touched(tmp_path) -> None:
    """Living under the output root does not make something Ask's to delete."""
    stray = tmp_path / "someones-notes"
    stray.mkdir()
    (stray / "important.md").write_text("keep me", encoding="utf-8")
    decided = prune_outputs.plan(tmp_path)
    assert decided["removable"] == []
    assert decided["kept"] == []


def test_a_run_with_only_a_compile_status_still_counts(tmp_path) -> None:
    _run(tmp_path, "compiled", age_days=30, marker="compile-status.json")
    assert len(prune_outputs.plan(tmp_path)["removable"]) == 1


def test_a_stale_inflight_marker_does_not_pin_a_finished_run(tmp_path) -> None:
    """1,226 of these exist; a completed submit leaves its marker behind."""
    _run(tmp_path, "done", age_days=30, status="PASS",
         extra={"webgpt_inflight.json": "{}"})
    assert len(prune_outputs.plan(tmp_path)["removable"]) == 1


def test_a_nested_run_inside_a_claimed_run_is_not_double_claimed(tmp_path) -> None:
    parent = _run(tmp_path, "parent", age_days=30, status="PASS")
    _run(parent, "node-artifacts-child", age_days=30, status="PASS")
    # Creating the child re-stamped the parent directory; age the tree again.
    import os

    when = time.time() - 30 * DAY
    for path in list(parent.rglob("*")) + [parent]:
        os.utime(path, (when, when))
    removable = prune_outputs.plan(tmp_path)["removable"]
    assert [Path(r["path"]).name for r in removable] == ["parent"]


def test_age_comes_from_the_newest_file_not_the_directory(tmp_path) -> None:
    """A directory mtime does not move when a nested artifact is written."""
    run = _run(tmp_path, "busy", age_days=30, status="PASS")
    nested = run / "node-artifacts" / "seat"
    nested.mkdir(parents=True)
    (nested / "response.md").write_text("just written", encoding="utf-8")
    assert prune_outputs.plan(tmp_path)["removable"] == []


def test_nothing_young_is_pruned_even_with_a_zero_threshold(tmp_path) -> None:
    """A run that finished minutes ago may still be being read."""
    _run(tmp_path, "just-done", age_days=0, status="PASS")
    assert prune_outputs.plan(tmp_path, older_than_days=0)["removable"] == []


def test_dry_run_deletes_nothing(tmp_path) -> None:
    run = _run(tmp_path, "old", age_days=30, status="PASS")
    receipt = prune_outputs.prune(tmp_path)
    assert receipt["removed_count"] == 1
    assert receipt["applied"] is False
    assert run.is_dir()


def test_apply_removes_and_reports_bytes(tmp_path) -> None:
    run = _run(tmp_path, "old", age_days=30, status="PASS")
    (run / "big.md").write_text("x" * 4096, encoding="utf-8")
    import os

    when = time.time() - 30 * DAY
    for path in list(run.rglob("*")) + [run]:
        os.utime(path, (when, when))
    receipt = prune_outputs.prune(tmp_path, apply=True)
    assert receipt["removed_count"] == 1
    assert receipt["freed_bytes"] >= 4096
    assert not run.exists()


def test_a_missing_root_is_reported_not_raised(tmp_path) -> None:
    decided = prune_outputs.plan(tmp_path / "nope")
    assert decided["missing_root"] is True
    assert decided["removable"] == []
