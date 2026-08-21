"""Durable write for explicit meeting decisions, proven only by readback.

Scope is deliberately one narrow fact class: an explicit decision or commitment
stated in the room. This is not general-purpose salience scoring.

The central rule is that the writer's own response body is never read. The
memory service on this machine has returned a success body for a document it
never wrote, so a `stored: true` field is not evidence of anything. The write
here opens a streaming response, observes only the transport status, and closes
it without touching the body; success is established solely by reading the
document back through a keyed lookup. That is structural rather than a
convention someone can quietly drop later.

Identity is deterministic:

    fact_id = sha256(session_id | fact_type | ordered source_event_ids)

so replaying the same source events cannot create a duplicate record.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from .models import TranscriptEvent, TranscriptKind

# Explicit commitment language only. "I will look at that" is conversation;
# "we decided" is a record. Anything outside these forms fails closed rather
# than guessing at intent.
_DECISION_FORMS = (
    r"\bthe meeting decision is\b",
    r"\bwe decided\b",
    r"\bwe have decided\b",
    r"\bwe agreed\b",
    r"\bwe have agreed\b",
    r"\bdecision:\b",
    r"\bmy commitment is\b",
    r"\bi commit to\b",
)
_DECISION_RE = re.compile("|".join(_DECISION_FORMS), re.IGNORECASE)

# Hedged language disqualifies a span even when it carries a decision form.
_NONCOMMITTAL_RE = re.compile(
    r"\b(maybe|might|perhaps|possibly|not sure|tentatively|if we|should we|could we)\b",
    re.IGNORECASE,
)

MIN_VALUE_CHARS = 24


class SalientFact(BaseModel):
    """One explicit decision, bound to the transcript that produced it."""

    model_config = ConfigDict(extra="forbid")

    schema_id: str = Field(default="live_evidence.salient_fact.v1", alias="schema")
    fact_id: str = Field(min_length=64, max_length=64)
    fact_type: str = Field(default="decision")
    session_id: str = Field(min_length=8)
    speaker: str
    value: str = Field(min_length=1, max_length=2_000)
    source_event_ids: list[str] = Field(min_length=1, max_length=16)
    source_sha256: str = Field(min_length=64, max_length=64)


def compute_fact_id(session_id: str, fact_type: str, source_event_ids: list[str]) -> str:
    """Deterministic identity, so reprocessing cannot duplicate a record."""

    payload = "|".join([session_id, fact_type, *source_event_ids])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def source_digest(events: list[TranscriptEvent]) -> str:
    """Hash the exact source text, so a record cannot drift from its evidence."""

    joined = "\n".join(event.text for event in events)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def extract_decision(event: TranscriptEvent, session_id: str) -> SalientFact | None:
    """Return a decision fact, or None. Deterministic and fail-closed.

    Rejects: non-final events (interim/stabilized text is still changing),
    questions, hedged phrasing, and spans too short to carry a decision.
    """

    if event.kind is not TranscriptKind.FINAL:
        return None
    text = " ".join(event.text.split())
    if not text or text.rstrip().endswith("?"):
        return None
    if _DECISION_RE.search(text) is None:
        return None
    if _NONCOMMITTAL_RE.search(text) is not None:
        return None
    if len(text) < MIN_VALUE_CHARS:
        return None

    source_event_ids = [event.event_id]
    return SalientFact(
        fact_id=compute_fact_id(session_id, "decision", source_event_ids),
        session_id=session_id,
        speaker=event.speaker.value,
        value=text[:2_000],
        source_event_ids=source_event_ids,
        source_sha256=source_digest([event]),
    )


class SalientFactWriter:
    """Write a fact and confirm it only by independent keyed readback."""

    def __init__(self, memory_url: str, collection: str = "live_evidence_facts", timeout_s: float = 10.0) -> None:
        self._url = memory_url.rstrip("/")
        self._collection = collection
        self._timeout_s = timeout_s

    async def write_and_confirm(self, fact: SalientFact) -> tuple[bool, str]:
        """Return (confirmed, detail). Confirmation never comes from the write."""

        document: dict[str, Any] = {"_key": fact.fact_id, **fact.model_dump(by_alias=True)}
        # OSError included: httpx eagerly builds an SSL context and raises
        # FileNotFoundError when the running venv has no CA bundle -- observed
        # live in the suite's ephemeral env (#1475 action lane). A transport
        # that cannot even construct is still a transport error, not a 500.
        try:
            await self._blind_write(document)
        except (httpx.HTTPError, OSError) as exc:
            return False, f"write_transport_error:{type(exc).__name__}"

        try:
            found = await self._readback(fact.fact_id)
        except (httpx.HTTPError, OSError) as exc:
            return False, f"readback_transport_error:{type(exc).__name__}"

        if found is None:
            return False, "readback_found_no_record"
        if found.get("source_sha256") != fact.source_sha256:
            return False, "readback_source_digest_mismatch"
        return True, "confirmed_by_readback"

    async def _blind_write(self, document: dict[str, Any]) -> None:
        """POST the document without ever reading the response body.

        The body is deliberately not parsed, streamed, or inspected. Whatever
        the service claims about its own success is irrelevant; only the
        readback decides. Reading it here would reintroduce exactly the
        failure this guards against.
        """

        payload = {"collection": self._collection, "documents": [document]}

        # urllib rather than httpx: httpx eagerly builds an SSL context and
        # raises FileNotFoundError in a venv without a CA bundle (observed in
        # the suite's ephemeral env), and this endpoint is plain local http.
        # The body is deliberately never read: only the keyed readback decides.
        import asyncio
        import json as _json
        import urllib.request

        def post_blind() -> int:
            request = urllib.request.Request(
                f"{self._url}/upsert",
                data=_json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json",
                         "X-Caller-Skill": "live-evidence"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                    return int(response.status)
            except urllib.error.HTTPError as exc:
                return int(exc.code)

        status = await asyncio.to_thread(post_blind)
        if status >= 500:
            raise OSError(f"memory upsert transport failure: HTTP {status}")

    async def _readback(self, fact_id: str) -> dict[str, Any] | None:
        """Keyed lookup. This, and only this, establishes that a write landed."""

        payload = {"collection": self._collection, "keys": [fact_id]}
        import asyncio
        import json as _json
        import urllib.request

        def recall() -> dict[str, Any] | None:
            request = urllib.request.Request(
                f"{self._url}/recall/by-keys",
                data=_json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json",
                         "X-Caller-Skill": "live-evidence"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                    if response.status != 200:
                        return None
                    return _json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError:
                return None

        body = await asyncio.to_thread(recall)
        if body is None:
            return None
        documents = body.get("documents") or body.get("results") or []
        for document in documents:
            if isinstance(document, dict) and document.get("_key") == fact_id:
                return document
        return None
