"""Regression tests for guaranteed Python module functional lessons."""

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


def _items(source: Path) -> list[dict]:
    return ingest_code.extract_python_knowledge(source, source.read_text())


def _module_items(source: Path) -> list[dict]:
    return [
        item
        for item in _items(source)
        if item.get("tags") == ["codebase", "module", source.stem]
    ]


def _module_item(source: Path) -> dict:
    items = _module_items(source)
    assert len(items) == 1
    return items[0]


def test_import_only_python_file_emits_module_lesson(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(repo, "pkg/app.py", "import os\nfrom sys import path\n")

    item = _module_item(source)

    assert item["problem"] == "What does app.py do?"
    assert item["solution"] == (
        "Module: app.py\n\nNo module docstring or named declarations."
    )


def test_assignment_only_python_file_emits_module_lesson(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(repo, "pkg/settings.py", "VALUE = 1\n")

    item = _module_item(source)

    assert item["problem"] == "What does settings.py do?"
    assert item["tags"] == ["codebase", "module", "settings"]


def test_empty_python_file_emits_module_lesson(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(repo, "pkg/empty.py", "")

    item = _module_item(source)

    assert item["problem"] == "What does empty.py do?"
    assert "No module docstring or named declarations." in item["solution"]


def test_long_module_docstring_output_is_unchanged(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    doc = "This module has a long enough docstring."
    source = _write(repo, "pkg/app.py", f'"""{doc}"""\nVALUE = 1\n')

    item = _module_item(source)

    assert item["solution"] == f"Module: app.py\n\n{doc}"


def test_named_declaration_summary_output_is_unchanged(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "pkg/app.py",
        "def run():\n"
        "    return 1\n"
        "\n"
        "class Service:\n"
        "    pass\n",
    )

    item = _module_item(source)

    assert item["solution"] == "Module: app.py\n\nDefines: run, Service"


def test_python_file_emits_exactly_one_module_lesson(tmp_path: Path) -> None:
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

    assert len(_module_items(source)) == 1


def test_import_edge_titles_match_import_only_module_lessons(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(repo, "app.py", "import config\n")
    target = _write(repo, "config.py", "import os\n")
    edges = ingest_code.extract_edges([source, target], repo)

    target_item = _module_item(target)

    assert target_item["problem"] == "What does config.py do?"
    assert edges == [
        {
            "from_file": str(source),
            "to_file": str(target.resolve()),
            "edge_type": "depends_on",
            "module": "config",
            "names": [],
        }
    ]


def test_skill_docs_describe_module_lesson_presence() -> None:
    text = SKILL_PATH.read_text()

    assert "Every successfully parsed Python file emits exactly one module lesson" in text
    assert "import-only" in text
    assert "empty modules" in text
