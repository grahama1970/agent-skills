"""Regression tests for truthful edge dry-run accounting."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

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
        "dry_run": True,
        "scope": "code",
        "batch_size": 50,
    }
    options.update(overrides)
    return options


def _edge(
    from_file: str,
    to_file: str,
    module: str,
    names: list[str] | None = None,
) -> dict:
    return {
        "from_file": from_file,
        "to_file": to_file,
        "edge_type": "depends_on",
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


def _common_scan_mocks(monkeypatch, tmp_path: Path, files: list[Path]) -> None:
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: None)
    monkeypatch.setattr(ingest_code, "_collect_files_or_exit", lambda *args, **kwargs: files)
    monkeypatch.setattr(ingest_code, "extract_knowledge", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", lambda path: [])


def test_store_edges_dry_run_previews_but_returns_zero(capsys) -> None:
    edges = [
        _edge("/repo/b.py", "/repo/c.py", "c", ["C"]),
        _edge("/repo/a.py", "/repo/b.py", "b", ["B"]),
    ]

    stored = ingest_code.store_edges(edges, dry_run=True)

    stdout = capsys.readouterr().out
    assert "  [EDGE] a.py → b.py (imports B)" in stdout
    assert "  [EDGE] b.py → c.py (imports C)" in stdout
    assert stored == 0


def test_store_edges_dry_run_never_constructs_memory_client(monkeypatch) -> None:
    monkeypatch.setattr(
        ingest_code,
        "CodeMemoryClient",
        lambda: (_ for _ in ()).throw(AssertionError("dry-run must not open memory")),
    )

    stored = ingest_code.store_edges([_edge("/repo/a.py", "/repo/b.py", "b")], dry_run=True)

    assert stored == 0


def test_edge_dry_run_preview_order_is_deterministic(capsys) -> None:
    edges = [
        _edge("/repo/b.py", "/repo/c.py", "c", ["C"]),
        _edge("/repo/a.py", "/repo/b.py", "b", ["B"]),
    ]

    ingest_code.store_edges(edges, dry_run=True)
    first = capsys.readouterr().out
    ingest_code.store_edges(list(reversed(edges)), dry_run=True)
    second = capsys.readouterr().out

    assert first == second


def test_scan_dry_run_summary_reports_found_not_stored(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")
    marker_calls = []
    discoverability_calls = []
    edges = [
        _edge(str(source), str(repo / "dep.py"), "dep", ["Dep"]),
        _edge(str(repo / "dep.py"), str(source), "app", ["app"]),
    ]
    _common_scan_mocks(monkeypatch, tmp_path, [source])
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: edges)
    monkeypatch.setattr(
        ingest_code,
        "CodeMemoryClient",
        lambda: (_ for _ in ()).throw(AssertionError("dry-run must not open memory")),
    )
    monkeypatch.setattr(ingest_code, "_write_required_ingest_marker", lambda *args, **kwargs: marker_calls.append(args))
    monkeypatch.setattr(ingest_code, "_learn_http", lambda *args, **kwargs: discoverability_calls.append(args))

    ingest_code.scan(**_scan_args(repo))

    summary = _summary_from_stdout(capsys.readouterr().out)
    assert summary["edges_found"] == 2
    assert summary["edges_stored"] == 0
    assert summary["dry_run"] is True
    assert marker_calls == []
    assert discoverability_calls == []
    assert not (repo / ".ingest-code.json").exists()


def test_scan_dry_run_prints_preview_summary(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")
    _common_scan_mocks(monkeypatch, tmp_path, [source])
    monkeypatch.setattr(
        ingest_code,
        "extract_edges",
        lambda *args, **kwargs: [
            _edge(str(source), str(repo / "dep.py"), "dep", ["Dep"]),
            _edge(str(repo / "dep.py"), str(source), "app", ["app"]),
        ],
    )

    ingest_code.scan(**_scan_args(repo))

    stdout = capsys.readouterr().out
    assert "Edges: 2 previewed, 0 stored" in stdout
    assert "Edges: 2 stored" not in stdout


def test_live_store_edges_behavior_is_unchanged(monkeypatch) -> None:
    calls = []

    class FakeClient:
        def add_edges(self, batch):
            calls.append(batch)
            return SimpleNamespace(stored=2, attempted=2, errors=[])

    monkeypatch.setattr(ingest_code, "CodeMemoryClient", lambda: FakeClient())
    edges = [
        _edge("/repo/a.py", "/repo/b.py", "pkg.b", ["B"]),
        _edge("/repo/a.py", "/repo/c.py", "pkg.c", ["C"]),
    ]

    stored = ingest_code.store_edges(edges, dry_run=False)

    assert stored == 2
    assert calls == [[
        {
            "from_title": "What does a.py do?",
            "to_title": "What does b.py do?",
            "type": "depends_on",
            "from_scope": "",
            "to_scope": "",
            "weight": 0.8,
            "rationale": "import: pkg.b",
        },
        {
            "from_title": "What does a.py do?",
            "to_title": "What does c.py do?",
            "type": "depends_on",
            "from_scope": "",
            "to_scope": "",
            "weight": 0.8,
            "rationale": "import: pkg.c",
        },
    ]]


def test_zero_edge_dry_run_reports_zero_counts(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")
    _common_scan_mocks(monkeypatch, tmp_path, [source])
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: [])

    ingest_code.scan(**_scan_args(repo))

    summary = _summary_from_stdout(capsys.readouterr().out)
    assert summary["edges_found"] == 0
    assert summary["edges_stored"] == 0


def test_skill_docs_define_edge_preview_accounting() -> None:
    text = SKILL_PATH.read_text()

    assert "[EDGE]" in text
    assert "edges_found" in text
    assert "edges_stored" in text
    assert "memory edge endpoint is not called" in text
