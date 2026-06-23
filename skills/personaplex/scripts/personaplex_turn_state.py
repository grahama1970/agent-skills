#!/usr/bin/env python3
from __future__ import annotations
"""Turn-aware state, output gate, and stale-callback fencing for PersonaPlex P0.

This module is intentionally stdlib-only so the greenfield bundle can be sanity
checked before it is mechanically ported into the real PersonaPlex wrapper.  It
models the safety-critical contract the live wrapper must preserve around
Deepgram final turns, memory-route callbacks, PersonaPlex grounding injection,
and bounded response release.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import time
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def stable_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_json(data: Any) -> str:
    return sha256_text(stable_json(data))


@dataclass(frozen=True)
class TurnToken:
    """Current-turn authority token carried through every async callback."""

    session_id: str
    persona_id: str
    turn_id: int
    generation: int
    transcript_hash: str
    policy_version: str
    created_at_utc: str

    @property
    def turn_key(self) -> str:
        return f"conversation:{self.session_id}:{self.turn_id:06d}"

    @property
    def authority_key(self) -> str:
        return sha256_json(
            {
                "session_id": self.session_id,
                "persona_id": self.persona_id,
                "turn_id": self.turn_id,
                "generation": self.generation,
                "transcript_hash": self.transcript_hash,
                "policy_version": self.policy_version,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["turn_key"] = self.turn_key
        data["authority_key"] = self.authority_key
        return data


@dataclass
class StaleCallbackReceipt:
    operation: str
    stale_turn_id: int
    stale_generation: int
    active_turn_id: int | None
    active_generation: int | None
    reason: str
    details: dict[str, Any] = field(default_factory=dict)
    created_at_utc: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class IntentAuthoritySnapshot:
    turn_id: int
    generation: int
    authority_key: str
    intent_hash: str
    action: str
    recall_profile: str
    tool_calls: list[dict[str, Any]]
    allowed_tools: list[str]
    query_plan: dict[str, Any]
    authoritative: bool
    note: str

    def non_authoritative_copy(self, note: str) -> dict[str, Any]:
        data = asdict(self)
        data["authoritative"] = False
        data["note"] = note
        return data


@dataclass
class ResponsePacket:
    """A bounded response that may be released only for its active turn."""

    session_id: str
    turn_id: int
    generation: int
    route_endpoint: str
    text: str
    factual_claims_allowed: bool
    source_product_hash: str
    current_intent_authority_hash: str
    bounded: bool = True
    created_at_utc: str = field(default_factory=utc_now)

    @property
    def packet_hash(self) -> str:
        return sha256_json(self.to_dict(include_hash=False))

    def to_dict(self, include_hash: bool = True) -> dict[str, Any]:
        data = asdict(self)
        if include_hash:
            data["packet_hash"] = self.packet_hash
        return data


@dataclass
class GateReceipt:
    session_id: str
    turn_id: int
    generation: int
    gate_closed_reason: str
    closed_at_monotonic: float
    released_at_monotonic: float
    queue_depth_at_release: int
    blocked_token_count: int
    response_packet_hash: str
    release_authorized: bool
    created_at_utc: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TurnStateMachine:
    """Monotonic turn state with strict stale-callback fencing.

    A new Deepgram ``speech_final`` event creates a fresh ``TurnToken``.  Any
    callback from an older token may still finish, but it cannot mutate state;
    callers must use ``require_active`` before every enqueue, gate release,
    receipt write, memory upsert, or session-head update.
    """

    def __init__(self, session_id: str, persona_id: str, policy_version: str = "p0-live-turn-aware-memory-compliance-harness.v1") -> None:
        self.session_id = session_id
        self.persona_id = persona_id
        self.policy_version = policy_version
        self._active_token: TurnToken | None = None
        self._next_turn_id = 0
        self._generation = 0
        self._current_intent_authority: IntentAuthoritySnapshot | None = None
        self._historical_authorities_for_next_turn: list[dict[str, Any]] = []
        self.stale_rejections: list[StaleCallbackReceipt] = []
        self.events: list[dict[str, Any]] = []

    @property
    def active_token(self) -> TurnToken | None:
        return self._active_token

    def start_turn(self, transcript: str) -> TurnToken:
        previous = self._active_token
        if previous is not None and self._current_intent_authority is not None:
            self._historical_authorities_for_next_turn.append(
                self._current_intent_authority.non_authoritative_copy(
                    "superseded by a newer speech_final turn; retained for audit/context only and cannot authorize tools"
                )
            )
        elif previous is not None:
            self._historical_authorities_for_next_turn.append(
                {
                    "turn_id": previous.turn_id,
                    "generation": previous.generation,
                    "authority_key": previous.authority_key,
                    "authoritative": False,
                    "note": "superseded before intent authority was established; transcript context only",
                }
            )
        self._current_intent_authority = None
        self._next_turn_id += 1
        self._generation += 1
        token = TurnToken(
            session_id=self.session_id,
            persona_id=self.persona_id,
            turn_id=self._next_turn_id,
            generation=self._generation,
            transcript_hash=sha256_text(transcript),
            policy_version=self.policy_version,
            created_at_utc=utc_now(),
        )
        self._active_token = token
        self.events.append(
            {
                "event": "turn_started",
                "turn": token.to_dict(),
                "previous_turn_id": previous.turn_id if previous else None,
                "created_at_utc": utc_now(),
            }
        )
        return token

    def consume_historical_authorities_for_active_turn(self) -> list[dict[str, Any]]:
        items = list(self._historical_authorities_for_next_turn)
        self._historical_authorities_for_next_turn.clear()
        return items

    def is_active(self, token: TurnToken) -> bool:
        active = self._active_token
        return bool(active and active.turn_id == token.turn_id and active.generation == token.generation)

    def require_active(self, token: TurnToken, operation: str, details: dict[str, Any] | None = None) -> bool:
        if self.is_active(token):
            return True
        active = self._active_token
        receipt = StaleCallbackReceipt(
            operation=operation,
            stale_turn_id=token.turn_id,
            stale_generation=token.generation,
            active_turn_id=active.turn_id if active else None,
            active_generation=active.generation if active else None,
            reason="stale turn callback fenced before mutation",
            details=details or {},
        )
        self.stale_rejections.append(receipt)
        self.events.append({"event": "stale_callback_rejected", **receipt.to_dict()})
        return False

    def attach_current_intent_authority(self, token: TurnToken, intent: dict[str, Any]) -> IntentAuthoritySnapshot | None:
        if not self.require_active(token, "attach_current_intent_authority"):
            return None
        data = intent.get("json") or intent
        snapshot = IntentAuthoritySnapshot(
            turn_id=token.turn_id,
            generation=token.generation,
            authority_key=token.authority_key,
            intent_hash=sha256_json(intent),
            action=str(data.get("action") or "").upper(),
            recall_profile=str(data.get("recall_profile") or ""),
            tool_calls=list(data.get("tool_calls") or []),
            allowed_tools=list(data.get("allowed_tools") or []),
            query_plan=dict(data.get("query_plan") or {}),
            authoritative=True,
            note="current /memory intent authority for this turn only",
        )
        self._current_intent_authority = snapshot
        self.events.append(
            {
                "event": "current_intent_authority_attached",
                "turn_id": token.turn_id,
                "generation": token.generation,
                "intent_hash": snapshot.intent_hash,
                "created_at_utc": utc_now(),
            }
        )
        return snapshot


class GateStateError(RuntimeError):
    pass


class TurnAwareOutputGate:
    """Gate and data stop for PersonaPlex output.

    Tokens produced while closed are blocked, not queued for later release.  The
    gate can open only after an active-turn ``ResponsePacket`` is staged.  This
    makes ``queue_depth_at_release`` deterministic and prevents old/ungrounded
    model output from leaking after memory/evidence work completes.
    """

    def __init__(self, state: TurnStateMachine) -> None:
        self.state = state
        self.closed = False
        self.gate_turn: TurnToken | None = None
        self.closed_reason = ""
        self.closed_at_monotonic = 0.0
        self.released_at_monotonic = 0.0
        self.pending_output_tokens: list[str] = []
        self.blocked_output_tokens: list[dict[str, Any]] = []
        self.response_packet: ResponsePacket | None = None
        self.release_receipts: list[GateReceipt] = []

    def close_for_turn(self, token: TurnToken, reason: str) -> None:
        if not self.state.require_active(token, "close_output_gate", {"reason": reason}):
            return
        self.closed = True
        self.gate_turn = token
        self.closed_reason = reason
        self.closed_at_monotonic = time.monotonic()
        self.released_at_monotonic = 0.0
        self.pending_output_tokens.clear()
        self.blocked_output_tokens.clear()
        self.response_packet = None
        self.state.events.append(
            {
                "event": "output_gate_closed",
                "turn_id": token.turn_id,
                "generation": token.generation,
                "reason": reason,
                "created_at_utc": utc_now(),
            }
        )

    def enqueue_model_token(self, token: TurnToken, token_text: str, factual: bool = True) -> bool:
        if not self.state.require_active(token, "enqueue_model_token", {"factual": factual}):
            return False
        if self.closed:
            self.blocked_output_tokens.append(
                {
                    "turn_id": token.turn_id,
                    "generation": token.generation,
                    "token_hash": sha256_text(token_text),
                    "factual": factual,
                    "reason": "output gate closed; token discarded rather than queued",
                    "created_at_utc": utc_now(),
                }
            )
            return False
        self.pending_output_tokens.append(token_text)
        return True

    def stage_response_packet(self, token: TurnToken, packet: ResponsePacket) -> bool:
        if not self.state.require_active(token, "stage_response_packet", {"route_endpoint": packet.route_endpoint}):
            return False
        if packet.turn_id != token.turn_id or packet.generation != token.generation:
            self.state.require_active(
                TurnToken(
                    session_id=token.session_id,
                    persona_id=token.persona_id,
                    turn_id=packet.turn_id,
                    generation=packet.generation,
                    transcript_hash=token.transcript_hash,
                    policy_version=token.policy_version,
                    created_at_utc=token.created_at_utc,
                ),
                "stage_response_packet_packet_identity_mismatch",
                {"active_turn_id": token.turn_id},
            )
            return False
        if not packet.bounded:
            raise GateStateError("response packet must be bounded")
        self.response_packet = packet
        self.pending_output_tokens.clear()
        self.state.events.append(
            {
                "event": "response_packet_staged",
                "turn_id": token.turn_id,
                "route_endpoint": packet.route_endpoint,
                "packet_hash": packet.packet_hash,
                "blocked_token_count": len(self.blocked_output_tokens),
                "created_at_utc": utc_now(),
            }
        )
        return True

    def open_for_active_packet(self, token: TurnToken) -> GateReceipt | None:
        if not self.state.require_active(token, "open_output_gate"):
            return None
        if self.gate_turn is None or self.gate_turn.turn_id != token.turn_id:
            raise GateStateError("gate is not closed for the active turn")
        if self.response_packet is None:
            raise GateStateError("cannot open gate before an active bounded response packet is staged")
        queue_depth = len(self.pending_output_tokens)
        if queue_depth != 0:
            raise GateStateError(f"cannot open gate with queued unauthorized model tokens: queue_depth={queue_depth}")
        self.closed = False
        self.released_at_monotonic = time.monotonic()
        receipt = GateReceipt(
            session_id=token.session_id,
            turn_id=token.turn_id,
            generation=token.generation,
            gate_closed_reason=self.closed_reason,
            closed_at_monotonic=self.closed_at_monotonic,
            released_at_monotonic=self.released_at_monotonic,
            queue_depth_at_release=queue_depth,
            blocked_token_count=len(self.blocked_output_tokens),
            response_packet_hash=self.response_packet.packet_hash,
            release_authorized=True,
        )
        self.release_receipts.append(receipt)
        self.state.events.append({"event": "output_gate_opened", **receipt.to_dict()})
        return receipt
