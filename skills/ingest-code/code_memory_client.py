"""Memory daemon client for ingest-code structured writes."""

from __future__ import annotations

from dataclasses import dataclass
import os

import httpx

from code_symbol_record import CodeSymbolRecord


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
    stored_records: tuple[CodeSymbolRecord, ...]


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
        """Upsert structured code symbols, falling back to legacy lessons per record.

        Failed multi-record upsert batches are split before using the legacy
        path. A parent batch failure is treated as recoverable when every
        descendant record stores successfully.
        """
        if not records:
            return CodeSymbolWriteResult(stored=0, attempted=0, errors=[], stored_records=())

        effective_batch_size = self._resolve_batch_size(batch_size)
        stored_records: list[CodeSymbolRecord] = []
        errors: list[str] = []

        def store_batch(batch: list[CodeSymbolRecord], client: httpx.Client) -> None:
            upsert_error = self._upsert_batch(batch, collection=collection, client=client)
            if upsert_error is None:
                stored_records.extend(batch)
                return

            if len(batch) > 1:
                midpoint = len(batch) // 2
                store_batch(batch[:midpoint], client)
                store_batch(batch[midpoint:], client)
                return

            record = batch[0]
            if self.store_legacy_code_symbol(record, client=client):
                stored_records.append(record)
                return

            errors.append(
                f"upsert and legacy fallback failed for {record.qualified_name}: "
                f"upsert={upsert_error}; legacy=fallback failed"
            )

        with self._client() as client:
            for i in range(0, len(records), effective_batch_size):
                store_batch(records[i : i + effective_batch_size], client)

        return CodeSymbolWriteResult(
            stored=len(stored_records),
            attempted=len(records),
            errors=errors,
            stored_records=tuple(stored_records),
        )

    def _resolve_batch_size(self, requested: int | None) -> int:
        """Resolve the per-call upsert batch size defensively."""
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
