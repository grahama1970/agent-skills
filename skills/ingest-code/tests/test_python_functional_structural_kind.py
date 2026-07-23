"""Regression tests for Python structural kinds in functional knowledge."""

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


def _item_by_problem(items: list[dict], problem: str) -> dict:
    for item in items:
        if item.get("problem") == problem:
            return item
    raise AssertionError(f"item not found: {problem}")


def _problems(items: list[dict]) -> set[str]:
    return {str(item.get("problem", "")) for item in items}


def _line(item: dict, prefix: str) -> str:
    solution = str(item["solution"])
    return next(line for line in solution.splitlines() if line.startswith(prefix))


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


def test_instance_async_static_and_class_methods_emit_method_kind(
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
        "    async def load(self):\n"
        "        \"\"\"Load service.\"\"\"\n"
        "        return 2\n"
        "\n"
        "    @staticmethod\n"
        "    def build(value):\n"
        "        \"\"\"Build service.\"\"\"\n"
        "        return value\n"
        "\n"
        "    @classmethod\n"
        "    def make(cls):\n"
        "        \"\"\"Make service.\"\"\"\n"
        "        return cls()\n",
    )

    items = _items(source)

    for name in ("run", "load", "build", "make"):
        item = _item_by_problem(items, f"What does Service.{name}() do in app.py?")
        assert _line(item, "Kind: ") == "Kind: method"
        assert "kind:method" in item["tags"]


def test_nested_function_inside_method_emits_function_kind(tmp_path: Path) -> None:
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

    assert _line(item, "Kind: ") == "Kind: function"
    assert "kind:function" in item["tags"]


def test_top_level_function_and_class_emit_structural_kinds(
    tmp_path: Path,
) -> None:
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

    assert _line(function_item, "Kind: ") == "Kind: function"
    assert _line(class_item, "Kind: ") == "Kind: class"
    assert "kind:function" in function_item["tags"]
    assert "kind:class" in class_item["tags"]


def test_legacy_function_and_class_tags_are_preserved(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Service:\n"
        "    \"\"\"Service docs.\"\"\"\n"
        "    def run(self):\n"
        "        \"\"\"Run service.\"\"\"\n"
        "        return 1\n",
    )

    items = _items(source)
    class_item = _item_by_problem(items, "What is the Service class in app.py?")
    method_item = _item_by_problem(items, "What does Service.run() do in app.py?")

    assert class_item["tags"] == [
        "codebase",
        "class",
        "Service",
        "app",
        "qualified:Service",
        "kind:class",
    ]
    assert method_item["tags"] == [
        "codebase",
        "function",
        "run",
        "app",
        "qualified:Service.run",
        "kind:method",
    ]


def test_functional_and_code_symbol_structural_kinds_match(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Service:\n"
        "    def run(self):\n"
        "        \"\"\"Run service.\"\"\"\n"
        "        return 1\n",
    )

    item = _item_by_problem(_items(source), "What does Service.run() do in app.py?")
    record = _record(source, repo, kind="function", name="run", start_line=2)

    assert record is not None
    assert _line(item, "Kind: ") == f"Kind: {record.symbol_kind}"
    assert f"kind:{record.symbol_kind}" in item["tags"]


def test_structural_kind_does_not_change_private_or_docstring_selection(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Service:\n"
        "    def undocumented(self):\n"
        "        def helper():\n"
        "            return 1\n"
        "        return helper\n"
        "\n"
        "def _private():\n"
        "    \"\"\"Private helper.\"\"\"\n"
        "    return 2\n",
    )

    problems = _problems(_items(source))

    assert "What does Service.undocumented.helper() do in app.py?" not in problems
    assert "What does _private() do in app.py?" not in problems
