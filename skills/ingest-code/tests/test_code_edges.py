"""Typed code-edge contract tests for ingest-code graph artifacts."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))

artifact_spec = importlib.util.spec_from_file_location("code_graph_artifact", MODULE_DIR / "code_graph_artifact.py")
assert artifact_spec and artifact_spec.loader
code_graph_artifact = importlib.util.module_from_spec(artifact_spec)
sys.modules[artifact_spec.name] = code_graph_artifact
artifact_spec.loader.exec_module(code_graph_artifact)

ingest_spec = importlib.util.spec_from_file_location("ingest_code", MODULE_DIR / "ingest_code.py")
assert ingest_spec and ingest_spec.loader
ingest_code = importlib.util.module_from_spec(ingest_spec)
sys.modules[ingest_spec.name] = ingest_code
ingest_spec.loader.exec_module(ingest_code)

from code_symbol_record import CodeSymbolRecord


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "code-graph" / "python"


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _copy_fixture(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURE_ROOT, repo)
    return repo


def _symbol(
    repo: Path,
    rel_path: str,
    kind: str,
    name: str,
    qualified_name: str,
    start_line: int,
    end_line: int,
) -> CodeSymbolRecord:
    code = "\n".join((repo / rel_path).read_text().splitlines()[start_line - 1:end_line])
    return CodeSymbolRecord(
        scope="code",
        repo=repo.name,
        root=str(repo),
        branch="main",
        commit="abc123",
        path=rel_path,
        language="python",
        symbol_kind=kind,
        symbol_name=name,
        qualified_name=qualified_name,
        start_line=start_line,
        end_line=end_line,
        signature=code.splitlines()[0] if code else "",
        code=code,
        content_hash=f"hash-{rel_path}-{qualified_name}",
    )


def _symbols(repo: Path) -> list[CodeSymbolRecord]:
    return [
        _symbol(repo, "pkg/provider.py", "function", "imported_target", "imported_target", 1, 2),
        _symbol(repo, "pkg/provider.py", "function", "duplicate", "duplicate", 5, 6),
        _symbol(repo, "pkg/provider.py", "class", "Base", "Base", 9, 11),
        _symbol(repo, "pkg/provider.py", "method", "inherited", "Base.inherited", 10, 11),
        _symbol(repo, "pkg/other.py", "function", "duplicate", "duplicate", 1, 2),
        _symbol(repo, "pkg/consumer.py", "class", "Child", "Child", 6, 10),
        _symbol(repo, "pkg/consumer.py", "method", "run", "Child.run", 7, 10),
        _symbol(repo, "pkg/consumer.py", "function", "local", "local", 13, 16),
    ]


def _write_bundle(repo: Path) -> Path:
    files = sorted(repo.rglob("*.py"))
    result = code_graph_artifact.write_code_graph_bundle(
        codebase_root=repo,
        repo=repo.name,
        branch="main",
        commit="abc123",
        scan_roots=[repo],
        files=files,
        symbols=_symbols(repo),
        edges=ingest_code.extract_edges(files, repo),
    )
    return Path(result["path"])


def test_import_edges_preserve_resolution_state_and_traversal_gate(tmp_path: Path) -> None:
    repo = _copy_fixture(tmp_path)
    bundle = _write_bundle(repo)
    edges = _jsonl(bundle / "edges.jsonl")

    imports = [edge for edge in edges if edge["edge_type"] == "IMPORTS"]
    assert {edge["raw_reference"] for edge in imports} == {"json", "pkg", "pkg.provider"}

    resolved_imports = [edge for edge in imports if edge["resolution_status"] == "resolved"]
    assert {edge["to_path"] for edge in resolved_imports} == {"pkg/provider.py", "pkg/other.py"}
    assert all(edge["active_for_traversal"] is True for edge in resolved_imports)

    json_import = next(edge for edge in imports if edge["raw_reference"] == "json")
    assert json_import["resolution_status"] == "unresolved"
    assert json_import["active_for_traversal"] is False
    assert json_import["to_id"] is None


def test_call_edges_resolve_aliases_inheritance_and_ambiguous_names(tmp_path: Path) -> None:
    repo = _copy_fixture(tmp_path)
    bundle = _write_bundle(repo)
    edges = _jsonl(bundle / "edges.jsonl")
    symbols = {record["symbol_id"]: record for record in _jsonl(bundle / "symbols.jsonl")}

    calls = [edge for edge in edges if edge["edge_type"] == "CALLS"]
    imported_target_calls = [
        edge for edge in calls
        if edge["raw_reference"] == "imported_target" and edge["resolution_status"] == "resolved"
    ]
    assert len(imported_target_calls) == 2
    assert {edge["source_start_line"] for edge in imported_target_calls} == {8, 14}
    assert len({edge["edge_id"] for edge in imported_target_calls}) == 2
    assert {
        symbols[edge["to_id"]]["path"] for edge in imported_target_calls if edge["to_id"]
    } == {"pkg/provider.py"}

    inherited = next(edge for edge in calls if edge["raw_reference"] == "self.inherited")
    assert inherited["resolution_status"] == "resolved"
    assert inherited["resolution_method"] == "enclosing_class_and_inheritance_scope"
    assert inherited["active_for_traversal"] is True
    assert symbols[inherited["to_id"]]["qualified_name"] == "Base.inherited"

    ambiguous = next(edge for edge in calls if edge["raw_reference"] == "duplicate")
    assert ambiguous["resolution_status"] == "candidate"
    assert ambiguous["active_for_traversal"] is False
    assert len(ambiguous["candidate_ids"]) == 2
    assert ambiguous["to_id"] is None
    assert ambiguous["unresolved_reason"] == "ambiguous_same_named_symbols"

    dynamic = next(edge for edge in calls if edge["raw_reference"] == "getattr")
    assert dynamic["resolution_status"] == "unresolved"
    assert dynamic["active_for_traversal"] is False


def test_edge_ids_are_stable_and_resolved_endpoints_exist(tmp_path: Path) -> None:
    repo = _copy_fixture(tmp_path)
    first_bundle = _write_bundle(repo)
    first_edges = _jsonl(first_bundle / "edges.jsonl")
    second_bundle = _write_bundle(repo)
    second_edges = _jsonl(second_bundle / "edges.jsonl")
    assert [edge["edge_id"] for edge in first_edges] == [edge["edge_id"] for edge in second_edges]

    file_ids = {record["file_id"] for record in _jsonl(first_bundle / "files.jsonl")}
    symbol_ids = {record["symbol_id"] for record in _jsonl(first_bundle / "symbols.jsonl")}
    known_ids = file_ids | symbol_ids
    for edge in first_edges:
        assert edge["from_id"] in known_ids
        if edge["resolution_status"] == "resolved":
            assert edge["to_id"] in known_ids
            assert edge["active_for_traversal"] is True
        else:
            assert edge["active_for_traversal"] is False

    coverage = json.loads((first_bundle / "coverage.json").read_text())
    assert coverage["counts"]["edges_resolved"] > 0
    assert coverage["counts"]["edges_candidate"] > 0
    assert coverage["counts"]["edges_unresolved"] > 0
