"""Regression tests for Python qualified identities in functional knowledge."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "ingest_code.py"
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


def _items(source: Path) -> list[dict]:
    return ingest_code.extract_python_knowledge(source, source.read_text())


def _problems(items: list[dict]) -> set[str]:
    return {str(item.get("problem", "")) for item in items}


def _item_by_problem(items: list[dict], problem: str) -> dict:
    for item in items:
        if item.get("problem") == problem:
            return item
    raise AssertionError(f"item not found: {problem}")


def _qualified_line(item: dict) -> str:
    solution = str(item["solution"])
    return next(
        line
        for line in solution.splitlines()
        if line.startswith("Qualified name: ")
    )


def _record(
    source: Path,
    repo: Path,
    *,
    kind: str,
    name: str,
    start_line: int,
):
    return ingest_code._build_code_symbol_record(
        {
            "kind": kind,
            "name": name,
            "start_line": start_line,
            "end_line": start_line,
            "signature": "treesitter signature",
        },
        source,
        repo,
        "code",
        "repo",
        "branch",
        "commit",
        [],
    )


def test_same_named_methods_in_different_classes_get_distinct_identities(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Alpha:\n"
        "    def run(self):\n"
        "        \"\"\"Run alpha.\"\"\"\n"
        "        return 'alpha'\n"
        "\n"
        "class Beta:\n"
        "    def run(self):\n"
        "        \"\"\"Run beta.\"\"\"\n"
        "        return 'beta'\n",
    )

    problems = _problems(_items(source))

    assert "What does Alpha.run() do in app.py?" in problems
    assert "What does Beta.run() do in app.py?" in problems
    assert "What does run() do in app.py?" not in problems


def test_nested_function_uses_full_class_method_ancestry(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Service:\n"
        "    def method(self):\n"
        "        def helper():\n"
        "            \"\"\"Help method.\"\"\"\n"
        "            return 1\n"
        "        return helper\n",
    )

    problems = _problems(_items(source))

    assert "What does Service.method.helper() do in app.py?" in problems


def test_nested_class_uses_full_class_ancestry(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Outer:\n"
        "    class Inner:\n"
        "        \"\"\"Inner docs.\"\"\"\n"
        "        def a(self):\n"
        "            pass\n",
    )

    problems = _problems(_items(source))

    assert "What is the Outer.Inner class in app.py?" in problems


def test_top_level_function_and_class_keep_bare_identity(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def run(value):\n"
        "    return value\n"
        "\n"
        "class Service:\n"
        "    \"\"\"Service docs.\"\"\"\n"
        "    pass\n",
    )

    items = _items(source)
    function_item = _item_by_problem(items, "What does run() do in app.py?")
    class_item = _item_by_problem(items, "What is the Service class in app.py?")

    assert _qualified_line(function_item) == "Qualified name: run"
    assert _qualified_line(class_item) == "Qualified name: Service"


def test_qualified_tag_is_additive_and_selection_policy_is_unchanged(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Service:\n"
        "    def run(self):\n"
        "        \"\"\"Run service.\"\"\"\n"
        "        return 1\n"
        "\n"
        "def _private():\n"
        "    \"\"\"Private helper.\"\"\"\n"
        "    return 2\n",
    )

    items = _items(source)
    item = _item_by_problem(items, "What does Service.run() do in app.py?")

    assert item["tags"] == [
        "codebase",
        "function",
        "run",
        "app",
        "qualified:Service.run",
    ]
    assert "What does _private() do in app.py?" not in _problems(items)


def test_functional_and_code_symbol_qualified_names_match(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Service:\n"
        "    def method(self):\n"
        "        def helper():\n"
        "            \"\"\"Help method.\"\"\"\n"
        "            return 1\n",
    )

    item = _item_by_problem(
        _items(source),
        "What does Service.method.helper() do in app.py?",
    )
    record = _record(source, repo, kind="function", name="helper", start_line=3)

    assert record is not None
    assert _qualified_line(item) == f"Qualified name: {record.qualified_name}"
