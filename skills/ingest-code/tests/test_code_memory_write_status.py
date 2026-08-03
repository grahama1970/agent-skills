from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))

for module_name in ["code_symbol_record", "code_memory_client", "ingest_code"]:
    spec = importlib.util.spec_from_file_location(module_name, MODULE_DIR / f"{module_name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

from code_memory_client import CodeMemoryClient
from code_symbol_record import CodeSymbolRecord
import ingest_code


class FakeResponse:
    def __init__(self, status_code: int, text: str = "", payload: dict | None = None) -> None:
        self.status_code = status_code
        self.text = text
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


class ScriptedHttpClient:
    def __init__(
        self,
        *,
        upsert_statuses: list[int],
        store_status: int = 200,
        learn_status: int = 200,
        readback: str = "match",
    ) -> None:
        self.upsert_statuses = list(upsert_statuses)
        self.store_status = store_status
        self.learn_status = learn_status
        self.readback = readback
        self.documents: dict[str, dict] = {}
        self.posts: list[tuple[str, dict]] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, path: str, json: dict):
        self.posts.append((path, json))
        if path == "/upsert":
            status = self.upsert_statuses.pop(0) if self.upsert_statuses else 200
            if 200 <= status < 300:
                for document in json["documents"]:
                    self.documents[document["_key"]] = dict(document)
                return FakeResponse(status)
            return FakeResponse(status, f"upsert-{status}")
        if path == "/get":
            if self.readback == "unavailable":
                return FakeResponse(404, "missing")
            document = dict(self.documents.get(json["key"], {}))
            if self.readback == "mismatch":
                document["content_hash"] = "stale"
            return FakeResponse(200, payload={"document": document})
        if path == "/store":
            return FakeResponse(self.store_status, f"store-{self.store_status}")
        if path == "/learn":
            return FakeResponse(self.learn_status, f"learn-{self.learn_status}")
        raise AssertionError(f"unexpected path {path}")


def _record(name: str, *, line: int = 1) -> CodeSymbolRecord:
    return CodeSymbolRecord(
        scope="test",
        repo="github.com/example/repo",
        repository_id="github.com/example/repo",
        root="/repo",
        branch="main",
        commit="abc",
        path="app.py",
        language="python",
        symbol_kind="function",
        symbol_name=name,
        qualified_name=name,
        start_line=line,
        end_line=line + 1,
        code=f"def {name}():\n    return {line}\n",
    )


def _client(fake: ScriptedHttpClient) -> CodeMemoryClient:
    client = CodeMemoryClient()
    client._client = lambda: fake  # type: ignore[method-assign]
    return client


def _status_dict(result) -> dict:
    return {
        "attempted": result.attempted,
        "structured_upsert_stored": result.structured_upsert_stored,
        "legacy_fallback_stored": result.legacy_fallback_stored,
        "structured_verified": result.structured_verified,
        "failed": result.failed,
        "write_status": result.write_status,
        "record_results": list(result.record_results),
    }


def test_all_structured_upserts_succeed_after_exact_key_readback() -> None:
    fake = ScriptedHttpClient(upsert_statuses=[200])
    records = [_record("first"), _record("second", line=3)]

    result = _client(fake).upsert_code_symbols(records, batch_size=10)

    assert result.write_status == "complete"
    assert result.stored == 2
    assert result.structured_upsert_stored == 2
    assert result.legacy_fallback_stored == 0
    assert result.structured_verified == 2
    assert result.failed == 0
    assert {item["route"] for item in result.record_results} == {"structured_upsert"}
    assert [path for path, _ in fake.posts].count("/get") == 2


def test_single_structured_failure_with_legacy_fallback_is_degraded(tmp_path: Path) -> None:
    fake = ScriptedHttpClient(upsert_statuses=[500], store_status=200)
    result = _client(fake).upsert_code_symbols([_record("fallback")], batch_size=1)

    assert result.write_status == "degraded"
    assert result.stored == 1
    assert result.structured_upsert_stored == 0
    assert result.legacy_fallback_stored == 1
    assert result.failed == 0
    assert result.record_results[0]["route"] == "legacy_fallback"
    assert "/get" not in [path for path, _ in fake.posts]

    marker_path = ingest_code._write_ingest_marker(
        tmp_path,
        files_scanned=1,
        knowledge_stored=0,
        cwe_stored=0,
        edges_stored=0,
        code_symbols_stored=result.structured_upsert_stored,
        treesitter=True,
        scope="test",
        code_symbols_write_status=_status_dict(result),
    )
    marker = json.loads(marker_path.read_text())
    assert marker["code_index"]["enabled"] is False
    assert marker["code_index"]["collection"] is None
    assert marker["code_index"]["hybrid_retrieval_capable"] is False
    assert marker["code_index"]["write_status"] == "degraded"
    assert marker["code_index"]["legacy_fallback_stored"] == 1


def test_structured_and_legacy_write_failure_is_failed(tmp_path: Path) -> None:
    fake = ScriptedHttpClient(upsert_statuses=[500], store_status=500, learn_status=500)
    result = _client(fake).upsert_code_symbols([_record("lost")], batch_size=1)

    assert result.write_status == "failed"
    assert result.stored == 0
    assert result.structured_upsert_stored == 0
    assert result.legacy_fallback_stored == 0
    assert result.failed == 1
    assert result.errors

    marker_path = ingest_code._write_ingest_marker(
        tmp_path,
        files_scanned=1,
        knowledge_stored=0,
        cwe_stored=0,
        edges_stored=0,
        code_symbols_stored=0,
        treesitter=True,
        scope="test",
        code_symbols_write_status=_status_dict(result),
    )
    marker = json.loads(marker_path.read_text())
    assert marker["code_index"]["enabled"] is False
    assert marker["code_index"]["write_status"] == "failed"
    assert marker["local_artifacts"]["code_symbols_write_status"]["failed"] == 1


def test_stale_exact_key_readback_prevents_structured_success() -> None:
    fake = ScriptedHttpClient(upsert_statuses=[200], readback="mismatch")

    result = _client(fake).upsert_code_symbols([_record("stale")], batch_size=1)

    assert result.write_status == "failed"
    assert result.structured_upsert_stored == 0
    assert result.structured_verified == 0
    assert result.failed == 1
    assert result.record_results[0]["route"] == "structured_upsert"
    assert result.record_results[0]["status"] == "failed"
    assert "readback_mismatch:content_hash" in result.errors[0]


def test_exact_key_readback_unavailable_after_legacy_only_fallback() -> None:
    fake = ScriptedHttpClient(upsert_statuses=[500], store_status=200, readback="unavailable")

    result = _client(fake).upsert_code_symbols([_record("legacy_only")], batch_size=1)

    assert result.write_status == "degraded"
    assert result.legacy_fallback_stored == 1
    assert result.structured_upsert_stored == 0
    assert "/get" not in [path for path, _ in fake.posts]


def test_exact_key_readback_unavailable_after_upsert_blocks_complete_status() -> None:
    fake = ScriptedHttpClient(upsert_statuses=[200], readback="unavailable")

    result = _client(fake).upsert_code_symbols([_record("unreadable")], batch_size=1)

    assert result.write_status == "failed"
    assert result.structured_upsert_stored == 0
    assert result.failed == 1
    assert "readback_missing" in result.errors[0]
