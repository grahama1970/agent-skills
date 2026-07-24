"""Regression tests for repository-relative Python module lesson identities."""

from __future__ import annotations

import importlib.util
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


def _write(repo: Path, relative_path: str, content: str = "") -> Path:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _items(source: Path, repo: Path | None = None) -> list[dict]:
    return ingest_code.extract_python_knowledge(
        source,
        source.read_text(),
        codebase_root=repo,
    )


def _module_item(source: Path, repo: Path | None = None) -> dict:
    module_items = [
        item
        for item in _items(source, repo)
        if item.get("tags") == ["codebase", "module", source.stem]
    ]
    assert len(module_items) == 1
    return module_items[0]


def _edge(from_file: Path, to_file: Path, module: str, names: list[str] | None = None) -> dict:
    return {
        "from_file": str(from_file),
        "to_file": str(to_file),
        "edge_type": "depends_on",
        "module": module,
        "names": names or [],
    }


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


def _install_scan_mocks(monkeypatch, tmp_path: Path, files: list[Path]) -> None:
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "_collect_files_or_exit", lambda *args, **kwargs: files)
    monkeypatch.setattr(ingest_code, "extract_knowledge", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "scan_file_cwe", lambda *args, **kwargs: {"cwe_mappings": []})
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "_learn_http", lambda *args, **kwargs: True)
    monkeypatch.setattr(ingest_code, "_write_required_ingest_marker", lambda *args, **kwargs: tmp_path / ".ingest-code.json")


def test_repository_root_qualifies_module_question_and_solution(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(repo, "pkg/app.py", "VALUE = 1\n")

    item = _module_item(source, repo)

    assert item["problem"] == "What does pkg/app.py do?"
    assert item["solution"].splitlines()[0] == "Module: pkg/app.py"


def test_duplicate_basenames_have_distinct_module_questions(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    api = _write(repo, "api/app.py", "VALUE = 1\n")
    worker = _write(repo, "worker/app.py", "VALUE = 2\n")

    assert _module_item(api, repo)["problem"] == "What does api/app.py do?"
    assert _module_item(worker, repo)["problem"] == "What does worker/app.py do?"


def test_import_only_module_uses_repository_relative_identity(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(repo, "pkg/config.py", "import os\n")

    item = _module_item(source, repo)

    assert item["problem"] == "What does pkg/config.py do?"
    assert item["solution"] == (
        "Module: pkg/config.py\n\nNo module docstring or named declarations."
    )


def test_store_edges_uses_matching_relative_endpoint_titles(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    app = _write(repo, "api/app.py")
    dep = _write(repo, "lib/dep.py")
    calls = []

    class FakeClient:
        def add_edges(self, batch):
            calls.append(batch)
            return SimpleNamespace(stored=len(batch), attempted=len(batch), errors=[])

    monkeypatch.setattr(ingest_code, "CodeMemoryClient", lambda: FakeClient())

    stored = ingest_code.store_edges(
        [_edge(app, dep, "lib.dep")],
        dry_run=False,
        codebase_root=repo,
    )

    assert stored == 1
    assert calls == [[{
        "from_title": "What does api/app.py do?",
        "to_title": "What does lib/dep.py do?",
        "type": "depends_on",
        "from_scope": "",
        "to_scope": "",
        "weight": 0.8,
        "rationale": "import: lib.dep",
    }]]


def test_edge_preview_disambiguates_duplicate_basenames(tmp_path: Path, capsys) -> None:
    repo = tmp_path / "repo"
    source = _write(repo, "api/app.py")
    target = _write(repo, "worker/app.py")

    ingest_code.store_edges(
        [_edge(source, target, "worker.app", ["run"])],
        dry_run=True,
        codebase_root=repo,
    )

    assert "  [EDGE] api/app.py \u2192 worker/app.py (imports run)" in capsys.readouterr().out


def test_scan_passes_root_to_store_edges(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = _write(repo, "app.py", "import dep\n")
    calls: list[Path | None] = []

    def fake_store_edges(edges, scope="code", dry_run=False, monitor=None, codebase_root=None):
        calls.append(codebase_root)
        return 0

    _install_scan_mocks(monkeypatch, tmp_path, [source])
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: [_edge(source, repo / "dep.py", "dep")])
    monkeypatch.setattr(ingest_code, "store_edges", fake_store_edges)

    ingest_code.scan(**_scan_args(repo))

    assert calls == [repo.resolve()]


def test_no_root_preserves_basename_compatibility(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(repo, "pkg/app.py", "VALUE = 1\n")

    item = _module_item(source)

    assert item["problem"] == "What does app.py do?"
    assert item["solution"].splitlines()[0] == "Module: app.py"


def test_module_identity_is_range_free(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(repo, "pkg/app.py", "def run():\n    return 1\n")

    item = _module_item(source, repo)

    assert item["problem"] == "What does pkg/app.py do?"
    assert "pkg/app.py:" not in item["problem"]
    assert item["solution"].splitlines()[0] == "Module: pkg/app.py"


def test_skill_docs_describe_repository_relative_module_identities() -> None:
    text = SKILL_PATH.read_text()

    assert "Python module lesson identities are repository-relative" in text
    assert "range-free" in text
    assert "edge endpoint titles use the same module identity" in text
