"""Frame-evidence validation for visual-dependent cards."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from .models import EvidenceCard, FrameEvidence


def content_sha256(content: bytes) -> str:
    """Return the canonical content digest used by frame receipts."""

    return hashlib.sha256(content).hexdigest()


def stable_frame_id(*, source: str, captured_at: datetime, content_sha256: str) -> str:
    """Derive a stable frame id from capture identity and content."""

    canonical = json.dumps(
        {
            "captured_at": captured_at.isoformat(),
            "content_sha256": content_sha256.lower(),
            "source": source,
        },
        sort_keys=True,
    )
    return "frame_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def frame_ref(frame: FrameEvidence) -> str:
    """Bind a card to an exact frame id and image hash."""

    return f"{frame.frame_id}:sha256:{frame.content_sha256}"


@dataclass(frozen=True)
class FrameValidation:
    """Result of validating a card's optional visual evidence dependency."""

    ok: bool
    reason_codes: list[str]
    frame_refs: list[str]


def validate_card_frame_evidence(
    card: EvidenceCard,
    *,
    frames: list[FrameEvidence],
    visual_required: bool,
) -> FrameValidation:
    """Validate that visual cards cite exact frames; audio-only cards pass.

    Timestamp proximity is deliberately ignored. A visual-dependent card must
    carry a `frame_id:sha256:<digest>` reference that resolves to a captured
    frame with the same id and content hash.
    """

    if not visual_required and not card.frame_refs:
        return FrameValidation(ok=True, reason_codes=["audio_only_no_frame_required"], frame_refs=[])

    if visual_required and not card.frame_refs:
        return FrameValidation(ok=False, reason_codes=["visual_card_missing_frame_ref"], frame_refs=[])

    frames_by_ref = {frame_ref(frame): frame for frame in frames}
    unresolved = [ref for ref in card.frame_refs if ref not in frames_by_ref]
    if unresolved:
        return FrameValidation(
            ok=False,
            reason_codes=["unresolved_frame_provenance"],
            frame_refs=list(card.frame_refs),
        )

    if visual_required:
        return FrameValidation(
            ok=True,
            reason_codes=["visual_frame_provenance_resolved"],
            frame_refs=list(card.frame_refs),
        )

    return FrameValidation(
        ok=True,
        reason_codes=["optional_frame_provenance_resolved"],
        frame_refs=list(card.frame_refs),
    )
