"""Tests for provenance-safe symbol documentation metadata.

Purpose: Ensure ingest-code can enrich Memory retrieval text with derived
symbol summaries without mutating source docstrings or treating generated prose
as authored documentation.
Inputs: CodeSymbolRecord fixtures and deterministic code graph bundles.
Outputs: JSON document and bundle assertions.
Failure modes: Stale summaries, malformed summaries, and generated-file symbols
must fail closed to metadata-only output.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

import code_graph_artifact  # noqa: E402
from code_symbol_record import CodeSymbolRecord  # noqa: E402
from symbol_summary import make_derived_summary, summary_evidence  # noqa: E402


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _record(**overrides) -> CodeSymbolRecord:
    values = {
        "scope": "code",
        "repo": "grahama1970/example",
        "root": "/repo",
        "branch": "main",
        "commit": "abc123",
        "path": "src/example.py",
        "language": "python",
        "symbol_kind": "function",
        "symbol_name": "build_index",
        "qualified_name": "build_index",
        "start_line": 1,
        "end_line": 3,
        "signature": "def build_index(path: Path) -> dict:",
        "parameters": ["path"],
        "called_symbols": ["Path.read_text"],
        "code": "def build_index(path: Path) -> dict:\n    return {'body': path.read_text()}\n",
        "content_hash": "hash-before",
    }
    values.update(overrides)
    return CodeSymbolRecord(**values)


def test_authored_docstring_remains_source_metadata_and_retrieval_purpose_once() -> None:
    record = _record(
        docstring="Build a compact index from a source file.",
        source_docstring="Build a compact index from a source file.",
        code='def build_index(path: Path) -> dict:\n    """Build a compact index from a source file."""\n    return {}\n',
    )

    document = record.to_document()

    assert document["source_docstring"] == "Build a compact index from a source file."
    assert document["docstring"] == document["source_docstring"]
    assert document["source_docstring_status"] == "present"
    assert document["purpose_source"] == "authored"
    assert document["derived_summary"] is None
    assert document["text"].count("Build a compact index from a source file.") == 1


def test_missing_public_io_symbol_requires_documentation_with_evidence_hash() -> None:
    record = _record(source_docstring="", docstring="")

    document = record.to_document()

    assert document["source_docstring"] == ""
    assert document["source_docstring_status"] == "missing"
    assert document["documentation_need"] == "required"
    assert "public_api" in document["documentation_need_reasons"]
    assert "external_io" in document["documentation_need_reasons"]
    assert document["summary_evidence"]["schema"] == "ingest-code.symbol_summary_evidence.v1"
    assert document["summary_evidence"]["evidence_sha256"].startswith("sha256:")
    assert document["purpose_source"] == "none"


def test_private_trivial_helper_is_exempt_and_generated_file_is_exempt() -> None:
    helper = _record(
        symbol_name="_as_list",
        qualified_name="_as_list",
        signature="def _as_list(value):",
        code="def _as_list(value):\n    return []\n",
        called_symbols=[],
        parameters=["value"],
        docstring="",
        source_docstring="",
    ).to_document()
    generated = _record(
        path="src/generated/api_pb2.py",
        code="# generated file\nclass Api:\n    pass\n",
        symbol_kind="class",
        symbol_name="Api",
        qualified_name="Api",
        docstring="",
        source_docstring="",
    ).to_document()

    assert helper["documentation_need"] == "exempt"
    assert "trivial_helper" in helper["documentation_need_reasons"]
    assert generated["source_docstring_status"] == "generated_file"
    assert generated["documentation_need"] == "exempt"


def test_current_derived_summary_is_used_only_when_bound_to_source_evidence() -> None:
    record = _record(docstring="", source_docstring="")
    evidence = summary_evidence(record)
    derived = make_derived_summary(
        text="Builds a source index by reading one path and returning a payload.",
        evidence=evidence,
        generator="proof",
        model="deterministic",
        prompt="Summarize build_index from facts.",
        created_at="2026-08-09T15:30:00Z",
        limitations=["unreviewed"],
    )

    current = _record(docstring="", source_docstring="", derived_summary=derived).to_document()
    stale = _record(docstring="", source_docstring="", content_hash="hash-after", derived_summary=derived).to_document()
    malformed = _record(docstring="", source_docstring="", derived_summary={"text": "Unsupported"}).to_document()

    assert current["purpose_source"] == "derived"
    assert current["derived_summary"]["status"] == "derived_unreviewed"
    assert "Builds a source index" in current["text"]
    assert stale["purpose_source"] == "none"
    assert stale["derived_summary"] is None
    assert malformed["derived_summary"] is None


def test_code_graph_bundle_readback_exposes_documentation_metadata(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    source = repo / "src" / "example.py"
    source.write_text("def build_index(path):\n    return {'body': path.read_text()}\n", encoding="utf-8")
    _git(repo, "init")

    symbol = _record(root=str(repo), repo=repo.name, path="src/example.py")
    result = code_graph_artifact.write_code_graph_bundle(
        codebase_root=repo,
        repo=repo.name,
        branch="main",
        commit="abc123",
        scan_roots=[repo],
        files=[source],
        symbols=[symbol],
        edges=[],
    )

    symbols = _jsonl(Path(result["path"]) / "symbols.jsonl")

    assert symbols[0]["source_docstring_status"] == "missing"
    assert symbols[0]["documentation_need"] == "required"
    assert symbols[0]["summary_evidence"]["symbol_id"] == symbol.symbol_id
    assert symbols[0]["retrieval_text_sha256"] == symbols[0]["memory_document"]["retrieval_text_sha256"]
