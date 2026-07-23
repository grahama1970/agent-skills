"""Regression tests for Python module-scope functional knowledge discovery."""

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


def test_undocumented_module_scope_function_inside_if_is_emitted(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "if enabled:\n"
        "    def configure(value):\n"
        "        return value\n",
    )

    item = _item_by_problem(_items(source), "What does configure() do in app.py?")

    assert "def configure(value)" in item["solution"]
    assert "Qualified name: configure" in item["solution"]
    assert "Kind: function" in item["solution"]


def test_undocumented_module_scope_async_function_inside_try_is_emitted(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "try:\n"
        "    async def load():\n"
        "        return {}\n"
        "except RuntimeError:\n"
        "    pass\n",
    )

    item = _item_by_problem(_items(source), "What does load() do in app.py?")

    assert "async def load()" in item["solution"]
    assert "kind:function" in item["tags"]


def test_module_summary_includes_control_flow_declarations_in_source_order(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "if enabled:\n"
        "    def first():\n"
        "        return 1\n"
        "\n"
        "    class Service:\n"
        "        pass\n"
        "\n"
        "try:\n"
        "    async def second():\n"
        "        return 2\n"
        "except RuntimeError:\n"
        "    pass\n",
    )

    module_item = _item_by_problem(_items(source), "What does app.py do?")

    assert "Defines: first, Service, second" in module_item["solution"]


def test_undocumented_method_and_nested_function_remain_excluded(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Service:\n"
        "    def method(self):\n"
        "        return 1\n"
        "\n"
        "def outer():\n"
        "    def helper():\n"
        "        return 2\n"
        "    return helper\n",
    )

    problems = _problems(_items(source))

    assert "What does Service.method() do in app.py?" not in problems
    assert "What does outer.helper() do in app.py?" not in problems
    assert "What does outer() do in app.py?" in problems


def test_documented_nested_function_remains_eligible(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def outer():\n"
        "    def helper():\n"
        "        \"\"\"Help outer.\"\"\"\n"
        "        return 1\n"
        "    return helper\n",
    )

    item = _item_by_problem(_items(source), "What does outer.helper() do in app.py?")

    assert "Help outer." in item["solution"]
    assert "kind:function" in item["tags"]


def test_private_module_scope_function_remains_excluded(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "if enabled:\n"
        "    def _private():\n"
        "        \"\"\"Private helper.\"\"\"\n"
        "        return 1\n",
    )

    assert "What does _private() do in app.py?" not in _problems(_items(source))
