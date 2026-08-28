#!/usr/bin/env python3
"""Focused proof for optional first-class frame evidence."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from live_evidence.frame_evidence import (
    content_sha256,
    frame_ref,
    stable_frame_id,
    validate_card_frame_evidence,
)
from live_evidence.models import (
    CardStatus,
    EvidenceCard,
    EvidenceSource,
    FrameChangeReason,
    FrameEvidence,
    FrameRetention,
    Freshness,
    RetrievalLane,
)
from live_evidence.publication import reduce_card_publication


CAPTURED_AT = datetime(2026, 8, 25, 14, 0, 0, tzinfo=timezone.utc)
OUT_DIR = Path(os.environ.get("LIVE_EVIDENCE_FRAME_EVIDENCE_OUT_DIR", "/tmp/live-evidence-frame-evidence-current"))


def build_frame(name: str, content: bytes) -> FrameEvidence:
    digest = content_sha256(content)
    source = "browser-tab:coding-screen"
    return FrameEvidence(
        frame_id=stable_frame_id(source=source, captured_at=CAPTURED_AT, content_sha256=digest),
        captured_at=CAPTURED_AT,
        source=source,
        content_sha256=digest,
        change_reason=FrameChangeReason.VISUAL_CHANGE,
        retention=FrameRetention.SESSION_ONLY,
        path=str(OUT_DIR / f"{name}.png"),
        transcript_event_ids=["event-visual-0001"],
        observations=["diagram shows Redis cache invalidation edge"],
    )


def build_card(frame_refs: list[str] | None = None) -> EvidenceCard:
    source = EvidenceSource(
        lane=RetrievalLane.RIPGREP,
        label="repo evidence",
        excerpt="The invalidation path updates dependent cache keys.",
        score=0.92,
        freshness=Freshness.CURRENT,
        path="/tmp/live-evidence-frame-repo/cache.py",
        repository="frame-proof",
    )
    return EvidenceCard(
        card_id="card-frame-proof-0001",
        query="Which part of the diagram maps to cache invalidation?",
        thread="visual interview",
        question="Which part of this diagram maps to cache invalidation?",
        answer="The invalidation edge maps to dependent cache key updates.",
        talking_point="The invalidation edge maps to dependent cache key updates.",
        proof="repo evidence plus exact screen frame",
        qualifier="Only for the cited frame and repository source.",
        confidence=0.86,
        status=CardStatus.SUPPORTED,
        sources=[source],
        frame_refs=frame_refs or [],
        lanes=[RetrievalLane.RIPGREP],
        question_id="question-visual-0001",
        question_revision=1,
    )


def check(name: str, condition: bool, detail: str = "") -> None:
    if not condition:
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(f"{name}: FAIL{suffix}")
    print(f"{name}: PASS")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    correct = build_frame("correct", b"correct diagram frame")
    nearby = build_frame("nearby", b"nearby irrelevant frame")
    card = build_card([frame_ref(correct)])

    accepted = validate_card_frame_evidence(card, frames=[correct], visual_required=True)
    missing = validate_card_frame_evidence(build_card(), frames=[correct], visual_required=True)
    wrong = validate_card_frame_evidence(card, frames=[nearby], visual_required=True)
    audio_only = validate_card_frame_evidence(build_card(), frames=[], visual_required=False)
    reduction = reduce_card_publication(
        displayed_cards=[],
        incoming=card,
        active_question_id="question-visual-0001",
        active_question_revision=1,
        question_last_revision={"question-visual-0001": 1},
        max_cards=4,
    )

    report = {
        "schema": "live_evidence.frame_evidence_eval.v1",
        "status": "PASS",
        "frame": correct.model_dump(mode="json", by_alias=True),
        "correct_frame_ref": frame_ref(correct),
        "nearby_frame_ref": frame_ref(nearby),
        "visual_accept": accepted.__dict__,
        "visual_missing": missing.__dict__,
        "visual_wrong_frame": wrong.__dict__,
        "audio_only": audio_only.__dict__,
        "publication_decision": reduction.decision.model_dump(mode="json", by_alias=True),
    }

    checks = [
        ("frame event has stable id and hash", correct.frame_id.startswith("frame_") and len(correct.content_sha256) == 64),
        ("frame records source/change/retention", correct.source == "browser-tab:coding-screen" and correct.change_reason is FrameChangeReason.VISUAL_CHANGE and correct.retention is FrameRetention.SESSION_ONLY),
        ("visual card accepts exact frame", accepted.ok and accepted.frame_refs == [frame_ref(correct)]),
        ("visual card holds without frame", not missing.ok and missing.reason_codes == ["visual_card_missing_frame_ref"]),
        ("nearby irrelevant frame rejected", not wrong.ok and wrong.reason_codes == ["unresolved_frame_provenance"]),
        ("audio-only card does not require screenshot", audio_only.ok and audio_only.reason_codes == ["audio_only_no_frame_required"]),
        ("publication receipt carries frame refs", reduction.decision.frame_refs == [frame_ref(correct)]),
    ]
    for name, condition in checks:
        check(name, condition)

    report_path = OUT_DIR / "report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"frame evidence report: {report_path}")
    print("frame evidence: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"frame evidence: FAIL: {exc}", file=sys.stderr)
        raise
