#!/usr/bin/env python3
"""Deterministic proof for the post-interview review dossier (#1451).

Runs against the committed time-coded fixture journal
fixtures/review_interview_journal.jsonl (two questions, one revised question,
one supported claim, one unverified candidate assertion, one contradicted
claim, one reviewer annotation) and proves, from readbacks:

1. exact event/timestamp binding for every question and answer span;
2. deterministic bundle digest (same inputs -> same digest, twice);
3. a claim cannot be LABELED supported without evidence (fail-closed);
4. a candidate assertion is never silently promoted;
5. no cross-question / obsolete-revision attribution;
6. annotations are append-only, attributable, and do not change the
   evidence digest; a mutated transcript is rejected on readback.

This proof is deterministic BY DESIGN (the ticket's "required deterministic
proof" rung); the live/browser rung is a separate, explicitly deferred case.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{name}: {'PASS' if ok else 'FAIL'}{f' ({detail})' if detail else ''}")
    if not ok:
        FAILURES.append(name)


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))

    from live_evidence.review import (
        MediaRetention,
        ReviewClaim,
        ReviewDisposition,
        ReviewerAnnotation,
        append_annotation,
        build_review_bundle,
        verify_bundle,
    )

    journal = root / "fixtures" / "review_interview_journal.jsonl"
    fixed_time = datetime(2026, 8, 14, 18, 0, 0, tzinfo=timezone.utc)
    policy_digest = "0" * 64
    media_sha = "1" * 64

    question_specs = [
        {"question_id": "q-linkedlist", "question_revision": 0, "event_ids": ["ev-q1-a"],
         "text": "Can you walk me through how you would reverse a linked list in place"},
        {"question_id": "q-linkedlist", "question_revision": 1, "event_ids": ["ev-q1-a", "ev-q1-b"],
         "text": "Reverse a linked list recursively"},
        {"question_id": "q-complexity", "question_revision": 0, "event_ids": ["ev-q2"],
         "text": "What is the time complexity of your solution"},
    ]
    span_specs = [
        {"span_id": "span-recursive-answer", "question_id": "q-linkedlist", "question_revision": 1,
         "event_ids": ["ev-a1-a", "ev-a1-b"]},
        {"span_id": "span-scale-assertion", "question_id": "q-linkedlist", "question_revision": 1,
         "event_ids": ["ev-claim-emp"]},
        {"span_id": "span-complexity-answer", "question_id": "q-complexity", "question_revision": 0,
         "event_ids": ["ev-a2"]},
    ]
    claims = [
        ReviewClaim(
            claim_id="claim-recursion-supported",
            text="Candidate described a correct recursive reversal including the base case.",
            disposition=ReviewDisposition.SUPPORTED_BY_INTERVIEW,
            span_ids=["span-recursive-answer"],
        ),
        ReviewClaim(
            claim_id="claim-scale-unverified",
            text="Candidate states they handled 200M requests/day at their last employer.",
            disposition=ReviewDisposition.CANDIDATE_ASSERTION_UNVERIFIED,
            span_ids=["span-scale-assertion"],
        ),
        ReviewClaim(
            claim_id="claim-complexity-contradicted",
            text="Candidate's constant-time claim contradicts their own recursive O(n) description.",
            disposition=ReviewDisposition.CONTRADICTED,
            span_ids=["span-complexity-answer", "span-recursive-answer"],
        ),
    ]

    def build(**overrides):
        kwargs = dict(
            session_id="fixture-session-1451",
            session_policy_digest=policy_digest,
            media_id="fixture-interview-recording",
            media_locator="file:///fixtures/review-interview.mkv",
            media_retention=MediaRetention.RETAINED_LOCAL,
            media_sha256=media_sha,
            question_specs=question_specs,
            span_specs=span_specs,
            claims=claims,
            created_at=fixed_time,
            review_id="review-fixture-1451",
        )
        kwargs.update(overrides)
        return build_review_bundle(journal, **kwargs)

    bundle = build()

    # 1. exact event/timestamp binding, read back from the fixture journal.
    span = {s.span_id: s for s in bundle.answer_spans}["span-recursive-answer"]
    check(
        "answer span binds exact events and media timestamps",
        span.event_ids == ["ev-a1-a", "ev-a1-b"]
        and span.sequence_start == 3 and span.sequence_end == 4
        and span.start_s == 17.0 and span.end_s == 30.0,
        f"events={span.event_ids} seq={span.sequence_start}-{span.sequence_end} t={span.start_s}-{span.end_s}s",
    )
    revised = [q for q in bundle.questions if q.question_id == "q-linkedlist"]
    check(
        "revised question kept distinct from original wording",
        len(revised) == 2 and {q.question_revision for q in revised} == {0, 1},
        f"revisions={sorted(q.question_revision for q in revised)}",
    )

    # 2. deterministic digest: independent second build, identical digest.
    digest_a = bundle.bundle_digest()
    digest_b = build().bundle_digest()
    check("bundle digest deterministic across independent builds", digest_a == digest_b, digest_a[:16])

    # 3. supported label without evidence is rejected at the type layer.
    try:
        ReviewClaim(text="x" * 10, disposition=ReviewDisposition.SUPPORTED_BY_INTERVIEW, span_ids=[])
        check("supported claim without spans rejected", False, "validator accepted it")
    except Exception as exc:
        check("supported claim without spans rejected", "answer span" in str(exc))
    try:
        ReviewClaim(
            text="x" * 10,
            disposition=ReviewDisposition.SUPPORTED_BY_AUTHORIZED_ARTIFACT,
            artifact_refs=[],
        )
        check("artifact-supported claim without artifact rejected", False, "validator accepted it")
    except Exception as exc:
        check("artifact-supported claim without artifact rejected", "artifact" in str(exc))

    # 4. candidate assertion is not silently promoted: it never appears in the
    # evidence-bearing TL;DR, while the supported claim does.
    tldr_ids = {b["text"] for b in bundle.tldr()}
    check(
        "tldr carries only evidence-bearing claims",
        any("recursive" in t for t in tldr_ids)
        and not any("200M" in t for t in tldr_ids),
        f"bullets={len(tldr_ids)}",
    )
    check(
        "every tldr bullet carries exact references",
        all(b["span_ids"] or b["artifact_refs"] for b in bundle.tldr()),
    )

    # 5. cross-question / obsolete-revision attribution rejected.
    try:
        build(span_specs=[{"span_id": "bad-span-revision", "question_id": "q-linkedlist",
                           "question_revision": 7, "event_ids": ["ev-a1-a"]}],
              claims=[])
        check("span bound to obsolete/unknown revision rejected", False, "accepted")
    except Exception as exc:
        check("span bound to obsolete/unknown revision rejected", "not in this bundle" in str(exc))
    try:
        build(span_specs=span_specs[:1],
              claims=[claims[2]])
        check("claim binding unknown span rejected", False, "accepted")
    except Exception as exc:
        check("claim binding unknown span rejected", "unknown span" in str(exc))

    # 6. append-only annotation: attributable, digest-stable, unknown claim refused.
    annotated = append_annotation(
        bundle,
        ReviewerAnnotation(actor="reviewer:graham", note="Verify the 200M/day figure before onsite.",
                           claim_id="claim-scale-unverified"),
    )
    check(
        "annotation appended and attributable without touching evidence digest",
        len(annotated.reviewer_annotations) == 1
        and annotated.reviewer_annotations[0].actor == "reviewer:graham"
        and annotated.bundle_digest() == digest_a,
    )
    try:
        append_annotation(bundle, ReviewerAnnotation(actor="a", note="n", claim_id="claim-missing-1"))
        check("annotation on unknown claim rejected", False, "accepted")
    except Exception as exc:
        check("annotation on unknown claim rejected", "unknown claim" in str(exc))

    # Mutated transcript rejected on readback.
    readback = verify_bundle(bundle, journal)
    check("unmutated journal verifies", readback["ok"] is True)
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as handle:
        rows = [json.loads(line) for line in journal.read_text().splitlines() if line.strip()]
        rows[2]["payload"]["text"] = "tampered answer"
        handle.write("\n".join(json.dumps(r) for r in rows))
        tampered = Path(handle.name)
    mutated = verify_bundle(bundle, tampered)
    tampered.unlink()
    check("mutated transcript rejected on readback", mutated["transcript_digest_ok"] is False)

    print()
    if FAILURES:
        print(f"review dossier: FAIL ({len(FAILURES)} failed: {', '.join(FAILURES)})")
        return 1
    print("review dossier: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
