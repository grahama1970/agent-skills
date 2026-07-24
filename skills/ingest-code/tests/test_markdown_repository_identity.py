"""Regression tests for repository-relative Markdown lesson identities."""

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


def _write_markdown(repo: Path, relative_path: str, body: str | None = None) -> Path:
    content = body or (
        "# Setup\n\n"
        "This section describes repository setup details, expected local "
        "commands, and operational notes that are intentionally long enough "
        "to pass the Markdown section inclusion threshold.\n"
    )
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def test_same_named_markdown_files_have_distinct_repository_relative_questions(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    first = _write_markdown(repo, "docs/README.md")
    second = _write_markdown(repo, "packages/api/README.md")

    first_items = ingest_code.extract_knowledge(first, codebase_root=repo)
    second_items = ingest_code.extract_knowledge(second, codebase_root=repo)

    assert first_items[0]["problem"] == "What does 'Setup' say in docs/README.md?"
    assert second_items[0]["problem"] == "What does 'Setup' say in packages/api/README.md?"


def test_markdown_solution_uses_relative_file_identity_without_checkout_path(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write_markdown(repo, "docs/README.md")

    item = ingest_code.extract_knowledge(source, codebase_root=repo)[0]

    assert "File: docs/README.md" in item["solution"]
    assert str(repo) not in item["solution"]


def test_extract_knowledge_forwards_repository_root_for_md_and_mdx(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    markdown = _write_markdown(repo, "docs/guide.md")
    mdx = _write_markdown(repo, "docs/page.mdx")

    markdown_item = ingest_code.extract_knowledge(markdown, codebase_root=repo)[0]
    mdx_item = ingest_code.extract_knowledge(mdx, codebase_root=repo)[0]

    assert markdown_item["problem"] == "What does 'Setup' say in docs/guide.md?"
    assert mdx_item["problem"] == "What does 'Setup' say in docs/page.mdx?"


def test_direct_markdown_helper_preserves_basename_compatibility(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write_markdown(repo, "docs/README.md")
    content = source.read_text()

    item = ingest_code.extract_markdown_knowledge(source, content)[0]

    assert item["problem"] == "What does 'Setup' say in README.md?"
    assert "File: README.md" in item["solution"]


def test_markdown_identity_change_preserves_section_body_and_tags(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    body = (
        "# Architecture Notes\n\n"
        "The service keeps route handlers thin, centralizes parsing behavior, "
        "and records operational decisions beside the code so future agents "
        "can recover the intent without scanning unrelated systems.\n"
    )
    source = _write_markdown(repo, "docs/architecture.md", body)

    item = ingest_code.extract_knowledge(source, codebase_root=repo)[0]

    assert "The service keeps route handlers thin" in item["solution"]
    assert "Section: Architecture Notes" in item["solution"]
    assert item["tags"] == [
        "codebase",
        "documentation",
        "architecture",
        "architecture-notes",
    ]


def test_skill_docs_describe_markdown_repository_identities() -> None:
    text = SKILL_PATH.read_text()

    assert "Markdown section lessons use repository-relative file identities" in text
    assert "direct helper calls without a repository root retain basename" in text
