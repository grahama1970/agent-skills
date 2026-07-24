"""Regression tests for repository-relative Python functional source locators."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "ingest_code.py"
SKILL_PATH = MODULE_PATH.parent / "SKILL.md"
sys.path.insert(0, str(MODULE_PATH.parent))
spec = importlib.util.spec_from_file_location("ingest_code", MODULE_PATH)
assert spec and spec.loader
ingest_code = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ingest_code
spec.loader.exec_module(ingest_code)


def _write(repo: Path, relative_path: str, content: str) -> Path:
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


def _problems(items: list[dict]) -> set[str]:
    return {str(item.get("problem", "")) for item in items}


def _item_by_problem(items: list[dict], problem: str) -> dict:
    for item in items:
        if item.get("problem") == problem:
            return item
    raise AssertionError(f"item not found: {problem}")


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


def _rescan_args(repos: list[Path], **overrides) -> dict:
    options = {
        "since": None,
        "validate": False,
        "treesitter": False,
        "code_index": True,
        "verify_embeddings": False,
        "scope": "code",
        "codebase": [str(repo) for repo in repos],
    }
    options.update(overrides)
    return options


def _install_command_mocks(monkeypatch, tmp_path: Path, source: Path) -> None:
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "_collect_files_or_exit", lambda *args, **kwargs: [source])
    monkeypatch.setattr(ingest_code, "scan_file_cwe", lambda *args, **kwargs: {"cwe_mappings": []})
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: True)
    monkeypatch.setattr(ingest_code, "_learn_http", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        ingest_code,
        "_write_required_ingest_marker",
        lambda *args, **kwargs: tmp_path / ".ingest-code.json",
    )


def test_function_and_class_lessons_use_repository_relative_ranges(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "pkg/app.py",
        "def run():\n"
        "    return 1\n"
        "\n"
        "class Service:\n"
        "    \"\"\"Service docs.\"\"\"\n"
        "    pass\n",
    )

    items = _items(source, repo)
    function_item = _item_by_problem(items, "What does run() do in pkg/app.py:1-2?")
    class_item = _item_by_problem(items, "What is the Service class in pkg/app.py:4-6?")

    assert function_item["solution"].splitlines()[0] == "File: pkg/app.py:1-2"
    assert class_item["solution"].splitlines()[0] == "File: pkg/app.py:4-6"


def test_same_qualified_redefinitions_receive_distinct_questions(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "pkg/app.py",
        "def run():\n"
        "    return 1\n"
        "\n"
        "def run():\n"
        "    return 2\n",
    )

    problems = _problems(_items(source, repo))

    assert "What does run() do in pkg/app.py:1-2?" in problems
    assert "What does run() do in pkg/app.py:4-5?" in problems


def test_same_symbol_and_basename_in_different_directories_are_distinct(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    api_source = _write(repo, "api/app.py", "def load():\n    return 'api'\n")
    worker_source = _write(repo, "worker/app.py", "def load():\n    return 'worker'\n")

    api_problems = _problems(_items(api_source, repo))
    worker_problems = _problems(_items(worker_source, repo))

    assert "What does load() do in api/app.py:1-2?" in api_problems
    assert "What does load() do in worker/app.py:1-2?" in worker_problems
    assert api_problems.isdisjoint(worker_problems - {"What does app.py do?"})


def test_decorated_locator_starts_at_first_decorator(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "pkg/app.py",
        "@decorator\n"
        "@other(arg=1)\n"
        "def run():\n"
        "    return 1\n",
    )

    item = _item_by_problem(
        _items(source, repo),
        "What does run() do in pkg/app.py:1-4?",
    )

    assert item["solution"].splitlines()[0] == "File: pkg/app.py:1-4"


def test_validated_extraction_propagates_repository_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(repo, "pkg/app.py", "def run():\n    return 1\n")

    direct = ingest_code.extract_knowledge(source, codebase_root=repo)
    validated = ingest_code._extract_validated_knowledge(source, codebase_root=repo)

    assert "What does run() do in pkg/app.py:1-2?" in _problems(direct)
    assert "What does run() do in pkg/app.py:1-2?" in _problems(list(validated))


def test_scan_and_rescan_supply_repository_root(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = _write(repo, "pkg/app.py", "def run():\n    return 1\n")
    calls: list[tuple[Path, Path | None]] = []

    def fake_extract(filepath: Path, codebase_root: Path | None = None):
        calls.append((filepath, codebase_root))
        return []

    _install_command_mocks(monkeypatch, tmp_path, source)
    monkeypatch.setattr(ingest_code, "_extract_validated_knowledge", fake_extract)

    ingest_code.scan(**_scan_args(repo))
    ingest_code.rescan(**_rescan_args([repo]))

    assert calls == [(source, repo.resolve()), (source, repo.resolve())]


def test_no_root_preserves_direct_extractor_output(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(repo, "pkg/app.py", "def run():\n    return 1\n")

    item = _item_by_problem(_items(source), "What does run() do in app.py?")

    assert item["solution"].splitlines()[0] == f"File: {source}"


def test_module_lesson_question_remains_basename_based(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(repo, "pkg/app.py", "def run():\n    return 1\n")

    item = _item_by_problem(_items(source, repo), "What does app.py do?")

    assert item["problem"] == "What does app.py do?"
    assert "pkg/app.py:" not in item["problem"]


def test_skill_docs_describe_python_phase1_source_locators() -> None:
    text = SKILL_PATH.read_text()

    assert "Python Phase 1 function and class lesson questions" in text
    assert "repository-relative" in text
    assert "source locators" in text
    assert "module lesson questions remain basename-based" in text
