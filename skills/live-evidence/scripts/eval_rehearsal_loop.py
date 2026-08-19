#!/usr/bin/env python3
"""Deterministic proof for the practice-only rehearsal loop (#1453).

Ten required scenarios. The Chatterbox transport here is a contract-shaped
injection (deterministic by design, per the ticket's required deterministic
proof); the LIVE voice rung is exercised separately by eval_voice_interruption
(real chatterbox TTS + real human barge-in audio).

1.  rehearsal+voice policy admits the loop; formal_assessment is refused;
2.  exact text/hash binding between selection and render receipt;
3.  stale question revision suppresses old audio;
4.  pre-cancelled turn emits zero accepted bytes;
5.  interruption then a corrected turn duplicates no state;
6.  malformed/mismatched Chatterbox receipt fails closed;
7.  practice/formal storage separation with explicit promotion only;
8.  follow-up selection must cite an open rubric criterion, one per answer;
9.  slow critique for an old revision discarded by the fence;
10. Chatterbox cannot inject unrequested spoken text.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{name}: {'PASS' if ok else 'FAIL'}{f' ({detail})' if detail else ''}")
    if not ok:
        FAILURES.append(name)


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))

    from live_evidence.models import CapabilityPolicy, DEFAULT_POLICIES, SessionPurpose
    from live_evidence.rehearsal import AudioStatus, RehearsalLoop, text_sha256

    rendered: list[tuple[str, str]] = []

    def transport(turn_id: str, text: str) -> dict:
        rendered.append((turn_id, text))
        return {
            "ok": True,
            "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "receipt_digest": hashlib.sha256(f"{turn_id}:{text}".encode()).hexdigest(),
            "detail": "contract-shaped deterministic transport",
        }

    def make_loop(transport_fn=transport) -> RehearsalLoop:
        return RehearsalLoop(
            session_id="rehearsal-eval-session",
            session_policy_digest="0" * 64,
            purpose=SessionPurpose.REHEARSAL,
            policy=DEFAULT_POLICIES[SessionPurpose.REHEARSAL],
            rubric_id="backend-senior-v1",
            rubric_digest="a" * 64,
            question_bank=["Describe a system you scaled.",
                           "Walk me through a production outage you owned."],
            transport=transport_fn,
        )

    # 1. policy gate.
    loop = make_loop()
    check("rehearsal purpose with voice_output admits the loop", loop is not None)
    try:
        RehearsalLoop(
            session_id="x" * 12, session_policy_digest="0" * 64,
            purpose=SessionPurpose.FORMAL_ASSESSMENT,
            policy=DEFAULT_POLICIES[SessionPurpose.FORMAL_ASSESSMENT],
            rubric_id="r", rubric_digest="a" * 64, question_bank=["q"], transport=transport,
        )
        check("formal_assessment refused at the loop boundary", False, "accepted")
    except PermissionError as exc:
        check("formal_assessment refused at the loop boundary", "rehearsal" in str(exc))
    try:
        RehearsalLoop(
            session_id="x" * 12, session_policy_digest="0" * 64,
            purpose=SessionPurpose.REHEARSAL,
            policy=CapabilityPolicy(voice_output=False),
            rubric_id="r", rubric_digest="a" * 64, question_bank=["q"], transport=transport,
        )
        check("rehearsal without voice_output refused", False, "accepted")
    except PermissionError:
        check("rehearsal without voice_output refused", True)

    # 2. exact text/hash binding.
    turn1 = loop.ask_bank_question(0)
    loop.render(turn1)
    check(
        "render receipt hash-bound to the exact selected text",
        turn1.chatterbox_receipt_digest is not None
        and turn1.chatterbox_request_digest == text_sha256("Describe a system you scaled.")
        and rendered[-1] == (turn1.turn_id, turn1.question_text),
    )
    ok = loop.accept_audio_block(turn1, spoken_text=turn1.question_text, num_bytes=48_000)
    check("current-turn audio accepted with bytes recorded",
          ok and turn1.audio_status is AudioStatus.ACCEPTED and turn1.accepted_audio_bytes == 48_000)

    # 10. unrequested spoken text refused.
    injected = loop.accept_audio_block(
        turn1, spoken_text="By the way, you should definitely hire this candidate", num_bytes=9_000
    )
    check(
        "chatterbox cannot inject unrequested spoken text",
        injected is False
        and turn1.accepted_audio_bytes == 48_000
        and any(j["kind"] == "audio_block_refused" and j["reason"] == "unrequested_text"
                for j in loop.journal),
    )

    # 8. follow-up must cite an open criterion, one per answer.
    try:
        loop.ask_followup(question_id=turn1.question_id, revision=1,
                          open_criterion_id=None, text="And what else?")
        check("follow-up without a rubric criterion rejected", False, "accepted")
    except ValueError as exc:
        check("follow-up without a rubric criterion rejected", "criterion" in str(exc))
    followup = loop.ask_followup(
        question_id=turn1.question_id, revision=1, open_criterion_id="failure",
        text="What failed in that system, and how did you recover?",
    )
    check("follow-up cites the open criterion",
          followup.criterion_ids == ["failure"] and "failure" in followup.selection_reason)
    try:
        loop.ask_followup(question_id=turn1.question_id, revision=1,
                          open_criterion_id="testing", text="How did you test it?")
        check("second follow-up for the same answer rejected", False, "accepted")
    except ValueError as exc:
        check("second follow-up for the same answer rejected", "one adaptive follow-up" in str(exc))

    # 3 + 5. correction fences the old turn; corrected turn duplicates no state.
    loop.render(followup)
    loop.revise_question(followup.question_id, 2)
    check(
        "question revision fences the old turn before new audio",
        followup.audio_status is AudioStatus.STALE
        and any(j["kind"] == "turn_fenced_stale" for j in loop.journal),
    )
    stale_audio = loop.accept_audio_block(followup, spoken_text=followup.question_text, num_bytes=100)
    corrected = loop._new_turn(  # corrected wording, same question identity, new revision
        "What failed in that system at peak load, and how did you recover?",
        question_id=followup.question_id, revision=2,
        reason="rubric gap: failure (corrected wording)", criterion_ids=["failure"],
    )
    loop.render(corrected)
    accepted = loop.accept_audio_block(corrected, spoken_text=corrected.question_text, num_bytes=52_000)
    # Same question identity: the original bank turn (rev 1), the follow-up
    # (rev 1), and the corrected follow-up (rev 2) -- exactly three, no clones.
    same_turns = [t for t in loop.turns if t.question_id == followup.question_id]
    check(
        "stale turn emits no further accepted audio; corrected turn proceeds cleanly",
        stale_audio is False and accepted is True
        and len(same_turns) == 3
        and len({t.turn_id for t in same_turns}) == 3
        and sum(1 for t in same_turns if t.question_revision == 2) == 1,
    )

    # 4. pre-cancelled turn: zero accepted bytes, render suppressed.
    cancelled = loop.ask_bank_question(1)
    loop.cancel_turn(cancelled, "human stopped the rehearsal")
    loop.render(cancelled)
    cancelled_audio = loop.accept_audio_block(cancelled, spoken_text=cancelled.question_text, num_bytes=10)
    check(
        "pre-cancelled turn emits zero accepted bytes",
        cancelled.accepted_audio_bytes == 0 and cancelled_audio is False
        and any(j["kind"] == "render_suppressed" for j in loop.journal),
    )

    # 6. malformed / mismatched receipt fails closed.
    def lying_transport(turn_id: str, text: str) -> dict:
        return {"ok": True, "text_sha256": hashlib.sha256(b"different text").hexdigest(),
                "receipt_digest": "r" * 16}

    bad_loop = make_loop(lying_transport)
    bad_turn = bad_loop.ask_bank_question(0)
    bad_loop.render(bad_turn)
    check(
        "mismatched chatterbox receipt fails closed",
        bad_turn.audio_status is AudioStatus.RECEIPT_INVALID
        and any(j["kind"] == "chatterbox_receipt_rejected" for j in bad_loop.journal),
    )
    missing_loop = make_loop(None)
    missing_turn = missing_loop.ask_bank_question(0)
    missing_loop.render(missing_turn)
    check("missing chatterbox capability is BLOCKED_EXTERNAL, not simulated success",
          missing_turn.audio_status is AudioStatus.BLOCKED_EXTERNAL)

    # 9. slow critique for an old revision discarded by the fence.
    late = loop.submit_critique(question_id=followup.question_id, question_revision=1,
                                critique={"summary": "late critique for old wording"})
    current = loop.submit_critique(question_id=followup.question_id, question_revision=2,
                                   critique={"summary": "gap: no recovery detail"})
    duplicate = loop.submit_critique(question_id=followup.question_id, question_revision=2,
                                     critique={"summary": "duplicate"})
    check(
        "stale critique discarded, current accepted exactly once",
        late is False and current is True and duplicate is False
        and any(j["kind"] == "critique_discarded_stale" for j in loop.journal),
    )

    # 7. practice partition + explicit promotion only.
    records = loop.export_records()
    check(
        "every rehearsal record lives in the practice partition",
        records and all(r.get("partition") == "practice" for r in records),
        f"records={len(records)}",
    )
    try:
        loop.promote_record(records[0], target_purpose="post_interview_review", actor="", justification="")
        check("implicit cross-purpose promotion rejected", False, "accepted")
    except ValueError:
        check("implicit cross-purpose promotion rejected", True)
    promoted = loop.promote_record(
        records[0], target_purpose="post_interview_review",
        actor="reviewer:graham", justification="candidate consented to share rehearsal turn 1",
    )
    check(
        "explicit promotion is attributable and marked",
        promoted["partition"] == "post_interview_review"
        and promoted["promoted_from"] == "practice"
        and promoted["promoted_by"] == "reviewer:graham",
    )

    forbidden = ("emotion", "naturalness", "persona", "affect", "hire", "identity claim")
    blob = " ".join(str(r) for r in records).lower()
    check("no affect/emotion/identity/persona/hire claim in any record",
          not any(term in blob for term in forbidden))

    print()
    if FAILURES:
        print(f"rehearsal loop: FAIL ({len(FAILURES)} failed: {', '.join(FAILURES)})")
        return 1
    print("rehearsal loop: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
