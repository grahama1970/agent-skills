"""Regression tests for dependency-edge canonicalization."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

MODULE_PATH = Path(__file__).resolve().parents[1] / "ingest_code.py"
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
        "dry_run": True,
        "scope": "code",
        "batch_size": 50,
    }
    options.update(overrides)
    return options


def _write(repo: Path, relative_path: str, content: str = "") -> Path:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _edge(
    from_file: str,
    to_file: str,
    module: str,
    names: list[str] | None = None,
    edge_type: str = "depends_on",
) -> dict:
    return {
        "from_file": from_file,
        "to_file": to_file,
        "edge_type": edge_type,
        "module": module,
        "names": names or [],
    }


def _summary_from_stdout(stdout: str) -> dict:
    lines = stdout.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == "{":
            candidate = "\n".join(lines[index:])
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
    raise AssertionError(f"summary JSON not found in output:\n{stdout}")


def _install_scan_mocks(monkeypatch, tmp_path: Path, files: list[Path]) -> None:
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "_collect_files_or_exit", lambda *args, **kwargs: files)
    monkeypatch.setattr(ingest_code, "extract_knowledge", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", lambda path: [])
    monkeypatch.setattr(ingest_code, "_learn_http", lambda *args, **kwargs: True)


def test_exact_duplicate_edges_collapse_to_one() -> None:
    edges = [
        _edge("/repo/app.py", "/repo/dep.py", "dep", ["run"]),
        _edge("/repo/app.py", "/repo/dep.py", "dep", ["run"]),
    ]

    assert ingest_code._canonicalize_dependency_edges(edges) == [
        _edge("/repo/app.py", "/repo/dep.py", "dep", ["run"]),
    ]


def test_repeated_import_statement_produces_one_edge(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    app = _write(repo, "app.py", "import dep\nimport dep\n")
    dep = _write(repo, "dep.py")

    edges = ingest_code.extract_edges([app, dep], repo)

    assert edges == [_edge(str(app.resolve()), str(dep.resolve()), "dep")]


def test_imported_names_merge_deterministically(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    app = _write(repo, "app.py", "from dep import run\nfrom dep import load\nfrom dep import run\n")
    dep = _write(repo, "dep.py")

    edges = ingest_code.extract_edges([app, dep], repo)

    assert edges == [_edge(str(app.resolve()), str(dep.resolve()), "dep", ["load", "run"])]


def test_edge_canonicalization_is_input_order_independent() -> None:
    edges = [
        _edge("/repo/b.py", "/repo/c.py", "c", ["C"]),
        _edge("/repo/a.py", "/repo/b.py", "b", ["B2"]),
        _edge("/repo/a.py", "/repo/b.py", "b", ["B1"]),
    ]

    assert ingest_code._canonicalize_dependency_edges(edges) == ingest_code._canonicalize_dependency_edges(
        list(reversed(edges))
    )


def test_duplicate_file_manifest_entry_does_not_duplicate_edges(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    app = _write(repo, "app.py", "import dep\n")
    dep = _write(repo, "dep.py")

    edges = ingest_code.extract_edges([app, app, dep], repo)

    assert edges == [_edge(str(app.resolve()), str(dep.resolve()), "dep")]


def test_different_modules_to_same_target_remain_distinct() -> None:
    edges = ingest_code._canonicalize_dependency_edges([
        _edge("/repo/app.py", "/repo/dep.py", "dep", ["run"]),
        _edge("/repo/app.py", "/repo/dep.py", "pkg.dep", ["run"]),
    ])

    assert edges == [
        _edge("/repo/app.py", "/repo/dep.py", "dep", ["run"]),
        _edge("/repo/app.py", "/repo/dep.py", "pkg.dep", ["run"]),
    ]


def test_dry_run_previews_canonical_edge_once(capsys) -> None:
    stored = ingest_code.store_edges(
        [
            _edge("/repo/app.py", "/repo/dep.py", "dep", ["run"]),
            _edge("/repo/app.py", "/repo/dep.py", "dep", ["run"]),
        ],
        dry_run=True,
    )

    stdout = capsys.readouterr().out
    assert stored == 0
    assert stdout.count("[EDGE]") == 1
    assert "imports run" in stdout


def test_live_store_submits_only_canonical_edges(monkeypatch) -> None:
    calls = []

    class FakeClient:
        def add_edges(self, batch):
            calls.append(batch)
            return SimpleNamespace(stored=len(batch), attempted=len(batch), errors=[])

    monkeypatch.setattr(ingest_code, "CodeMemoryClient", lambda: FakeClient())

    stored = ingest_code.store_edges(
        [
            _edge("/repo/app.py", "/repo/dep.py", "dep", ["run"]),
            _edge("/repo/app.py", "/repo/dep.py", "dep", ["load", "run"]),
        ],
        dry_run=False,
    )

    assert stored == 1
    assert calls == [[{
        "from_title": "What does app.py do?",
        "to_title": "What does dep.py do?",
        "type": "depends_on",
        "from_scope": "",
        "to_scope": "",
        "weight": 0.8,
        "rationale": "import: dep",
    }]]


def test_scan_summary_uses_canonical_edge_count(monkeypatch, tmp_path: Path, capsys) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    app = _write(repo, "app.py", "import dep\nimport dep\n")
    dep = _write(repo, "dep.py")
    _install_scan_mocks(monkeypatch, tmp_path, [app, dep])

    ingest_code.scan(**_scan_args(repo, dry_run=True))

    summary = _summary_from_stdout(capsys.readouterr().out)
    assert summary["edges_found"] == 1
    assert summary["edges_stored"] == 0


def test_live_marker_does_not_inflate_edges_stored(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    app = _write(repo, "app.py", "import dep\nimport dep\n")
    dep = _write(repo, "dep.py")
    _install_scan_mocks(monkeypatch, tmp_path, [app, dep])

    class FakeClient:
        def add_edges(self, batch):
            return SimpleNamespace(stored=len(batch), attempted=len(batch), errors=[])

    monkeypatch.setattr(ingest_code, "CodeMemoryClient", lambda: FakeClient())

    ingest_code.scan(**_scan_args(repo, dry_run=False))

    status = ingest_code.build_marker_status(repo)
    assert status["status"] == "fresh"
    assert status["edges_stored"] == 1
