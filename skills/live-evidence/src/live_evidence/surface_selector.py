"""Agentic surfacing selector (which evidence to surface, decided by a model).

A deterministic scalar ranker cannot judge relevance to the live conversation:
ripgrep matches carry structural freshness/locator bonuses that a
semantically-correct memory document can never earn, so file-name noise
outranked the answer (caught by the agentic transcript eval). The fix is to
let a fast model decide what to surface, not a weight table.

One quick `gpt-5.5` low-reasoning call takes the canonical question, the recent
conversation thread, and the gathered candidate sources, and returns the
candidates ordered most-relevant first. The deterministic ranker is demoted to
a candidate GATHERER (dedup + coarse cap); this call is the arbiter.

Fail-open by construction: no key, a timeout, an unparseable reply, or an empty
result leaves the caller's order untouched, so the card path never blocks on
the selector. Direct provider calls are disabled; selection is deterministic/fail-open unless Tau-backed reviewer work is explicitly configured elsewhere.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Any

from loguru import logger

from .models import EvidenceSource
from .resolver import resolver_key

DEFAULT_URL = ""
DEFAULT_MODEL = "gpt-5.5"
DEFAULT_EFFORT = "low"
MAX_CANDIDATES = 10

PROMPT = (
    "You are the filtering agent for a live meeting assistant. A candidate "
    "utterance was detected and evidence retrieved. You make two decisions.\n\n"
    "1. SURFACE (the gate): is this a genuine, answerable question or request "
    "for information that a human would want an evidence card for? Set "
    "surface=false ONLY for turns that are not real questions -- a rhetorical "
    "aside ('right?', 'make sense?'), a greeting or standup framing, a "
    "social/logistics remark ('can everyone hear me', 'move this to Friday'), a "
    "plain statement, a bare mention of a project name, or an incomplete "
    "half-formed fragment. A genuine question ALWAYS surfaces, even when the "
    "retrieved evidence is thin or weak -- a thin answer is the card's problem, "
    "not a reason to hide that the question was asked. When unsure, surface.\n\n"
    "2. ORDER: if surfacing, order the candidate ids most-relevant-first by "
    "MEANING, not keyword overlap -- put the source that actually answers the "
    "question first and demote generic file matches (licenses, notices, "
    "readmes, fixtures, unrelated tests) that merely mention the topic.\n\n"
    "Reply with ONLY JSON: {\"surface\": true|false, \"order\": [ids], "
    "\"reason\": \"<one sentence>\"}\n\n"
)


class SurfaceSelector:
    """One fast model call that orders candidates by relevance to the turn."""

    def __init__(
        self,
        *,
        url: str | None = None,
        model: str | None = None,
        effort: str | None = None,
        timeout_s: float = 8.0,
    ) -> None:
        self._url = (url or DEFAULT_URL).rstrip("/")
        self._model = model or os.getenv("LIVE_EVIDENCE_SELECTOR_MODEL") or DEFAULT_MODEL
        self._effort = effort or os.getenv("LIVE_EVIDENCE_SELECTOR_EFFORT") or DEFAULT_EFFORT
        self._timeout_s = timeout_s

    @staticmethod
    def enabled() -> bool:
        if os.getenv("LIVE_EVIDENCE_SURFACE_SELECTOR", "true").lower() in {"0", "false", "no"}:
            return False
        return bool(resolver_key())

    def order(
        self, query: str, thread: str, sources: list[EvidenceSource]
    ) -> tuple[list[EvidenceSource], dict[str, Any]]:
        """Decide whether to surface a card and, if so, order its evidence.

        Returns (reordered sources, receipt). receipt["surface"] is the gate:
        False means suppress the card (an irrelevant/non-question turn).
        Fail-open on every failure path: an unreachable or unparseable selector
        keeps surface=True and the input order, so the card path never goes
        dark because the gate could not run.
        """

        receipt: dict[str, Any] = {"mode": "surface_selector", "model": self._model,
                                   "effort": self._effort, "applied": False,
                                   "surface": True}
        if not sources:
            return sources, receipt
        key = resolver_key()
        if not key:
            receipt["error"] = "direct_provider_disabled_tau_only"
            return sources, receipt
        pool = _balanced_pool(sources, MAX_CANDIDATES)
        lines = [
            f"[{i}] lane={s.lane.value} {(s.label or '')[:80]}: "
            f"{' '.join((s.excerpt or '').split())[:240]}"
            for i, s in enumerate(pool)
        ]
        receipt["candidates"] = [
            f"{s.lane.value}:{(s.label or '')[:60]}" for s in pool
        ]
        body = (
            f"{PROMPT}CURRENT QUESTION: {query}\n"
            f"CONVERSATION THREAD: {thread or '(none)'}\n\n"
            "CANDIDATES:\n" + "\n".join(lines)
        )
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": body}],
            "reasoning_effort": self._effort,
            "stream": False,
        }
        request = urllib.request.Request(
            f"{self._url}/provider-disabled",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {key}",
                     "X-Caller-Skill": "live-evidence",
                     "Content-Type": "application/json"},
            method="POST",
        )
        start = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                data = json.loads(response.read().decode("utf-8"))
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            decision = _parse_decision(content, len(pool))
        except Exception as exc:  # noqa: BLE001 -- fail-open on any transport error
            receipt["error"] = f"{type(exc).__name__}: {exc}"
            logger.warning("surface selector failed ({}); surfacing with input order", exc)
            return sources, receipt
        receipt["elapsed_s"] = round(time.monotonic() - start, 3)
        if decision is None:
            receipt["error"] = "unparseable_decision"
            return sources, receipt
        receipt["applied"] = True
        receipt["surface"] = decision["surface"]
        receipt["reason"] = decision["reason"]
        if not decision["surface"]:
            return sources, receipt
        receipt["order"] = decision["order"]
        reordered = [pool[i] for i in decision["order"]] + sources[MAX_CANDIDATES:]
        return reordered, receipt


def _balanced_pool(sources: list[EvidenceSource], cap: int) -> list[EvidenceSource]:
    """Round-robin across lanes so every lane that retrieved evidence reaches
    the selector. A ripgrep flood (8+ file hits) otherwise fills the cap and
    the one memory document that answers the question never gets judged."""

    by_lane: dict[Any, list[EvidenceSource]] = {}
    for source in sources:
        by_lane.setdefault(source.lane, []).append(source)
    pool: list[EvidenceSource] = []
    rank = 0
    while len(pool) < cap and any(rank < len(v) for v in by_lane.values()):
        for lane_sources in by_lane.values():
            if rank < len(lane_sources) and len(pool) < cap:
                pool.append(lane_sources[rank])
        rank += 1
    return pool


def _parse_decision(content: str, count: int) -> dict[str, Any] | None:
    """Parse {"surface": bool, "order": [ids], "reason": str}. None if unusable."""

    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        raw = json.loads(content[start:end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict) or "surface" not in raw:
        return None
    surface = bool(raw.get("surface"))
    reason = str(raw.get("reason") or "")
    order: list[int] = []
    for value in raw.get("order") or []:
        if isinstance(value, int) and 0 <= value < count and value not in order:
            order.append(value)
    # Append any candidate the model dropped, preserving original position, so
    # no gathered evidence is silently lost when the card does surface.
    for index in range(count):
        if index not in order:
            order.append(index)
    return {"surface": surface, "order": order, "reason": reason}
