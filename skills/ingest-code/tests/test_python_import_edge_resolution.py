"""Regression tests for ambiguity-safe Python import edge resolution."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

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


def _edge_pairs(edges: list[dict]) -> list[tuple[str, str, str]]:
    return sorted(
        (edge["from_file"], edge["to_file"], edge["module"])
        for edge in edges
    )


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


def test_module_index_retains_all_candidates_for_short_alias(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    src_util = _write(repo, "src/pkg/util.py")
    tests_util = _write(repo, "tests/pkg/util.py")

    index = ingest_code.build_module_index([src_util, tests_util], repo)

    assert index["pkg.util"] == (src_util.resolve(), tests_util.resolve())


def test_ambiguous_short_import_emits_no_edge(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    caller = _write(repo, "app.py", "import pkg.util\n")
    src_util = _write(repo, "src/pkg/util.py")
    tests_util = _write(repo, "tests/pkg/util.py")

    edges = ingest_code.extract_edges([caller, src_util, tests_util], repo)

    assert edges == []


def test_unique_full_import_resolves_despite_short_alias_collision(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    caller = _write(repo, "app.py", "import src.pkg.util\n")
    src_util = _write(repo, "src/pkg/util.py")
    tests_util = _write(repo, "tests/pkg/util.py")

    edges = ingest_code.extract_edges([caller, src_util, tests_util], repo)

    assert edges == [
        {
            "from_file": str(caller),
            "to_file": str(src_util.resolve()),
            "edge_type": "depends_on",
            "module": "src.pkg.util",
            "names": [],
        }
    ]


def test_unique_short_alias_still_emits_edge(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    caller = _write(repo, "app.py", "import pkg.util\n")
    src_util = _write(repo, "src/pkg/util.py")

    edges = ingest_code.extract_edges([caller, src_util], repo)

    assert edges == [
        {
            "from_file": str(caller),
            "to_file": str(src_util.resolve()),
            "edge_type": "depends_on",
            "module": "pkg.util",
            "names": [],
        }
    ]


def test_package_init_alias_ambiguity_is_suppressed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    caller = _write(repo, "app.py", "import pkg\n")
    src_pkg = _write(repo, "src/pkg/__init__.py")
    tests_pkg = _write(repo, "tests/pkg/__init__.py")

    index = ingest_code.build_module_index([src_pkg, tests_pkg], repo)
    edges = ingest_code.extract_edges([caller, src_pkg, tests_pkg], repo)

    assert index["pkg"] == (src_pkg.resolve(), tests_pkg.resolve())
    assert edges == []


def test_module_resolution_is_independent_of_file_order(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    caller = _write(repo, "app.py", "import src.pkg.util\n")
    src_util = _write(repo, "src/pkg/util.py")
    tests_util = _write(repo, "tests/pkg/util.py")
    files = [caller, src_util, tests_util]

    forward_index = ingest_code.build_module_index(files, repo)
    reverse_index = ingest_code.build_module_index(list(reversed(files)), repo)
    forward_edges = ingest_code.extract_edges(files, repo)
    reverse_edges = ingest_code.extract_edges(list(reversed(files)), repo)

    assert forward_index == reverse_index
    assert _edge_pairs(forward_edges) == _edge_pairs(reverse_edges)


def test_duplicate_input_path_does_not_create_ambiguity(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    src_util = _write(repo, "src/pkg/util.py")

    index = ingest_code.build_module_index([src_util, src_util], repo)

    assert index["pkg.util"] == (src_util.resolve(),)
    assert ingest_code._resolve_unique_python_module(index, "pkg.util") == src_util.resolve()


def test_ambiguous_import_does_not_reach_edge_storage(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    caller = _write(repo, "app.py", "import pkg.util\n")
    src_util = _write(repo, "src/pkg/util.py")
    tests_util = _write(repo, "tests/pkg/util.py")
    files = [caller, src_util, tests_util]
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: None)
    monkeypatch.setattr(ingest_code, "_collect_files_or_exit", lambda *args, **kwargs: files)
    monkeypatch.setattr(ingest_code, "extract_knowledge", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", lambda path: [])
    monkeypatch.setattr(
        ingest_code,
        "CodeMemoryClient",
        lambda: (_ for _ in ()).throw(AssertionError("ambiguous dry-run edge should not open memory")),
    )

    ingest_code.scan(**_scan_args(repo))

    stdout = capsys.readouterr().out
    summary = _summary_from_stdout(stdout)
    assert "[EDGE]" not in stdout
    assert summary["edges_found"] == 0
    assert summary["edges_stored"] == 0
