"""Memory daemon client for ingest-code structured writes."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from code_symbol_record import CodeSymbolRecord


MEMORY_SOCKET_PATH = "/run/user/1000/embry/memory.sock"


@dataclass(frozen=True)
class MemoryWriteResult:
    stored: int
    attempted: int
    errors: list[str]


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
        batch_size: int = 100,
    ) -> MemoryWriteResult:
        """Upsert structured code symbols, falling back to legacy lessons per record."""
        if not records:
            return MemoryWriteResult(stored=0, attempted=0, errors=[])

        stored = 0
        errors: list[str] = []
        with self._client() as client:
            for i in range(0, len(records), batch_size):
                batch = records[i : i + batch_size]
                documents = [record.to_document() for record in batch]
                try:
                    response = client.post(
                        "/upsert",
                        json={"collection": collection, "documents": documents},
                    )
                    if 200 <= response.status_code < 300:
                        stored += len(batch)
                        continue
                    errors.append(f"/upsert batch {i // batch_size}: HTTP {response.status_code}")
                except Exception as exc:
                    errors.append(f"/upsert batch {i // batch_size}: {exc}")

                for record in batch:
                    if self.store_legacy_code_symbol(record, client=client):
                        stored += 1
                    else:
                        errors.append(f"legacy fallback failed: {record.qualified_name}")

        return MemoryWriteResult(stored=stored, attempted=len(records), errors=errors)

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
