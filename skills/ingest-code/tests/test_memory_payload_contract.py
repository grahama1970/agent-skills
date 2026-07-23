"""Regression tests for memory compatibility payload classification."""

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


def _assert_no_code_symbol_classification(value) -> None:
    if isinstance(value, dict):
        assert "code_symbol" not in value
        if "type" in value:
            assert value["type"] != "code_symbol"
        metadata = value.get("metadata")
        if isinstance(metadata, dict):
            assert metadata.get("type") != "code_symbol"
        for child in value.values():
            _assert_no_code_symbol_classification(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_code_symbol_classification(child)


class _Response:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def _install_fake_http(monkeypatch, statuses: list[int], requests: list) -> None:
    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def post(self, path: str, json):
            requests.append((path, json))
            return _Response(statuses.pop(0))

    monkeypatch.setattr(ingest_code.httpx, "HTTPTransport", lambda *args, **kwargs: object())
    monkeypatch.setattr(ingest_code.httpx, "Client", FakeClient)


def test_generic_lesson_document_omits_code_symbol_classification() -> None:
    document = ingest_code._build_lesson_document(
        problem="problem",
        solution="solution",
        scope="code",
        tags=["codebase"],
    )

    assert document == {
        "problem": "problem",
        "solution": "solution",
        "scope": "code",
        "tags": ["codebase"],
    }
    assert "code_symbol" not in document
    assert "type" not in document
    assert "metadata" not in document


def test_learn_http_store_payload_is_generic_lesson(monkeypatch) -> None:
    requests = []
    _install_fake_http(monkeypatch, [200], requests)

    assert ingest_code._learn_http("problem", "solution", "scope", ["tag"]) is True

    assert requests == [
        (
            "/store",
            {
                "document": {
                    "problem": "problem",
                    "solution": "solution",
                    "scope": "scope",
                    "tags": ["tag"],
                }
            },
        )
    ]
    _assert_no_code_symbol_classification(requests[0][1])


def test_learn_http_fallback_payload_is_generic_lesson(monkeypatch) -> None:
    requests = []
    _install_fake_http(monkeypatch, [500, 200], requests)

    assert ingest_code._learn_http("problem", "solution", "scope", ["tag"]) is True

    assert requests == [
        (
            "/store",
            {
                "document": {
                    "problem": "problem",
                    "solution": "solution",
                    "scope": "scope",
                    "tags": ["tag"],
                }
            },
        ),
        (
            "/learn",
            {
                "problem": "problem",
                "solution": "solution",
                "scope": "scope",
                "tags": ["tag"],
            },
        ),
    ]
    for _, payload in requests:
        _assert_no_code_symbol_classification(payload)


def test_generic_lesson_builder_copies_tags() -> None:
    tags = ["codebase"]
    document = ingest_code._build_lesson_document("problem", "solution", "code", tags)

    tags.append("mutated")

    assert document["tags"] == ["codebase"]


def test_code_symbol_legacy_fallback_remains_explicitly_classified() -> None:
    record = ingest_code.CodeSymbolRecord(
        scope="code",
        repo="repo",
        root="/repo",
        branch="main",
        commit="abc",
        path="src/app.py",
        language="python",
        symbol_kind="function",
        symbol_name="app",
        qualified_name="app",
        start_line=1,
        end_line=2,
    )

    assert record.to_document()["code_symbol"] is True
    assert record.to_legacy_lesson_document()["code_symbol"] is True
    assert record.to_legacy_lesson_document()["metadata"]["type"] == "code_symbol"


def test_scan_discoverability_payload_is_not_a_code_symbol(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    requests = []
    _install_fake_http(monkeypatch, [200], requests)

    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "collect_files", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "extract_knowledge", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: [])

    ingest_code.scan(
        path=repo,
        glob=[],
        cwe_only=False,
        validate=False,
        treesitter=False,
        code_index=True,
        dry_run=False,
        scope="code",
        batch_size=50,
    )

    assert len(requests) == 1
    assert requests[0][0] == "/store"
    payload = requests[0][1]
    assert payload["document"]["tags"][:2] == ["ingest-code", "indexed-codebase"]
    _assert_no_code_symbol_classification(payload)
