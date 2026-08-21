"""Briefing-pack opening detection for live meetings.

Before a call, the human loads a pack of talking points: each point carries
opening-trigger vocabulary, the hook sentence to say, and the concrete story
that backs it. During live monitoring every final transcript event is matched
against the pack, and a hit surfaces the point WITH the exact phrase and
event that opened the door -- a recognition assist, never a script.

Deterministic floor by design: phrase/term matching is zero-latency on the
hot transcript path and every surfaced point is bound to the transcript
events that triggered it. A point cools down after surfacing so one topic
does not spam the HUD. Not available in formal_assessment sessions.
"""

from __future__ import annotations

import hashlib
import json
import re
from time import monotonic
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_COOLDOWN_S = 120.0


class BriefingPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    point_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=300)
    # Any ONE group matching surfaces the point; a group matches when ALL its
    # terms appear in the rolling recent-transcript window (multi-word phrases
    # allowed; matching is case-insensitive on word boundaries).
    opening_triggers: list[list[str]] = Field(min_length=1, max_length=16)
    hook: str = Field(default="", max_length=1_000)
    story: str = Field(default="", max_length=2_000)
    ask: str = Field(default="", max_length=1_000)
    sources: list[str] = Field(default_factory=list, max_length=8)

    @property
    def display_text(self) -> str:
        return self.hook or self.ask

    def model_post_init(self, __context) -> None:
        if not (self.hook or self.ask):
            raise ValueError(f"briefing point {self.point_id} needs a hook or an ask")


class BriefingPack(BaseModel):
    """live_evidence.briefing_pack.v1 -- one call's prepared openings."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    schema_id: Literal["live_evidence.briefing_pack.v1"] = Field(
        default="live_evidence.briefing_pack.v1",
        validation_alias="schema", serialization_alias="schema",
    )
    pack_id: str = Field(min_length=1, max_length=100)
    audience: str = Field(min_length=1, max_length=200)
    core_concepts: list[str] = Field(default_factory=list, max_length=12)
    closing_sentence: str = Field(default="", max_length=1_000)
    points: list[BriefingPoint] = Field(min_length=1, max_length=64)

    def pack_digest(self) -> str:
        payload = self.model_dump(mode="json", by_alias=True)
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


def _term_pattern(term: str) -> re.Pattern:
    """Word-start anchored, stem-open: 'pilot' matches 'pilots', 'operationaliz'
    matches 'operationalize/-ation', while 'rag' still cannot match 'dragon'."""

    words = [re.escape(w) for w in term.split()]
    words[-1] = words[-1] + r"\w*"
    return re.compile(r"\b" + r"[\s\-]+".join(words), re.IGNORECASE)


class BriefingMatcher:
    """Match final transcript events against the loaded pack, with cooldown.

    A rolling window of recent final-event text is kept so a trigger group
    whose terms arrive across two adjacent sentences still matches, and every
    surfaced point records the event ids that contributed.
    """

    def __init__(self, pack: BriefingPack, *, cooldown_s: float = DEFAULT_COOLDOWN_S,
                 window_events: int = 6) -> None:
        self.pack = pack
        self.digest = pack.pack_digest()
        self._cooldown_s = cooldown_s
        self._window: list[tuple[str, str]] = []  # (event_id, text)
        self._window_events = window_events
        self._last_surfaced: dict[str, float] = {}
        self._patterns: dict[str, list[list[re.Pattern]]] = {
            point.point_id: [[_term_pattern(t) for t in group]
                              for group in point.opening_triggers]
            for point in pack.points
        }
        self.surfaced: list[dict[str, Any]] = []

    def match(self, event_id: str, text: str) -> list[dict[str, Any]]:
        """Feed one FINAL transcript event; return newly surfaced points."""

        self._window.append((event_id, text))
        self._window = self._window[-self._window_events:]
        window_text = " ".join(t for _, t in self._window)
        now = monotonic()
        hits: list[dict[str, Any]] = []
        for point in self.pack.points:
            last = self._last_surfaced.get(point.point_id)
            if last is not None and now - last < self._cooldown_s:
                continue
            for group, patterns in zip(point.opening_triggers,
                                        self._patterns[point.point_id]):
                if all(p.search(window_text) for p in patterns):
                    matched_terms = list(group)
                    trigger_events = [
                        eid for eid, t in self._window
                        if any(p.search(t) for p in patterns)
                    ]
                    self._last_surfaced[point.point_id] = now
                    hit = {
                        "point_id": point.point_id,
                        "title": point.title,
                        "hook": point.hook,
                        "story": point.story,
                        "ask": point.ask,
                        "matched_terms": matched_terms,
                        "trigger_event_ids": trigger_events or [event_id],
                        "pack_digest": self.digest,
                    }
                    hits.append(hit)
                    self.surfaced.append(hit)
                    break
        self.surfaced = self.surfaced[-24:]
        return hits
