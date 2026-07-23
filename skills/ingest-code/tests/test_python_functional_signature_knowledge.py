"""Regression tests for canonical Python signatures in functional knowledge."""

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


def _function_item(items: list[dict], name: str) -> dict:
    problem = f"What does {name}() do"
    for item in items:
        if str(item.get("problem", "")).startswith(problem):
            return item
    raise AssertionError(f"function item not found: {name}")


def _description_first_line(item: dict) -> str:
    solution = str(item["solution"])
    return solution.split("\n\n", 1)[1].splitlines()[0]


def _record(
    source: Path,
    repo: Path,
    *,
    name: str,
    start_line: int,
    end_line: int,
):
    return ingest_code._build_code_symbol_record(
        {
            "kind": "function",
            "name": name,
            "start_line": start_line,
            "end_line": end_line,
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


def test_functional_knowledge_uses_all_argument_kinds_annotations_and_defaults(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def run(pos, /, value: int = 1, *args: str, flag: bool, "
        "named='x', **kwargs: object) -> list[str]:\n"
        "    return []\n",
    )

    item = _function_item(ingest_code.extract_python_knowledge(source, source.read_text()), "run")

    assert _description_first_line(item) == (
        "def run(pos, /, value: int=1, *args: str, flag: bool, "
        "named='x', **kwargs: object) -> list[str]"
    )


def test_functional_knowledge_keeps_method_receiver_in_full_signature(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Service:\n"
        "    def run(self, value):\n"
        "        \"\"\"Run service.\"\"\"\n"
        "        return value\n",
    )

    item = _function_item(
        ingest_code.extract_python_knowledge(source, source.read_text()),
        "Service.run",
    )

    assert _description_first_line(item) == "def run(self, value)"


def test_functional_knowledge_renders_async_complex_return_annotation(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "async def load() -> dict[str, list[int]]:\n"
        "    return {}\n",
    )

    item = _function_item(ingest_code.extract_python_knowledge(source, source.read_text()), "load")

    assert _description_first_line(item) == "async def load() -> dict[str, list[int]]"


def test_functional_signature_is_one_line_without_decorator_or_body(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "@decorator\n"
        "def run(\n"
        "    value: int,\n"
        "    *,\n"
        "    flag: bool = True,\n"
        ") -> None:\n"
        "    return None\n",
    )

    item = _function_item(ingest_code.extract_python_knowledge(source, source.read_text()), "run")
    first_line = _description_first_line(item)

    assert first_line == "def run(value: int, *, flag: bool=True) -> None"
    assert "decorator" not in first_line
    assert "return None" not in first_line


def test_functional_signature_does_not_truncate_after_eight_parameters(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def run(a, b, c, d, e, f, g, h, i, j):\n"
        "    return a\n",
    )

    item = _function_item(ingest_code.extract_python_knowledge(source, source.read_text()), "run")

    assert _description_first_line(item) == "def run(a, b, c, d, e, f, g, h, i, j)"


def test_functional_and_code_symbol_signatures_share_canonical_renderer(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def run(value: int = 1) -> str:\n"
        "    return str(value)\n",
    )

    item = _function_item(ingest_code.extract_python_knowledge(source, source.read_text()), "run")
    record = _record(source, repo, name="run", start_line=1, end_line=2)

    assert record is not None
    assert _description_first_line(item) == record.signature.removesuffix(":")
