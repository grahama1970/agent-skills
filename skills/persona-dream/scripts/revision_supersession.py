#!/usr/bin/env python3
"""Sanctioned supersession for re-qualifying a rebuilt-index Persona Dream revision.

When a revision's artifact index is rebuilt (for example, to fold regenerated
storyboard frames into the same immutable revision id), the qualification chain
must be re-run against the *same* revision id with a *changed* index. Three
fail-closed guards deliberately block that re-run:

  (a) the Memory active-revision pointer already targets this revision with the
      old evidence hashes (``BLOCKED_MEMORY_ACTIVE_POINTER_MISMATCH``);
  (b) the immutable queue terminal event embeds the old index hash
      (``BLOCKED_ACTIVATION_IMMUTABLE_FILE_CONFLICT``);
  (c) the immutable prepare/verify/activation receipts embed the old index hash
      (``BLOCKED_MEMORY_*_RECEIPT_*`` / ``BLOCKED_ACTIVATION_IMMUTABLE_FILE_CONFLICT``).

Historically these were worked around by hand-deleting the pointer document, the
terminal event, and the receipts. Deletion is an un-sanctioned third category:
GOAL.md requires superseded records to be *marked stale/superseded and retained*,
never silently reused and never silently dropped.

This module implements the sanctioned alternative. It never deletes evidentiary
content. For a genuine same-revision index rebuild it:

  1. archives each stale predecessor receipt / terminal event byte-for-byte under
     ``<revision_root>/superseded/<old_index_prefix>/`` (retained, readable);
  2. writes a durable ``pd_active_..__superseded__<old_index_prefix>`` snapshot of
     the old Memory active pointer, marked ``lifecycle_state = SUPERSEDED`` (the
     old pointer content is retained in Memory, not dropped);
  3. appends an old-hash -> new-hash entry to an append-only supersession ledger
     and writes a supersession receipt;
  4. vacates the canonical file slots so the standard prepare/verify/activate
     chain can re-run and write fresh artifacts.

It fails closed for every case that is *not* a clean same-revision index rebuild:
a changed revision id / source revision / human idea, a changed provider
invariant, or an unchanged index (nothing to supersede) all refuse to touch
anything. ``activate --supersede`` then accepts the properly-superseded
predecessor pointer (and only that one) when it overwrites the canonical pointer.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from prepare_revision_qualification import (
    DEFAULT_COLLECTION,
    DEFAULT_MEMORY_URL,
    GateBlocked,
    MemoryClient,
    load_snapshot,
    read_object,
    sha256_file,
    sha256_json,
    validate_upsert_result,
)

SUPERSEDE_LEDGER_NAME = "revision_requalification_supersession_ledger.v1.json"
SUPERSEDE_RECEIPT_NAME = "revision_requalification_supersession_receipt.v1.json"
SUPERSEDED_DIRNAME = "superseded"

PREPARE_RECEIPT_NAME = "revision_memory_prepare_receipt.json"
VERIFY_RECEIPT_NAME = "revision_memory_verify_receipt.json"
ACTIVATION_RECEIPT_NAME = "revision_activation_receipt.json"
QUEUE_EVENT_NAME = "000001-completed.json"

PROVIDER_INVARIANT = {
    "provider_live": False,
    "paid_call_authorized": False,
    "submitted": False,
    "actual_provider_call_attempts": 0,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Predecessor identity + index extraction
# ---------------------------------------------------------------------------


def receipt_index_sha(doc: Mapping[str, Any]) -> str | None:
    value = doc.get("artifact_index_sha256")
    return str(value) if isinstance(value, str) and value else None


def activation_index_sha(doc: Mapping[str, Any]) -> str | None:
    local = doc.get("local_files")
    if isinstance(local, Mapping):
        entry = local.get("artifact_index")
        if isinstance(entry, Mapping) and isinstance(entry.get("sha256"), str):
            return str(entry["sha256"])
    return None


def old_index_prefix(old_index_sha256: str) -> str:
    return old_index_sha256.removeprefix("sha256:")[:16]


def assert_same_revision_identity(doc: Mapping[str, Any], snapshot: Any, *, label: str) -> None:
    """Refuse supersession unless only the index changed on the same revision."""
    checks = {
        "run_id": snapshot.run_id,
        "revision_id": snapshot.revision_id,
        "source_revision_id": snapshot.source_revision_id,
    }
    for field, expected in checks.items():
        observed = doc.get(field)
        if observed is not None and observed != expected:
            raise GateBlocked(
                "BLOCKED_SUPERSEDE_IDENTITY_CHANGED",
                details={"artifact": label, "field": field, "expected": expected, "observed": observed},
            )


def assert_provider_invariant(doc: Mapping[str, Any], *, label: str) -> None:
    for field, expected in PROVIDER_INVARIANT.items():
        if field in doc and doc.get(field) != expected:
            raise GateBlocked(
                "BLOCKED_SUPERSEDE_PROVIDER_INVARIANT",
                details={"artifact": label, "field": field, "expected": expected, "observed": doc.get(field)},
            )


# ---------------------------------------------------------------------------
# Ledger (append-only)
# ---------------------------------------------------------------------------


def read_ledger(revision_root: Path) -> dict[str, Any]:
    path = revision_root / SUPERSEDE_LEDGER_NAME
    if not path.is_file():
        return {
            "schema": "persona_dream.revision_requalification_supersession_ledger.v1",
            "run_id": None,
            "revision_id": None,
            "entries": [],
        }
    value = read_object(path)
    if not isinstance(value.get("entries"), list):
        raise GateBlocked("BLOCKED_SUPERSEDE_LEDGER_INVALID", details={"path": str(path)})
    return value


def write_ledger(revision_root: Path, ledger: Mapping[str, Any]) -> Path:
    path = revision_root / SUPERSEDE_LEDGER_NAME
    path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def ledger_authorizes(
    revision_root: Path,
    *,
    old_index_sha256: str,
    new_index_sha256: str,
) -> bool:
    """True iff the ledger records this exact old -> new index supersession."""
    ledger = read_ledger(revision_root)
    for entry in ledger.get("entries", []):
        if (
            isinstance(entry, Mapping)
            and entry.get("old_artifact_index_sha256") == old_index_sha256
            and entry.get("new_artifact_index_sha256") == new_index_sha256
        ):
            return True
    return False


# ---------------------------------------------------------------------------
# File archival (retain, never delete)
# ---------------------------------------------------------------------------


def archive_file(canonical: Path, revision_root: Path, *, prefix: str) -> dict[str, Any]:
    """Copy the stale canonical file under superseded/<prefix>/, then vacate the slot.

    The bytes are retained (readable) at the archive path and referenced by hash.
    Vacating the canonical slot is a *move-with-retention*, categorically distinct
    from deletion: the content is preserved and receipted, never dropped.
    """
    old_sha256 = sha256_file(canonical)
    rel = canonical.relative_to(revision_root)
    archive_root = revision_root / SUPERSEDED_DIRNAME / prefix
    archive_path = archive_root / rel
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if archive_path.exists():
        if sha256_file(archive_path) != old_sha256:
            raise GateBlocked(
                "BLOCKED_SUPERSEDE_ARCHIVE_CONFLICT",
                details={"archive_path": str(archive_path)},
            )
    else:
        shutil.copy2(canonical, archive_path)
    canonical.unlink()
    return {
        "canonical_relative_path": rel.as_posix(),
        "archived_relative_path": archive_path.relative_to(revision_root).as_posix(),
        "old_sha256": old_sha256,
    }


# ---------------------------------------------------------------------------
# Memory active-pointer snapshot (retain the old pointer, marked SUPERSEDED)
# ---------------------------------------------------------------------------


def superseded_pointer_key(active_key: str, old_index_sha256: str) -> str:
    return f"{active_key}__superseded__{old_index_prefix(old_index_sha256)}"


def build_superseded_pointer(
    old_pointer: Mapping[str, Any],
    *,
    superseded_key: str,
    new_index_sha256: str,
    superseded_at: str,
) -> dict[str, Any]:
    server_owned = {
        "_id",
        "_rev",
        "qdrant_collection",
        "qdrant_point_id",
        "embedding_model",
        "embedding_version",
        "text_hash",
        "semantic_sync_state",
        "semantic_sync_error",
        "document_contract_sha256",
    }
    doc = {k: v for k, v in old_pointer.items() if k not in server_owned}
    doc["_key"] = superseded_key
    doc["record_type"] = "active_revision_pointer_superseded"
    doc["lifecycle_state"] = "SUPERSEDED"
    doc["superseded_at"] = superseded_at
    doc["superseded_by_artifact_index_sha256"] = new_index_sha256
    doc["superseded_from_artifact_index_sha256"] = str(old_pointer.get("artifact_index_sha256") or "")
    doc["retrieval_text"] = (
        "Superseded Persona Dream active-revision pointer for run "
        f"{old_pointer.get('run_id')} revision {old_pointer.get('active_revision_id')}: "
        f"index {old_pointer.get('artifact_index_sha256')} superseded by {new_index_sha256}. "
        "Retained for audit; never reused as the active pointer."
    )
    doc["document_contract_sha256"] = sha256_json({k: v for k, v in doc.items() if k != "document_contract_sha256"})
    return doc


def snapshot_active_pointer(
    client: MemoryClient,
    collection: str,
    *,
    active_key: str,
    snapshot: Any,
    new_index_sha256: str,
    superseded_at: str,
) -> dict[str, Any] | None:
    """Retain the current active pointer as a SUPERSEDED snapshot if it is stale.

    Returns snapshot info, or None when there is nothing to supersede (no pointer,
    or the pointer already carries the new index).
    """
    payload = {
        "collection": collection,
        "limit": 2,
        "offset": 0,
        "sort_field": "_key",
        "sort_order": "ASC",
        "filters": {"_key": active_key},
    }
    evidence = client.post("/list", payload)
    documents = evidence.response.get("documents")
    if not isinstance(documents, list):
        raise GateBlocked("BLOCKED_SUPERSEDE_POINTER_LIST_INVALID", exit_code=4)
    if not documents:
        return None
    old_pointer = documents[0]
    if str(old_pointer.get("active_revision_id") or "") != snapshot.revision_id:
        raise GateBlocked(
            "BLOCKED_SUPERSEDE_POINTER_IDENTITY",
            details={
                "expected_revision_id": snapshot.revision_id,
                "observed_active_revision_id": old_pointer.get("active_revision_id"),
            },
        )
    old_index = str(old_pointer.get("artifact_index_sha256") or "")
    if old_index == new_index_sha256:
        return None
    assert_same_revision_identity(old_pointer, snapshot, label="active_pointer")
    assert_provider_invariant(old_pointer, label="active_pointer")

    superseded_key = superseded_pointer_key(active_key, old_index)
    superseded_doc = build_superseded_pointer(
        old_pointer,
        superseded_key=superseded_key,
        new_index_sha256=new_index_sha256,
        superseded_at=superseded_at,
    )
    upsert = client.post("/upsert", {"collection": collection, "documents": [superseded_doc]})
    validate_upsert_result(upsert, 1)
    return {
        "superseded_pointer_key": superseded_key,
        "old_artifact_index_sha256": old_index,
        "old_activation_transaction_id": str(old_pointer.get("activation_transaction_id") or ""),
    }


# ---------------------------------------------------------------------------
# Supersession transaction
# ---------------------------------------------------------------------------


FILE_SPECS: tuple[tuple[str, str, Callable[[Mapping[str, Any]], str | None]], ...] = (
    ("prepare_receipt", PREPARE_RECEIPT_NAME, receipt_index_sha),
    ("verify_receipt", VERIFY_RECEIPT_NAME, receipt_index_sha),
    ("activation_receipt", ACTIVATION_RECEIPT_NAME, activation_index_sha),
)


def terminal_event_path(snapshot: Any) -> Path | None:
    """Locate the successor's queue terminal event via the (stale) activation receipt."""
    receipt_path = snapshot.revision_root / ACTIVATION_RECEIPT_NAME
    if not receipt_path.is_file():
        return None
    doc = read_object(receipt_path)
    ref = (doc.get("local_files") or {}).get("queue_terminal_event")
    if not isinstance(ref, Mapping) or not ref.get("relative_path"):
        return None
    return snapshot.run_root / str(ref["relative_path"])


def supersede(args: argparse.Namespace) -> dict[str, Any]:
    snapshot = load_snapshot(args.run_root, args.revision_id, args.source_commit)
    new_index_sha256 = snapshot.index_sha256
    superseded_at = args.superseded_at or utc_now()

    archived: list[dict[str, Any]] = []
    old_index_seen: set[str] = set()

    # Locate the terminal event before we vacate the activation receipt that points to it.
    event_path = terminal_event_path(snapshot)

    for label, name, extractor in FILE_SPECS:
        canonical = snapshot.revision_root / name
        if not canonical.is_file():
            continue
        doc = read_object(canonical)
        assert_same_revision_identity(doc, snapshot, label=label)
        assert_provider_invariant(doc, label=label)
        bound_index = extractor(doc)
        if bound_index is None:
            raise GateBlocked("BLOCKED_SUPERSEDE_INDEX_UNREADABLE", details={"artifact": label})
        if bound_index == new_index_sha256:
            # Already current for this rebuilt index; nothing to supersede here.
            continue
        old_index_seen.add(bound_index)
        entry = archive_file(canonical, snapshot.revision_root, prefix=old_index_prefix(bound_index))
        entry["artifact"] = label
        entry["bound_artifact_index_sha256"] = bound_index
        archived.append(entry)

    if event_path is not None and event_path.is_file():
        doc = read_object(event_path)
        assert_same_revision_identity(doc, snapshot, label="queue_terminal_event")
        assert_provider_invariant(doc, label="queue_terminal_event")
        bound_index = receipt_index_sha(doc)
        if bound_index is not None and bound_index != new_index_sha256:
            old_index_seen.add(bound_index)
            # Terminal event lives under run_root, not revision_root; archive under
            # the revision's superseded/ tree keyed by its run-relative path.
            old_sha256 = sha256_file(event_path)
            rel = event_path.relative_to(snapshot.run_root)
            archive_path = snapshot.revision_root / SUPERSEDED_DIRNAME / old_index_prefix(bound_index) / "run_root" / rel
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            if archive_path.exists():
                if sha256_file(archive_path) != old_sha256:
                    raise GateBlocked("BLOCKED_SUPERSEDE_ARCHIVE_CONFLICT", details={"archive_path": str(archive_path)})
            else:
                shutil.copy2(event_path, archive_path)
            event_path.unlink()
            archived.append(
                {
                    "artifact": "queue_terminal_event",
                    "canonical_relative_path": rel.as_posix(),
                    "archived_relative_path": archive_path.relative_to(snapshot.revision_root).as_posix(),
                    "old_sha256": old_sha256,
                    "bound_artifact_index_sha256": bound_index,
                }
            )

    pointer_snapshot: dict[str, Any] | None = None
    with MemoryClient(
        args.memory_url,
        connect_timeout=args.connect_timeout,
        read_timeout=args.read_timeout,
    ) as client:
        from activate_revision_qualification import active_pointer_key

        active_key = active_pointer_key(snapshot.run_id)
        pointer_snapshot = snapshot_active_pointer(
            client,
            args.collection,
            active_key=active_key,
            snapshot=snapshot,
            new_index_sha256=new_index_sha256,
            superseded_at=superseded_at,
        )
        if pointer_snapshot is not None:
            old_index_seen.add(pointer_snapshot["old_artifact_index_sha256"])

    if not archived and pointer_snapshot is None:
        raise GateBlocked(
            "BLOCKED_SUPERSEDE_NOTHING_STALE",
            details={
                "reason": "no predecessor artifact bound to a different index was found; "
                "the canonical state already matches the rebuilt index or no predecessor exists",
                "new_artifact_index_sha256": new_index_sha256,
            },
        )
    if len(old_index_seen) > 1:
        raise GateBlocked(
            "BLOCKED_SUPERSEDE_INCONSISTENT_PREDECESSOR",
            details={"old_index_shas": sorted(old_index_seen)},
        )
    old_index_sha256 = next(iter(old_index_seen))

    ledger = read_ledger(snapshot.revision_root)
    ledger["run_id"] = snapshot.run_id
    ledger["revision_id"] = snapshot.revision_id
    entry = {
        "old_artifact_index_sha256": old_index_sha256,
        "new_artifact_index_sha256": new_index_sha256,
        "superseded_at": superseded_at,
        "source_commit": snapshot.source_commit,
        "archived_files": archived,
        "superseded_active_pointer": pointer_snapshot,
        "rule": "old records retained under superseded/ and as a SUPERSEDED Memory snapshot; never reused, never deleted",
    }
    ledger["entries"] = [*ledger.get("entries", []), entry]
    ledger_path = write_ledger(snapshot.revision_root, ledger)

    receipt = {
        "schema": "persona_dream.revision_requalification_supersession_receipt.v1",
        "status": "PASS_REQUALIFICATION_SUPERSEDED",
        "run_id": snapshot.run_id,
        "revision_id": snapshot.revision_id,
        "source_revision_id": snapshot.source_revision_id,
        "source_commit": snapshot.source_commit,
        "old_artifact_index_sha256": old_index_sha256,
        "new_artifact_index_sha256": new_index_sha256,
        "superseded_at": superseded_at,
        "archived_files": archived,
        "superseded_active_pointer": pointer_snapshot,
        "supersession_ledger": SUPERSEDE_LEDGER_NAME,
        "supersession_ledger_sha256": sha256_file(ledger_path),
        "claims": {
            "proves": [
                "every stale predecessor receipt and terminal event was retained under superseded/ and referenced by hash before its canonical slot was vacated",
                "the old Memory active pointer was retained as a SUPERSEDED snapshot, not dropped",
                "an old->new artifact-index supersession entry was appended to the append-only ledger",
            ],
            "does_not_prove": [
                "the fresh prepare/verify/activation receipts (written by the standard chain after supersession)",
                "provider readiness, publication, payment, or submission",
            ],
        },
        "provider_live": False,
        "paid_call_authorized": False,
        "submitted": False,
        "actual_provider_call_attempts": 0,
    }
    receipt_path = snapshot.revision_root / SUPERSEDE_RECEIPT_NAME
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt["receipt_path"] = str(receipt_path)
    return receipt


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--run-root", type=Path, required=True)
    value.add_argument("--revision-id", required=True)
    value.add_argument("--source-commit", required=True)
    value.add_argument("--superseded-at", help="ISO-8601 timestamp for deterministic replay")
    value.add_argument("--memory-url", default=DEFAULT_MEMORY_URL)
    value.add_argument("--collection", default=DEFAULT_COLLECTION)
    value.add_argument("--connect-timeout", type=float, default=5.0)
    value.add_argument("--read-timeout", type=float, default=60.0)
    return value


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = supersede(args)
    except GateBlocked as exc:
        output = {
            "status": exc.code,
            "gate": "revision-requalification-supersession",
            "details": exc.details,
        }
        print(json.dumps(output, indent=2, sort_keys=True))
        return exc.exit_code
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
