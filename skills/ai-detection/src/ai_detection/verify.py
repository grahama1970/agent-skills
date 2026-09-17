"""Independent event replay oracle; re-computes state without importing producer edit logic."""
import hashlib
import json

from ai_detection.contracts import EvidenceExport, ReplayVerification
from ai_detection.errors import Code, DetectionError


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def verify_export(export: EvidenceExport) -> dict:
    codepoints: list[str] = []
    previous = _hash(b"")
    event_ids = set()
    last_received = export.created_at
    if export.expires_at <= export.created_at:
        raise DetectionError(Code.INTEGRITY, "Invalid session time interval.")
    for expected_seq, receipt in enumerate(export.events, 1):
        event = receipt.event
        if receipt.session_id != export.session_id or receipt.revision != expected_seq:
            raise DetectionError(Code.INTEGRITY, "Receipt is bound to another session or revision.")
        if event.seq != expected_seq or event.base_revision != expected_seq - 1:
            raise DetectionError(Code.INTEGRITY, "Event sequence is not contiguous.")
        if event.event_id in event_ids or receipt.previous_sha256 != previous:
            raise DetectionError(Code.INTEGRITY, "Duplicate event or broken receipt chain.")
        if not last_received <= receipt.received_at < export.expires_at:
            raise DetectionError(Code.INTEGRITY, "Receipt time falls outside its valid window.")
        event_ids.add(event.event_id)
        if event.start > len(codepoints) or event.start + event.delete_count > len(codepoints):
            raise DetectionError(Code.INTEGRITY, "Invalid Unicode codepoint edit range.")
        codepoints[event.start:event.start + event.delete_count] = list(event.insert_text)
        current_hash = _hash("".join(codepoints).encode("utf-8"))
        if current_hash != event.after_sha256:
            raise DetectionError(Code.INTEGRITY, "Independent source readback disagrees with the receipt.")
        payload = receipt.model_dump(mode="json")
        payload.pop("receipt_sha256")
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                separators=(",", ":"), allow_nan=False).encode("utf-8")
        previous = _hash(serialized)
        if previous != receipt.receipt_sha256:
            raise DetectionError(Code.INTEGRITY, "Receipt digest is invalid.")
        last_received = receipt.received_at
    if export.revision != len(export.events) or export.source != "".join(codepoints):
        raise DetectionError(Code.INTEGRITY, "Final source or revision failed independent readback.")
    if _hash(export.source.encode("utf-8")) != export.source_sha256 or previous != export.head_sha256:
        raise DetectionError(Code.INTEGRITY, "Export head or source digest mismatch.")
    if (export.submitted_at is None) != (export.analysis is None):
        raise DetectionError(Code.INTEGRITY, "Submission and analysis states disagree.")
    if export.submitted_at is not None and not last_received <= export.submitted_at < export.expires_at:
        raise DetectionError(Code.INTEGRITY, "Invalid submission time.")
    if export.analysis and export.analysis.source_sha256 != export.source_sha256:
        raise DetectionError(Code.INTEGRITY, "Analysis was bound to another revision.")
    return ReplayVerification.model_validate({"schema_version": "ai_detection.replay_verification.v1", "status": "PASS",
            "session_id": export.session_id, "event_count": len(export.events),
            "source_sha256": export.source_sha256, "head_sha256": export.head_sha256,
            "proves": "Internal receipt consistency and reconstructed server-received source.",
            "does_not_prove": "Human authorship, complete client history, or resistance to a database owner's rewrite."}).model_dump(mode="json")
