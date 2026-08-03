"""Memory daemon client for ingest-code structured writes."""

from __future__ import annotations

from dataclasses import dataclass
import os

import httpx
from dotenv import load_dotenv

from code_symbol_record import CodeSymbolRecord


load_dotenv(override=False)

MEMORY_SOCKET_PATH = "/run/user/1000/embry/memory.sock"
DEFAULT_CODE_SYMBOLS_BATCH_SIZE = 100
CODE_SYMBOLS_BATCH_SIZE_ENV = "CODE_SYMBOLS_QDRANT_BATCH_SIZE"


@dataclass(frozen=True)
class MemoryWriteResult:
    stored: int
    attempted: int
    errors: list[str]


@dataclass(frozen=True)
class CodeSymbolWriteResult(MemoryWriteResult):
    structured_upsert_stored: int
    legacy_fallback_stored: int
    structured_verified: int
    failed: int
    write_status: str
    stored_records: tuple[CodeSymbolRecord, ...]
    structured_records: tuple[CodeSymbolRecord, ...]
    legacy_records: tuple[CodeSymbolRecord, ...]
    failed_records: tuple[CodeSymbolRecord, ...]
    record_results: tuple[dict, ...]


class CodeMemoryClient:
    """Small Unix-socket client for memory-owned code indexing."""

    def __init__(self, socket_path: str = MEMORY_SOCKET_PATH, timeout: float = 30.0):
        self.socket_path = socket_path
        self.timeout = timeout

    def _client(self) -> httpx.Client:
        transport = httpx.HTTPTransport(uds=self.socket_path)
        return httpx.Client(transport=transport, base_url="http://localhost", timeout=self.timeout)

    def upsert_code_symbols(
        self,
        records: list[CodeSymbolRecord],
        collection: str = "code_symbols",
        batch_size: int | None = None,
    ) -> CodeSymbolWriteResult:
        """Upsert structured code symbols, splitting failed batches first."""
        if not records:
            return CodeSymbolWriteResult(
                stored=0,
                attempted=0,
                errors=[],
                structured_upsert_stored=0,
                legacy_fallback_stored=0,
                structured_verified=0,
                failed=0,
                write_status="complete",
                stored_records=(),
                structured_records=(),
                legacy_records=(),
                failed_records=(),
                record_results=(),
            )

        effective_batch_size = self._resolve_batch_size(batch_size)
        structured_records: list[CodeSymbolRecord] = []
        legacy_records: list[CodeSymbolRecord] = []
        failed_records: list[CodeSymbolRecord] = []
        record_results: list[dict] = []
        errors: list[str] = []

        def append_result(record: CodeSymbolRecord, *, route: str, status: str, error: str = "") -> None:
            record_results.append({
                "symbol_id": record.symbol_id,
                "symbol_version_id": record.symbol_version_id,
                "qualified_name": record.qualified_name,
                "route": route,
                "status": status,
                "error": error,
            })

        def store_batch(batch: list[CodeSymbolRecord], client: httpx.Client) -> None:
            upsert_error = self._upsert_batch(batch, collection=collection, client=client)
            if upsert_error is None:
                for record in batch:
                    verification_error = self._verify_structured_code_symbol(record, collection, client)
                    if verification_error is None:
                        structured_records.append(record)
                        append_result(record, route="structured_upsert", status="stored")
                    else:
                        failed_records.append(record)
                        error = f"exact readback failed for {record.qualified_name}: {verification_error}"
                        errors.append(error)
                        append_result(record, route="structured_upsert", status="failed", error=error)
                return

            if len(batch) > 1:
                midpoint = len(batch) // 2
                store_batch(batch[:midpoint], client)
                store_batch(batch[midpoint:], client)
                return

            record = batch[0]
            if self.store_legacy_code_symbol(record, client=client):
                legacy_records.append(record)
                append_result(record, route="legacy_fallback", status="stored", error=upsert_error)
                return

            failed_records.append(record)
            error = (
                f"upsert and legacy fallback failed for {record.qualified_name}: "
                f"upsert={upsert_error}; legacy=fallback failed"
            )
            errors.append(error)
            append_result(record, route="failed", status="failed", error=error)

        with self._client() as client:
            for i in range(0, len(records), effective_batch_size):
                store_batch(records[i : i + effective_batch_size], client)

        stored_records = [*structured_records, *legacy_records]
        failed = len(failed_records)
        if failed:
            write_status = "failed"
        elif legacy_records:
            write_status = "degraded"
        else:
            write_status = "complete"
        return CodeSymbolWriteResult(
            stored=len(stored_records),
            attempted=len(records),
            errors=errors,
            stored_records=tuple(stored_records),
            structured_upsert_stored=len(structured_records),
            legacy_fallback_stored=len(legacy_records),
            structured_verified=len(structured_records),
            failed=failed,
            write_status=write_status,
            structured_records=tuple(structured_records),
            legacy_records=tuple(legacy_records),
            failed_records=tuple(failed_records),
            record_results=tuple(record_results),
        )

    def _resolve_batch_size(self, requested: int | None) -> int:
        """Resolve the per-call structured upsert batch size."""
        if requested is not None:
            return requested if requested > 0 else DEFAULT_CODE_SYMBOLS_BATCH_SIZE

        raw = os.environ.get(CODE_SYMBOLS_BATCH_SIZE_ENV)
        if not raw:
            return DEFAULT_CODE_SYMBOLS_BATCH_SIZE

        try:
            parsed = int(raw)
        except (TypeError, ValueError):
            return DEFAULT_CODE_SYMBOLS_BATCH_SIZE

        return parsed if parsed > 0 else DEFAULT_CODE_SYMBOLS_BATCH_SIZE

    def _upsert_batch(
        self,
        records: list[CodeSymbolRecord],
        collection: str,
        client: httpx.Client,
    ) -> str | None:
        """Try one structured upsert batch; return an error string on failure."""
        documents = [record.to_document() for record in records]
        try:
            response = client.post(
                "/upsert",
                json={"collection": collection, "documents": documents},
            )
        except Exception as exc:
            return str(exc)

        if 200 <= response.status_code < 300:
            return None

        detail = getattr(response, "text", "") or ""
        if detail:
            return f"HTTP {response.status_code}: {detail}"
        return f"HTTP {response.status_code}"

    def _verify_structured_code_symbol(
        self,
        record: CodeSymbolRecord,
        collection: str,
        client: httpx.Client,
    ) -> str | None:
        """Verify one structured write using a bounded exact-key readback route."""
        try:
            response = client.post(
                "/get",
                json={"collection": collection, "key": record.symbol_id},
            )
        except Exception as exc:
            return f"readback_unavailable:{exc}"

        if response.status_code == 404:
            return "readback_missing"
        if not (200 <= response.status_code < 300):
            detail = getattr(response, "text", "") or ""
            return f"readback_http_{response.status_code}:{detail}" if detail else f"readback_http_{response.status_code}"

        try:
            payload = response.json()
        except Exception as exc:
            return f"readback_invalid_json:{exc}"

        document = payload.get("document") if isinstance(payload, dict) else None
        if document is None and isinstance(payload, dict):
            document = payload.get("item") or payload.get("record") or payload.get("data")
        if not isinstance(document, dict):
            return "readback_missing_document"

        expected = record.to_document()
        checks = {
            "_key": expected["_key"],
            "symbol_id": expected["symbol_id"],
            "symbol_version_id": expected["symbol_version_id"],
            "repo": expected["repo"],
            "repository_id": expected["repository_id"],
            "branch": expected["branch"],
            "path": expected["path"],
            "content_hash": expected["content_hash"],
            "start_line": expected["start_line"],
            "end_line": expected["end_line"],
        }
        for field, expected_value in checks.items():
            if document.get(field) != expected_value:
                return f"readback_mismatch:{field}"
        return None

    def store_legacy_code_symbol(
        self,
        record: CodeSymbolRecord,
        client: httpx.Client | None = None,
    ) -> bool:
        """Store one code symbol through memory's compatibility lesson path."""
        owns_client = client is None
        active_client = client or self._client()
        try:
            document = record.to_legacy_lesson_document()
            response = active_client.post("/store", json={"document": document})
            if 200 <= response.status_code < 300:
                return True

            response = active_client.post("/learn", json=document)
            return 200 <= response.status_code < 300
        except Exception:
            return False
        finally:
            if owns_client:
                active_client.close()

    def add_edges(self, edges: list[dict], batch_size: int = 100) -> MemoryWriteResult:
        """Store graph edges through the memory daemon Unix socket."""
        if not edges:
            return MemoryWriteResult(stored=0, attempted=0, errors=[])

        stored = 0
        errors: list[str] = []
        with self._client() as client:
            for i in range(0, len(edges), batch_size):
                chunk = edges[i : i + batch_size]
                try:
                    response = client.post("/add-edges", json={"edges": chunk}, timeout=60.0)
                    if 200 <= response.status_code < 300:
                        data = response.json()
                        stored += int(data.get("stored", len(chunk)))
                    else:
                        errors.append(f"/add-edges batch {i // batch_size}: HTTP {response.status_code}")
                except Exception as exc:
                    errors.append(f"/add-edges batch {i // batch_size}: {exc}")

        return MemoryWriteResult(stored=stored, attempted=len(edges), errors=errors)
