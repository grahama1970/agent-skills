"""Crash-safe immutable receipt persistence for Battle attempts."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any

SCHEMA = "battle.receipt_store_attempt.v1"


class InjectedTermination(RuntimeError):
    pass


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}-{uuid.uuid4().hex}")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _safe_component(name: str, value: str) -> str:
    if not isinstance(value, str) or not value or value in {".", ".."}:
        raise ValueError(f"{name} must be a safe path component")
    separators = {os.sep}
    if os.altsep:
        separators.add(os.altsep)
    if any(separator in value for separator in separators):
        raise ValueError(f"{name} must be a safe path component")
    return value


class ReceiptStore:
    """Immutable attempts + content-addressed artifacts.

    Attempts are addressed by caller-provided run_id/attempt_id/event_id. A
    committed event is idempotent if retried byte-for-byte. Partial attempts are
    left as INCOMPLETE and never promoted to success by recovery.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.blobs = self.root / "blobs" / "sha256"
        self.attempts = self.root / "attempts"

    def _maybe_kill(self, failpoint: str | None, point: str) -> None:
        if failpoint == point:
            raise InjectedTermination(point)

    def commit(
        self,
        *,
        run_id: str,
        attempt_id: str,
        event_id: str,
        receipt: dict[str, Any],
        artifacts: dict[str, str | Path] | None = None,
        failpoint: str | None = None,
    ) -> dict[str, Any]:
        run_id = _safe_component("run_id", run_id)
        attempt_id = _safe_component("attempt_id", attempt_id)
        event_id = _safe_component("event_id", event_id)
        attempt_dir = self.attempts / run_id / attempt_id / event_id
        final = attempt_dir / "attempt.json"
        receipt_bytes = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
        receipt_digest = _sha256_bytes(receipt_bytes)
        if final.exists():
            existing = json.loads(final.read_text(encoding="utf-8"))
            if existing.get("receipt_sha256") == receipt_digest:
                return existing
            raise FileExistsError(f"event already committed with different receipt: {run_id}/{attempt_id}/{event_id}")

        incomplete = {
            "schema": SCHEMA,
            "run_id": run_id,
            "attempt_id": attempt_id,
            "event_id": event_id,
            "status": "INCOMPLETE",
            "receipt_sha256": receipt_digest,
            "artifacts": [],
        }
        _atomic_write(attempt_dir / "incomplete.json", json.dumps(incomplete, indent=2, sort_keys=True).encode() + b"\n")
        self._maybe_kill(failpoint, "after_incomplete")

        artifact_entries = []
        for name, raw in sorted((artifacts or {}).items()):
            src = Path(raw)
            data = src.read_bytes()
            digest = _sha256_bytes(data)
            blob = self.blobs / digest.split(":", 1)[1]
            if not blob.exists():
                _atomic_write(blob, data)
            artifact_entries.append({"name": name, "sha256": digest, "bytes": len(data), "blob": str(blob.relative_to(self.root))})
        self._maybe_kill(failpoint, "after_artifacts")

        receipt_blob = self.blobs / receipt_digest.split(":", 1)[1]
        if not receipt_blob.exists():
            _atomic_write(receipt_blob, receipt_bytes)
        self._maybe_kill(failpoint, "after_receipt_blob")

        committed = dict(incomplete)
        committed.update({
            "status": "COMMITTED",
            "receipt_blob": str(receipt_blob.relative_to(self.root)),
            "artifacts": artifact_entries,
        })
        _atomic_write(final, json.dumps(committed, indent=2, sort_keys=True).encode() + b"\n")
        try:
            (attempt_dir / "incomplete.json").unlink()
        except FileNotFoundError:
            pass
        return committed

    def recover(self) -> list[dict[str, Any]]:
        recovered = []
        for marker in self.attempts.glob("*/*/*/incomplete.json"):
            payload = json.loads(marker.read_text(encoding="utf-8"))
            final = marker.with_name("attempt.json")
            if final.exists():
                payload = json.loads(final.read_text(encoding="utf-8"))
            else:
                payload["status"] = "INCOMPLETE"
                _atomic_write(marker, json.dumps(payload, indent=2, sort_keys=True).encode() + b"\n")
            recovered.append(payload)
        return recovered


def commit_receipt(
    root: str | Path,
    *,
    run_id: str,
    attempt_id: str,
    event_id: str,
    receipt: dict[str, Any],
    artifacts: dict[str, str | Path] | None = None,
    failpoint: str | None = None,
) -> dict[str, Any]:
    return ReceiptStore(root).commit(
        run_id=run_id,
        attempt_id=attempt_id,
        event_id=event_id,
        receipt=receipt,
        artifacts=artifacts,
        failpoint=failpoint,
    )
