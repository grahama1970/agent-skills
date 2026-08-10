"""Memory daemon client for ingest-code structured writes."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from code_symbol_record import CodeSymbolRecord


load_dotenv(override=False)

MEMORY_SOCKET_PATH = "/run/user/1000/embry/memory.sock"
DEFAULT_CODE_SYMBOLS_BATCH_SIZE = 100
CODE_SYMBOLS_BATCH_SIZE_ENV = "CODE_SYMBOLS_QDRANT_BATCH_SIZE"
CODE_GRAPH_ARTIFACTS = (
    "manifest.json",
    "files.jsonl",
    "symbols.jsonl",
    "edges.jsonl",
    "debug_invocations.jsonl",
    "diagnostics.jsonl",
    "coverage.json",
    "checksums.json",
)


@dataclass(frozen=True)
class MemoryWriteResult:
    stored: int
    attempted: int
    errors: list[str]


@dataclass(frozen=True)
class CodeSymbolWriteResult(MemoryWriteResult):
    stored_records: tuple[CodeSymbolRecord, ...]


@dataclass(frozen=True)
class CodeProjectionApplyResult(MemoryWriteResult):
    receipt: dict[str, Any] | None
    request: dict[str, Any]
    submitted_bundle_digest: str
    checksums_digest: str


def code_graph_bundle_digest(bundle_path: Path) -> str:
    """Return a deterministic digest over the submitted code-graph bundle."""
    hasher = hashlib.sha256()
    for name in CODE_GRAPH_ARTIFACTS:
        artifact = bundle_path / name
        hasher.update(name.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(artifact.read_bytes() if artifact.exists() else b"<missing>")
        hasher.update(b"\0")
    return f"sha256:{hasher.hexdigest()}"


def code_graph_checksums_digest(bundle_path: Path) -> str:
    """Return the digest of checksums.json for the submitted code-graph bundle."""
    return f"sha256:{hashlib.sha256((bundle_path / 'checksums.json').read_bytes()).hexdigest()}"


class CodeMemoryClient:
    """Small Unix-socket client for memory-owned code indexing."""

    def __init__(self, socket_path: str | None = None, timeout: float = 30.0):
        self.socket_path = socket_path or os.environ.get("MEMORY_SOCKET_PATH") or MEMORY_SOCKET_PATH
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

    def apply_code_projection_bundle(
        self,
        *,
        bundle_path: Path,
        scope: str,
        repo: str,
        branch: str,
        root: str,
        source_commit: str,
        expected_counts: dict[str, int],
        idempotency_key: str,
    ) -> CodeProjectionApplyResult:
        """Apply one complete code-graph bundle through Memory/GMO lifecycle authority."""
        bundle_path = bundle_path.resolve()
        submitted_digest = code_graph_bundle_digest(bundle_path)
        checksums_digest = code_graph_checksums_digest(bundle_path)
        request = {
            "bundle_path": str(bundle_path),
            "scope": scope,
            "repo": repo,
            "branch": branch,
            "root": root,
            "source_commit": source_commit,
            "submitted_bundle_digest": submitted_digest,
            "checksums_digest": checksums_digest,
            "expected_counts": expected_counts,
            "idempotency_key": idempotency_key,
        }
        try:
            with self._client() as client:
                response = client.post("/code/projection/apply", json=request)
        except Exception as exc:
            return CodeProjectionApplyResult(
                stored=0,
                attempted=int(expected_counts.get("symbols", 0)),
                errors=[str(exc)],
                receipt=None,
                request=request,
                submitted_bundle_digest=submitted_digest,
                checksums_digest=checksums_digest,
            )

        if not (200 <= response.status_code < 300):
            detail = getattr(response, "text", "") or ""
            error = f"HTTP {response.status_code}: {detail}" if detail else f"HTTP {response.status_code}"
            return CodeProjectionApplyResult(
                stored=0,
                attempted=int(expected_counts.get("symbols", 0)),
                errors=[error],
                receipt=None,
                request=request,
                submitted_bundle_digest=submitted_digest,
                checksums_digest=checksums_digest,
            )

        try:
            receipt = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            return CodeProjectionApplyResult(
                stored=0,
                attempted=int(expected_counts.get("symbols", 0)),
                errors=[f"invalid application receipt JSON: {exc}"],
                receipt=None,
                request=request,
                submitted_bundle_digest=submitted_digest,
                checksums_digest=checksums_digest,
            )

        errors: list[str] = []
        if receipt.get("submitted_bundle_digest") != submitted_digest:
            errors.append("application receipt submitted_bundle_digest mismatch")
        if receipt.get("checksums_digest") != checksums_digest:
            errors.append("application receipt checksums_digest mismatch")
        if not (receipt.get("generation") or {}).get("generation_id"):
            errors.append("application receipt missing generation_id")
        if receipt.get("status") != "applied":
            errors.append(f"application receipt status is not applied: {receipt.get('status')}")

        return CodeProjectionApplyResult(
            stored=0 if errors else int(expected_counts.get("symbols", 0)),
            attempted=int(expected_counts.get("symbols", 0)),
            errors=errors,
            receipt=receipt,
            request=request,
            submitted_bundle_digest=submitted_digest,
            checksums_digest=checksums_digest,
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

    def prune_code_symbols(
        self,
        symbol_ids: list[str],
        collection: str = "code_symbols",
        batch_size: int = 100,
    ) -> MemoryWriteResult:
        """Remove symbols whose source no longer exists.

        Ingestion is otherwise append-only, so a deleted function keeps
        answering recall queries forever. Pruning is a correctness operation,
        not a cleanup nicety.

        Failures are collected rather than raised: a prune that cannot reach
        memory must not fail the ingest that already succeeded, and the
        unpruned ids stay in the state file so the next run retries them.
        """
        if not symbol_ids:
            return MemoryWriteResult(stored=0, attempted=0, errors=[])
        removed = 0
        errors: list[str] = []
        with self._client() as client:
            for start in range(0, len(symbol_ids), max(1, batch_size)):
                batch = symbol_ids[start : start + max(1, batch_size)]
                try:
                    response = client.post(
                        "/delete",
                        json={"collection": collection, "keys": batch},
                    )
                except Exception as exc:
                    errors.append(str(exc))
                    continue
                if 200 <= response.status_code < 300:
                    removed += len(batch)
                    continue
                detail = getattr(response, "text", "") or ""
                errors.append(
                    f"HTTP {response.status_code}: {detail}" if detail else f"HTTP {response.status_code}"
                )
        return MemoryWriteResult(stored=removed, errors=errors)

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
