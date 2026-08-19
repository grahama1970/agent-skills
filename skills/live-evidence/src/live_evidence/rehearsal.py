"""Practice-only interview rehearsal loop over Chatterbox (#1453).

Authority boundary: Live Evidence owns interview state -- question selection,
revision fencing, rubric coverage, critique. Chatterbox is a renderer of exact
approved text and nothing else; its output cannot change the selected
question, the rubric state, or what counts as evidence. No affect, emotion,
identity, naturalness, or Persona Dream claim is made anywhere here.

The loop is available only when the frozen session purpose (#1449) is
``rehearsal`` with ``voice_output=true``. Every artifact lands in a
practice-only partition; promotion into any other purpose requires an
explicit, attributable human action.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Callable
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .models import CapabilityPolicy, SessionPurpose


class AudioStatus(StrEnum):
    PENDING = "pending"
    RENDERING = "rendering"
    ACCEPTED = "accepted"
    CANCELLED = "cancelled"
    STALE = "stale"
    BLOCKED_EXTERNAL = "blocked_external"
    RECEIPT_INVALID = "receipt_invalid"


class RehearsalTurn(BaseModel):
    """live_evidence.rehearsal_turn.v1 -- one voiced question/follow-up."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    schema_id: str = Field(default="live_evidence.rehearsal_turn.v1",
                           validation_alias="schema", serialization_alias="schema")
    rehearsal_id: str = Field(min_length=8, max_length=64)
    session_id: str = Field(min_length=8, max_length=64)
    session_policy_digest: str = Field(min_length=64, max_length=64)
    rubric_id: str = Field(min_length=1, max_length=100)
    rubric_digest: str = Field(min_length=64, max_length=64)
    turn_id: str = Field(default_factory=lambda: uuid4().hex, min_length=8)
    question_id: str = Field(min_length=8, max_length=64)
    question_revision: int = Field(ge=0)
    question_text: str = Field(min_length=1, max_length=4_000)
    question_text_sha256: str = Field(min_length=64, max_length=64)
    selection_reason: str = Field(min_length=1, max_length=1_000)
    criterion_ids: list[str] = Field(default_factory=list, max_length=8)
    chatterbox_request_digest: str | None = None
    chatterbox_receipt_digest: str | None = None
    audio_status: AudioStatus = AudioStatus.PENDING
    accepted_audio_bytes: int = 0
    partition: str = "practice"
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# Transport contract: called with (turn_id, text) and returns a receipt dict
# {"ok": bool, "text_sha256": str, "receipt_digest": str, "detail": str}.
# The LIVE adapter posts to the running chatterbox server; the deterministic
# proof injects a contract-shaped transport. Either way, the loop verifies the
# receipt against the text IT selected -- an HTTP 200 is never acceptance.
ChatterboxTransport = Callable[[str, str], dict[str, Any]]


class RehearsalLoop:
    """Bounded practice-only turn loop. Live Evidence holds all authority."""

    def __init__(
        self,
        *,
        session_id: str,
        session_policy_digest: str,
        purpose: SessionPurpose,
        policy: CapabilityPolicy,
        rubric_id: str,
        rubric_digest: str,
        question_bank: list[str],
        transport: ChatterboxTransport | None,
    ) -> None:
        if purpose is not SessionPurpose.REHEARSAL or not policy.voice_output:
            raise PermissionError(
                "rehearsal voice loop requires purpose=rehearsal with voice_output=true; "
                f"got purpose={purpose.value} voice_output={policy.voice_output}"
            )
        self._session_id = session_id
        self._policy_digest = session_policy_digest
        self._rubric_id = rubric_id
        self._rubric_digest = rubric_digest
        self._bank = list(question_bank)
        self._transport = transport
        self.rehearsal_id = uuid4().hex
        self.turns: list[RehearsalTurn] = []
        self.journal: list[dict[str, Any]] = []
        self._followups_used: set[tuple[str, int]] = set()
        self._critiques: dict[str, dict[str, Any]] = {}

    # -- selection -------------------------------------------------------

    def _new_turn(self, text: str, *, question_id: str, revision: int,
                  reason: str, criterion_ids: list[str]) -> RehearsalTurn:
        turn = RehearsalTurn(
            rehearsal_id=self.rehearsal_id,
            session_id=self._session_id,
            session_policy_digest=self._policy_digest,
            rubric_id=self._rubric_id,
            rubric_digest=self._rubric_digest,
            question_id=question_id,
            question_revision=revision,
            question_text=text,
            question_text_sha256=text_sha256(text),
            selection_reason=reason,
            criterion_ids=criterion_ids,
        )
        self.turns.append(turn)
        return turn

    def ask_bank_question(self, index: int) -> RehearsalTurn:
        text = self._bank[index]
        return self._new_turn(
            text, question_id=uuid4().hex, revision=1,
            reason=f"approved question bank item {index}", criterion_ids=[],
        )

    def ask_followup(self, *, question_id: str, revision: int,
                     open_criterion_id: str | None, text: str) -> RehearsalTurn:
        """At most ONE adaptive follow-up per answer, and it must cite the
        open rubric criterion that motivates it -- a generic model follow-up
        detached from a rubric gap is rejected."""

        if not open_criterion_id:
            raise ValueError("follow-up must cite an open rubric criterion")
        key = (question_id, revision)
        if key in self._followups_used:
            raise ValueError("only one adaptive follow-up per answer in the MVP")
        self._followups_used.add(key)
        return self._new_turn(
            text, question_id=question_id, revision=revision,
            reason=f"rubric gap: {open_criterion_id}",
            criterion_ids=[open_criterion_id],
        )

    # -- rendering + fencing ---------------------------------------------

    def render(self, turn: RehearsalTurn) -> RehearsalTurn:
        """Render EXACTLY the selected text; verify the receipt against it."""

        if turn.audio_status in {AudioStatus.CANCELLED, AudioStatus.STALE}:
            self.journal.append({"kind": "render_suppressed", "turn_id": turn.turn_id,
                                 "audio_status": turn.audio_status.value})
            return turn
        if self._transport is None:
            turn.audio_status = AudioStatus.BLOCKED_EXTERNAL
            self.journal.append({"kind": "chatterbox_unavailable", "turn_id": turn.turn_id})
            return turn
        turn.audio_status = AudioStatus.RENDERING
        turn.chatterbox_request_digest = turn.question_text_sha256
        receipt = self._transport(turn.turn_id, turn.question_text)
        # Fail closed on a malformed or mismatched receipt: an ok=true with the
        # wrong text hash means Chatterbox rendered something we did not select.
        if (
            not isinstance(receipt, dict)
            or receipt.get("ok") is not True
            or receipt.get("text_sha256") != turn.question_text_sha256
            or not receipt.get("receipt_digest")
        ):
            turn.audio_status = AudioStatus.RECEIPT_INVALID
            self.journal.append({"kind": "chatterbox_receipt_rejected",
                                 "turn_id": turn.turn_id,
                                 "receipt": receipt if isinstance(receipt, dict) else str(receipt)})
            return turn
        turn.chatterbox_receipt_digest = str(receipt["receipt_digest"])
        return turn

    def accept_audio_block(self, turn: RehearsalTurn, *, spoken_text: str, num_bytes: int) -> bool:
        """Audio acceptance gate: only the current, uncancelled turn, and only
        for the exact selected text. Chatterbox cannot inject unrequested
        speech -- a block whose text hash differs is refused and journaled."""

        if turn.audio_status in {AudioStatus.CANCELLED, AudioStatus.STALE,
                                 AudioStatus.RECEIPT_INVALID, AudioStatus.BLOCKED_EXTERNAL}:
            self.journal.append({"kind": "audio_block_refused", "turn_id": turn.turn_id,
                                 "reason": turn.audio_status.value})
            return False
        if text_sha256(spoken_text) != turn.question_text_sha256:
            self.journal.append({"kind": "audio_block_refused", "turn_id": turn.turn_id,
                                 "reason": "unrequested_text"})
            return False
        turn.accepted_audio_bytes += int(num_bytes)
        turn.audio_status = AudioStatus.ACCEPTED
        return True

    def cancel_turn(self, turn: RehearsalTurn, reason: str) -> None:
        turn.audio_status = AudioStatus.CANCELLED
        turn.completed_at = datetime.now(timezone.utc)
        self.journal.append({"kind": "turn_cancelled", "turn_id": turn.turn_id, "reason": reason})

    def revise_question(self, question_id: str, new_revision: int) -> None:
        """A correction fences every older turn of that question BEFORE any
        new audio: stale turns can accept no further blocks."""

        for turn in self.turns:
            if turn.question_id == question_id and turn.question_revision < new_revision:
                if turn.audio_status not in {AudioStatus.CANCELLED, AudioStatus.STALE}:
                    turn.audio_status = AudioStatus.STALE
                    self.journal.append({"kind": "turn_fenced_stale", "turn_id": turn.turn_id,
                                         "superseded_by_revision": new_revision})

    # -- critique (off the voice critical path) ---------------------------

    def submit_critique(self, *, question_id: str, question_revision: int,
                        critique: dict[str, Any]) -> bool:
        """Slow critique lands after the fact and is revision-fenced: a result
        for revision N is discarded once a newer revision exists."""

        newest = max(
            (t.question_revision for t in self.turns if t.question_id == question_id),
            default=None,
        )
        if newest is None or question_revision < newest:
            self.journal.append({"kind": "critique_discarded_stale",
                                 "question_id": question_id,
                                 "question_revision": question_revision,
                                 "newest_revision": newest})
            return False
        key = f"{question_id}:{question_revision}"
        if key in self._critiques:
            self.journal.append({"kind": "critique_duplicate_ignored", "key": key})
            return False
        self._critiques[key] = {**critique, "partition": "practice"}
        return True

    # -- practice partition ------------------------------------------------

    def export_records(self) -> list[dict[str, Any]]:
        return [
            {**turn.model_dump(mode="json", by_alias=True)}
            for turn in self.turns
        ] + [
            {"kind": "critique", **payload} for payload in self._critiques.values()
        ]

    @staticmethod
    def promote_record(record: dict[str, Any], *, target_purpose: str, actor: str,
                       justification: str) -> dict[str, Any]:
        """Explicit, attributable cross-purpose promotion; never implicit."""

        if not actor or not justification:
            raise ValueError("cross-purpose promotion requires actor and justification")
        return {
            **record,
            "partition": target_purpose,
            "promoted_from": "practice",
            "promoted_by": actor,
            "promotion_justification": justification,
        }
