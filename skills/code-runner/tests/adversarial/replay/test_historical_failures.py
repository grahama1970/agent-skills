from __future__ import annotations

import json
from pathlib import Path

from ..helpers.assertions import (
    assert_no_residual_code_runner_worktree,
    assert_result_failed,
    assert_result_passed,
    hunk_path,
    patch_path,
    read_json,
    result_path,
)
from ..helpers.git_repo import make_minimal_python_repo, write
from ..helpers.monkeypatch_scillm import FakeScillm
from ..helpers.patch_oracle import touched_paths_from_patch_or_hunk
from ..helpers.runner import run_spec
from ..helpers.source_snapshot import assert_source_snapshot_unchanged, snapshot_source


REPLAY_ROOT = Path(__file__).resolve().parent


def _fixture(case_name: str) -> Path:
    return REPLAY_ROOT / case_name


def _load_spec(case_name: str, repo: Path, output_dir: Path) -> dict:
    spec = json.loads((_fixture(case_name) / "spec.json").read_text())
    spec["cwd"] = str(repo)
    spec["output_dir"] = str(output_dir)
    return spec


def _load_expected(case_name: str) -> dict:
    return json.loads((_fixture(case_name) / "expected_result_subset.json").read_text())


def _install_transcript(case_name: str, monkeypatch) -> FakeScillm:
    messages: list[dict] = []
    for raw_line in (_fixture(case_name) / "fake_scillm_transcript.jsonl").read_text().splitlines():
        if not raw_line.strip():
            continue
        item = json.loads(raw_line)
        if "error" in item:
            return FakeScillm(error=RuntimeError(item["error"])).install(monkeypatch)
        messages.append(item)
    return FakeScillm(messages).install(monkeypatch)


def _assert_expected_subset(result: dict, expected: dict) -> None:
    for key, expected_value in expected.items():
        assert result.get(key) == expected_value, f"{key}: expected {expected_value!r}, got {result.get(key)!r}"


def _assert_replay_diagnostics(output_dir: Path, task_id: str) -> None:
    required = [
        output_dir / f"{task_id}.request.json",
        output_dir / f"{task_id}.status.json",
        output_dir / f"{task_id}.events.jsonl",
        output_dir / f"{task_id}.result.json",
        output_dir / f"{task_id}.verifier.log",
    ]
    for path in required:
        assert path.exists(), f"missing replay diagnostic artifact: {path}"
    status = read_json(output_dir / f"{task_id}.status.json")
    assert status["task_id"] == task_id


def _run_replay(case_name: str, tmp_path: Path, monkeypatch, *, dirty_allowlist: bool = False) -> tuple[Path, Path, dict]:
    repo = make_minimal_python_repo(tmp_path)
    if dirty_allowlist:
        write(repo, "src/app.py", "def add_one(x):\n    return 'USER DIRTY WORK'\n")
    output_dir = tmp_path / "out" / case_name
    before = snapshot_source(repo)

    _install_transcript(case_name, monkeypatch)
    result = run_spec(_load_spec(case_name, repo, output_dir))

    _assert_expected_subset(result, _load_expected(case_name))
    _assert_replay_diagnostics(output_dir, case_name)
    assert_source_snapshot_unchanged(repo, before)
    assert_no_residual_code_runner_worktree(repo, case_name)
    assert result_path(output_dir, case_name).exists()
    return repo, output_dir, result


def test_replay_dirty_allowlist_fail_closed(tmp_path: Path, monkeypatch) -> None:
    repo, _output_dir, result = _run_replay("dirty_allowlist_fail_closed", tmp_path, monkeypatch, dirty_allowlist=True)

    assert_result_failed(result)
    assert result["source_patch_applied"] is False
    assert result["source_rollback_applied"] is False
    assert (repo / "src/app.py").read_text() == "def add_one(x):\n    return 'USER DIRTY WORK'\n"


def test_replay_dod_ran_from_source(tmp_path: Path, monkeypatch) -> None:
    repo, output_dir, result = _run_replay("dod_ran_from_source", tmp_path, monkeypatch)

    assert_result_passed(result)
    assert (repo / "src/app.py").read_text() == "def add_one(x):\n    return x\n"
    assert touched_paths_from_patch_or_hunk(hunk_path(output_dir, "dod_ran_from_source")) == {"src/app.py"}
    assert patch_path(output_dir, "dod_ran_from_source").exists()


def test_replay_restore_wrong_cwd(tmp_path: Path, monkeypatch) -> None:
    repo, output_dir, result = _run_replay("restore_wrong_cwd", tmp_path, monkeypatch)

    assert_result_failed(result)
    assert not (repo / "docs/outside.md").exists()
    assert touched_paths_from_patch_or_hunk(hunk_path(output_dir, "restore_wrong_cwd")) == set()


def test_replay_patch_numstat_wrong_cwd(tmp_path: Path, monkeypatch) -> None:
    repo, output_dir, result = _run_replay("patch_numstat_wrong_cwd", tmp_path, monkeypatch)

    assert_result_passed(result)
    assert (repo / "src/app.py").read_text() == "def add_one(x):\n    return x\n"
    assert touched_paths_from_patch_or_hunk(hunk_path(output_dir, "patch_numstat_wrong_cwd")) == {"src/app.py"}


def test_replay_scillm_http_400(tmp_path: Path, monkeypatch) -> None:
    repo, _output_dir, result = _run_replay("scillm_http_400", tmp_path, monkeypatch)

    assert_result_failed(result)
    assert "scillm HTTP 400" in result["error"]
    assert (repo / "src/app.py").read_text() == "def add_one(x):\n    return x\n"


def test_replay_false_green_monolith(tmp_path: Path, monkeypatch) -> None:
    repo, output_dir, result = _run_replay("false_green_monolith", tmp_path, monkeypatch)

    assert_result_failed(result)
    assert result["rounds"] == 1
    assert touched_paths_from_patch_or_hunk(hunk_path(output_dir, "false_green_monolith")) == set()
    assert (repo / "src/app.py").read_text() == "def add_one(x):\n    return x\n"
