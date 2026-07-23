"""Regression tests for INGEST_WORKERS validation."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "ingest_code.py"
SKILL_PATH = MODULE_PATH.parent / "SKILL.md"
sys.path.insert(0, str(MODULE_PATH.parent))
spec = importlib.util.spec_from_file_location("ingest_code", MODULE_PATH)
assert spec and spec.loader
ingest_code = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ingest_code
spec.loader.exec_module(ingest_code)


def _scan_args(repo: Path, **overrides) -> dict:
    options = {
        "path": repo,
        "glob": [],
        "cwe_only": False,
        "validate": False,
        "treesitter": False,
        "code_index": True,
        "dry_run": False,
        "scope": "code",
        "batch_size": 50,
    }
    options.update(overrides)
    return options


def _install_minimal_scan_mocks(
    monkeypatch,
    tmp_path: Path,
    repo: Path,
    source: Path,
    *,
    items: list[dict] | None = None,
) -> list[tuple]:
    discoverability_calls: list[tuple] = []
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "_collect_files_or_exit", lambda *args, **kwargs: [source])
    monkeypatch.setattr(
        ingest_code,
        "extract_knowledge",
        lambda *args, **kwargs: items if items is not None else [],
    )
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        ingest_code,
        "_write_required_ingest_marker",
        lambda *args, **kwargs: repo / ".ingest-code.json",
    )
    monkeypatch.setattr(
        ingest_code,
        "_learn_http",
        lambda *args, **kwargs: discoverability_calls.append(args) or True,
    )
    return discoverability_calls


class _FakeFuture:
    def __init__(self, value: bool) -> None:
        self._value = value

    def result(self) -> bool:
        return self._value


class _FakeExecutor:
    captured_max_workers: list[int] = []

    def __init__(self, max_workers: int) -> None:
        self.captured_max_workers.append(max_workers)

    def __enter__(self) -> "_FakeExecutor":
        return self

    def __exit__(self, *args) -> None:
        return None

    def submit(self, fn, item: dict) -> _FakeFuture:
        return _FakeFuture(fn(item))


def _install_fake_executor(monkeypatch) -> None:
    _FakeExecutor.captured_max_workers = []
    monkeypatch.setattr(ingest_code, "ThreadPoolExecutor", _FakeExecutor)
    monkeypatch.setattr(ingest_code, "as_completed", lambda futures: list(futures))


def test_resolve_ingest_workers_uses_default_for_missing_or_blank(monkeypatch) -> None:
    monkeypatch.delenv("INGEST_WORKERS", raising=False)

    assert ingest_code._resolve_ingest_workers() == 8
    assert ingest_code._resolve_ingest_workers("") == 8
    assert ingest_code._resolve_ingest_workers("   ") == 8


def test_resolve_ingest_workers_accepts_positive_values() -> None:
    assert ingest_code._resolve_ingest_workers("1") == 1
    assert ingest_code._resolve_ingest_workers("16") == 16


@pytest.mark.parametrize("raw_value", ["zero", "1.5", "0", "-1", "-100"])
def test_resolve_ingest_workers_rejects_invalid_values(raw_value: str) -> None:
    with pytest.raises(ingest_code.IngestWorkersError):
        ingest_code._resolve_ingest_workers(raw_value)


def test_invalid_workers_exit_before_external_work(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    calls: list[str] = []
    monkeypatch.setenv("INGEST_WORKERS", "invalid")
    monkeypatch.setattr(ingest_code, "_resolve_codebase_directory", lambda *args, **kwargs: calls.append("resolve"))
    monkeypatch.setattr(ingest_code, "_preflight_scan_config", lambda *args, **kwargs: calls.append("preflight"))
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: calls.append("taxonomy"))
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: calls.append("memory"))
    monkeypatch.setattr(ingest_code, "_collect_files_or_exit", lambda *args, **kwargs: calls.append("collect"))
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: calls.append("learn"))
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", lambda *args, **kwargs: calls.append("treesitter"))
    monkeypatch.setattr(ingest_code, "_write_required_ingest_marker", lambda *args, **kwargs: calls.append("marker"))

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(tmp_path / "repo"))

    assert exc_info.value.code == 2
    assert calls == []
    stderr = capsys.readouterr().err.strip().splitlines()
    error = json.loads(stderr[-1])
    assert error["error"] == "Invalid INGEST_WORKERS value"
    assert error["environment"] == "INGEST_WORKERS"
    assert error["value"] == "invalid"


def test_valid_workers_value_reaches_executor(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")
    learn_calls: list[tuple] = []
    item = {"problem": "p", "solution": "s", "tags": ["t"]}
    monkeypatch.setenv("INGEST_WORKERS", "3")
    _install_minimal_scan_mocks(monkeypatch, tmp_path, repo, source, items=[item])
    _install_fake_executor(monkeypatch)
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: learn_calls.append(args) or True)

    ingest_code.scan(**_scan_args(repo))

    assert _FakeExecutor.captured_max_workers == [3]
    assert len(learn_calls) == 1


def test_workers_override_is_resolved_once_per_scan(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")
    items = [
        {"problem": f"p{index}", "solution": "s", "tags": ["t"]}
        for index in range(3)
    ]
    resolver_calls: list[None] = []
    _install_minimal_scan_mocks(monkeypatch, tmp_path, repo, source, items=items)
    _install_fake_executor(monkeypatch)
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: True)

    def fake_resolve() -> int:
        resolver_calls.append(None)
        return 2

    monkeypatch.setattr(ingest_code, "_resolve_ingest_workers", fake_resolve)

    ingest_code.scan(**_scan_args(repo))

    assert resolver_calls == [None]
    assert _FakeExecutor.captured_max_workers == [2]


def test_dry_run_ignores_invalid_workers_override(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")
    monkeypatch.setenv("INGEST_WORKERS", "invalid")
    _install_minimal_scan_mocks(
        monkeypatch,
        tmp_path,
        repo,
        source,
        items=[{"problem": "p", "solution": "s", "tags": ["t"]}],
    )
    monkeypatch.setattr(
        ingest_code,
        "_resolve_ingest_workers",
        lambda *args, **kwargs: pytest.fail("dry-run should not resolve INGEST_WORKERS"),
    )
    monkeypatch.setattr(
        ingest_code,
        "ThreadPoolExecutor",
        lambda *args, **kwargs: pytest.fail("dry-run should not create a write pool"),
    )
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: pytest.fail("dry-run should not write lessons"))

    ingest_code.scan(**_scan_args(repo, dry_run=True))


def test_cwe_only_ignores_invalid_workers_override(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")
    monkeypatch.setenv("INGEST_WORKERS", "invalid")
    _install_minimal_scan_mocks(monkeypatch, tmp_path, repo, source)
    monkeypatch.setattr(
        ingest_code,
        "_resolve_ingest_workers",
        lambda *args, **kwargs: pytest.fail("CWE-only should not resolve INGEST_WORKERS"),
    )
    monkeypatch.setattr(
        ingest_code,
        "ThreadPoolExecutor",
        lambda *args, **kwargs: pytest.fail("CWE-only should not create a knowledge write pool"),
    )
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: pytest.fail("CWE-only should not write lessons"))

    ingest_code.scan(**_scan_args(repo, cwe_only=True))


def test_skill_docs_describe_ingest_workers() -> None:
    text = SKILL_PATH.read_text()

    assert "INGEST_WORKERS" in text
    assert "default to 8" in text
    assert "status 2" in text
    assert "dry-run" in text
    assert "CWE-only" in text
