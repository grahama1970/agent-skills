"""Regression tests for canonical Python class signatures in functional knowledge."""

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


def _class_item(items: list[dict], name: str) -> dict:
    problem = f"What is the {name} class"
    for item in items:
        if str(item.get("problem", "")).startswith(problem):
            return item
    raise AssertionError(f"class item not found: {name}")


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
            "kind": "class",
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


def test_class_knowledge_renders_complex_bases_metaclass_and_kwargs(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Service(Base, metaclass=Meta, **opts):\n"
        "    \"\"\"Service docs.\"\"\"\n"
        "    pass\n",
    )

    item = _class_item(ingest_code.extract_python_knowledge(source, source.read_text()), "Service")

    assert _description_first_line(item) == "class Service(Base, metaclass=Meta, **opts)"


def test_class_knowledge_renders_subscripted_and_called_bases_without_placeholder(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Repo(Mapping[str, int], factory('x')):\n"
        "    \"\"\"Repo docs.\"\"\"\n"
        "    pass\n",
    )

    item = _class_item(ingest_code.extract_python_knowledge(source, source.read_text()), "Repo")
    first_line = _description_first_line(item)

    assert first_line == "class Repo(Mapping[str, int], factory('x'))"
    assert "?" not in first_line


def test_decorated_multiline_class_has_one_line_decorator_free_signature(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "@decorator\n"
        "class Service(\n"
        "    Base,\n"
        "    metaclass=Meta,\n"
        "):\n"
        "    \"\"\"Service docs.\"\"\"\n"
        "    pass\n",
    )

    item = _class_item(ingest_code.extract_python_knowledge(source, source.read_text()), "Service")
    first_line = _description_first_line(item)

    assert first_line == "class Service(Base, metaclass=Meta)"
    assert "decorator" not in first_line


def test_class_without_bases_omits_empty_parentheses(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Plain:\n"
        "    \"\"\"Plain docs.\"\"\"\n"
        "    pass\n",
    )

    item = _class_item(ingest_code.extract_python_knowledge(source, source.read_text()), "Plain")

    assert _description_first_line(item) == "class Plain"


def test_methods_and_cleaned_docstring_remain_after_canonical_signature(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Service(Base):\n"
        "    \"\"\"\n"
        "    Service docs.\n"
        "\n"
        "        Detail.\n"
        "    \"\"\"\n"
        "    def a(self):\n"
        "        pass\n"
        "    async def b(self):\n"
        "        pass\n"
        "    def c(self):\n"
        "        pass\n",
    )

    item = _class_item(ingest_code.extract_python_knowledge(source, source.read_text()), "Service")
    solution = str(item["solution"])

    assert _description_first_line(item) == "class Service(Base)"
    assert "Methods: a, b, c" in solution
    assert "Service docs.\n\n    Detail." in solution


def test_functional_and_code_symbol_class_signatures_share_renderer(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Service(Base, metaclass=Meta):\n"
        "    \"\"\"Service docs.\"\"\"\n"
        "    pass\n",
    )

    item = _class_item(ingest_code.extract_python_knowledge(source, source.read_text()), "Service")
    record = _record(source, repo, name="Service", start_line=1, end_line=3)

    assert record is not None
    assert _description_first_line(item) == record.signature.removesuffix(":")
