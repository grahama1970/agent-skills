"""Regression tests for repository-relative generic lesson identities."""

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


def _write_source(repo: Path, relative_path: str, content: str) -> Path:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _module_record(items: list[dict]) -> dict:
    return next(item for item in items if "module" in item["tags"])


def _export_record(items: list[dict], symbol: str) -> dict:
    return next(
        item
        for item in items
        if "export" in item["tags"] and symbol in item["tags"]
    )


def _typescript_content(symbol: str = "start") -> str:
    return (
        "// Package entrypoint for local service startup behavior.\n"
        "// Records the expected public export used by callers.\n"
        f"export function {symbol}() {{\n"
        "  return true;\n"
        "}\n"
    )


def test_same_named_typescript_exports_have_distinct_repository_relative_questions(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    src_index = _write_source(repo, "src/index.ts", _typescript_content())
    tools_index = _write_source(repo, "tools/index.ts", _typescript_content())

    src_record = _export_record(
        ingest_code.extract_knowledge(src_index, codebase_root=repo),
        "start",
    )
    tools_record = _export_record(
        ingest_code.extract_knowledge(tools_index, codebase_root=repo),
        "start",
    )

    assert src_record["problem"] == "What is start in src/index.ts?"
    assert tools_record["problem"] == "What is start in tools/index.ts?"


def test_generic_comment_module_uses_repository_relative_identity(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write_source(
        repo,
        "crates/app/src/lib.rs",
        (
            "// Library module for service construction and request routing.\n"
            "// Keeps setup details close to the Rust entry points.\n"
            "pub fn run() {}\n"
        ),
    )

    record = _module_record(ingest_code.extract_knowledge(source, codebase_root=repo))

    assert record["problem"] == "What does crates/app/src/lib.rs do?"


def test_generic_solutions_use_relative_paths_without_checkout_root(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write_source(repo, "src/index.ts", _typescript_content())

    items = ingest_code.extract_knowledge(source, codebase_root=repo)

    assert items
    assert all("File: src/index.ts" in item["solution"] for item in items)
    assert all(str(repo) not in item["solution"] for item in items)


def test_direct_generic_helper_retains_basename_identity(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write_source(repo, "src/index.ts", _typescript_content())
    content = source.read_text()

    items = ingest_code.extract_generic_knowledge(source, content)
    module = _module_record(items)
    export = _export_record(items, "start")

    assert module["problem"] == "What does index.ts do?"
    assert export["problem"] == "What is start in index.ts?"
    assert "File: index.ts" in module["solution"]
    assert "File: index.ts" in export["solution"]


def test_generic_identity_change_preserves_content_symbols_and_tags(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write_source(repo, "src/index.ts", _typescript_content("startServer"))

    items = ingest_code.extract_knowledge(source, codebase_root=repo)
    module = _module_record(items)
    export = _export_record(items, "startServer")

    assert "Package entrypoint for local service startup behavior" in module["solution"]
    assert "Exported symbol: startServer" in export["solution"]
    assert module["tags"] == ["codebase", "module", "index"]
    assert export["tags"] == ["codebase", "export", "startServer", "index"]


def test_skill_docs_describe_generic_repository_identities() -> None:
    text = SKILL_PATH.read_text()

    assert (
        "Generic non-Python module-comment and TS/JS export lessons use"
        in text
    )
    assert "repository-relative file identities during `scan` and `rescan`" in text
    assert "direct helper calls without a repository root retain basename" in text
