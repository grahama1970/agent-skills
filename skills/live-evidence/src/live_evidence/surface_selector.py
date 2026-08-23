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
the selector. Same direct-SciLLM stage boundary as the resolver/solver
(SKILL.md "Provider boundary: two tiers"): the live path cannot absorb
tau-dag orchestration per question, and selection is disposable judgment with
no receipt to preserve.
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

DEFAULT_URL = "http://127.0.0.1:4001"
DEFAULT_MODEL = "gpt-5.5"
DEFAULT_EFFORT = "low"
MAX_CANDIDATES = 10

PROMPT = (
    "You decide which retrieved evidence a live meeting assistant should "
    "surface to answer the CURRENT question. Judge relevance to the question "
    "and the conversation, not surface keyword overlap: prefer the source that "
    "actually answers it, and demote generic file matches (licenses, notices, "
    "readmes, fixtures) that merely mention the topic.\n"
    "Reply with ONLY a JSON array of candidate ids (integers), most relevant "
    "first. Include every id exactly once.\n\n"
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
        self._url = (url or os.getenv("LIVE_EVIDENCE_SCILLM_URL") or DEFAULT_URL).rstrip("/")
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
        """Return (reordered sources, receipt). Fail-open to the input order."""

        receipt: dict[str, Any] = {"mode": "surface_selector", "model": self._model,
                                   "effort": self._effort, "applied": False}
        if len(sources) < 2:
            return sources, receipt
        key = resolver_key()
        if not key:
            receipt["error"] = "no_scillm_key_configured"
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
            f"{self._url}/v1/chat/completions",
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
            order = _parse_order(content, len(pool))
        except Exception as exc:  # noqa: BLE001 -- fail-open on any transport error
            receipt["error"] = f"{type(exc).__name__}: {exc}"
            logger.warning("surface selector failed ({}); keeping deterministic order", exc)
            return sources, receipt
        receipt["elapsed_s"] = round(time.monotonic() - start, 3)
        if order is None:
            receipt["error"] = "unparseable_order"
            return sources, receipt
        reordered = [pool[i] for i in order] + sources[MAX_CANDIDATES:]
        receipt["applied"] = True
        receipt["order"] = order
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


def _parse_order(content: str, count: int) -> list[int] | None:
    start, end = content.find("["), content.rfind("]")
    if start == -1 or end == -1:
        return None
    try:
        raw = json.loads(content[start:end + 1])
    except json.JSONDecodeError:
        return None
    seen: list[int] = []
    for value in raw:
        if isinstance(value, int) and 0 <= value < count and value not in seen:
            seen.append(value)
    if not seen:
        return None
    # Append any candidate the model dropped, preserving its original position,
    # so no gathered evidence is silently lost by a short model reply.
    for index in range(count):
        if index not in seen:
            seen.append(index)
    return seen
