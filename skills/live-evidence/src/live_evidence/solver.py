"""Fast-path stage-2 solver (#1473).

One bounded streaming SciLLM call for one canonical question revision plus its
retrieved evidence. The staged answer contract is preserved; chunks stream so
the HUD shows first content seconds after the question settles instead of
waiting for a full orchestration round trip. `$ask tau-dag` remains the
escalation path (its run directory is the receipt-heavy route); this fast path
records model, effort, latency segments, and a response digest so its own
receipts stand on their own.

Same documented stage-boundary exception as the stage-1 resolver (SKILL.md
"Provider boundary: two tiers"): a live conversational path cannot absorb
full-compliance orchestration per call.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Iterator

from .resolver import resolver_key

DEFAULT_URL = "http://127.0.0.1:4001"
# sonnet, not opus: the answer path is latency-critical and opus low still
# spends a variable thinking phase before first content (measured live: p95
# 16s+ first content; sonnet completes comparable answers in ~3s). Quality is
# held by the blinded parity gate in eval_fast_solver, not by model prestige.
DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_EFFORT = "high"

CODE_PROMPT = (
    "Answer the interview/meeting question below directly; no roundtable or "
    "report framing.\n"
    "For coding questions use exactly these Markdown headings:\n"
    "## APPROACH\n## PSEUDOCODE\n## CODE\n## COMPLEXITY\n## OPTIMIZATIONS\n"
    "For factual/research questions: a compact answer, no headings.\n"
    "Evidence rules: general technical knowledge is fair game and needs no "
    "excerpt. Claims about THIS user's specific codebase or files must come "
    "from the provided excerpts only -- ignore excerpts irrelevant to the "
    "question, and say plainly when a codebase-specific claim has no excerpt "
    "support. Never refuse a general question for lack of excerpts.\n\n"
)


@dataclass
class SolverChunk:
    text: str
    elapsed_s: float


@dataclass
class SolverOutcome:
    ok: bool
    answer: str = ""
    error: str | None = None
    model: str = ""
    effort: str = ""
    first_content_s: float | None = None
    total_s: float | None = None
    response_sha256: str | None = None
    chunk_count: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


class FastSolver:
    """Stream one staged answer; emit SolverChunk deltas then a SolverOutcome."""

    def __init__(
        self,
        *,
        url: str | None = None,
        model: str | None = None,
        effort: str | None = None,
        timeout_s: float = 90.0,
    ) -> None:
        self._url = (url or os.getenv("LIVE_EVIDENCE_SCILLM_URL") or DEFAULT_URL).rstrip("/")
        self._model = model or os.getenv("LIVE_EVIDENCE_SOLVER_MODEL") or DEFAULT_MODEL
        self._effort = effort or os.getenv("LIVE_EVIDENCE_SOLVER_EFFORT") or DEFAULT_EFFORT
        self._timeout_s = timeout_s

    @staticmethod
    def available() -> bool:
        if os.getenv("LIVE_EVIDENCE_FAST_SOLVER", "true").lower() in {"0", "false", "no"}:
            return False
        return bool(os.getenv("LIVE_EVIDENCE_SOLVER_FIXTURE") or resolver_key())

    def stream(self, query: str, evidence_excerpts: list[str]) -> Iterator[SolverChunk | SolverOutcome]:
        fixture = os.getenv("LIVE_EVIDENCE_SOLVER_FIXTURE")
        start = time.monotonic()
        if fixture:
            # Deterministic transport for negative-path evals; the live rung
            # never sets this and the receipt records the mode.
            text = open(fixture, encoding="utf-8").read()
            yield SolverChunk(text=text, elapsed_s=time.monotonic() - start)
            yield SolverOutcome(
                ok=True, answer=text, model="fixture", effort="fixture",
                first_content_s=0.0, total_s=time.monotonic() - start,
                response_sha256=hashlib.sha256(text.encode()).hexdigest(),
                chunk_count=1, extra={"mode": "fixture"},
            )
            return
        key = resolver_key()
        if not key:
            yield SolverOutcome(ok=False, error="no_scillm_key_configured")
            return
        body = CODE_PROMPT + "QUESTION:\n" + query
        if evidence_excerpts:
            body += "\n\nLOCAL EVIDENCE EXCERPTS:\n" + "\n---\n".join(evidence_excerpts[:4])
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": body}],
            "reasoning_effort": self._effort,
            "stream": True,
        }
        request = urllib.request.Request(
            f"{self._url}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {key}",
                "X-Caller-Skill": "live-evidence",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        accumulated = ""
        first_content: float | None = None
        chunks = 0
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8", "ignore").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                    piece = delta.get("content") or ""
                    if not piece:
                        continue
                    if first_content is None:
                        first_content = time.monotonic() - start
                    accumulated += piece
                    chunks += 1
                    yield SolverChunk(text=piece, elapsed_s=time.monotonic() - start)
        except Exception as exc:
            yield SolverOutcome(
                ok=False, error=f"{type(exc).__name__}: {exc}", answer=accumulated,
                model=self._model, effort=self._effort,
                first_content_s=first_content, total_s=time.monotonic() - start,
                chunk_count=chunks,
            )
            return
        yield SolverOutcome(
            ok=bool(accumulated.strip()),
            answer=accumulated,
            error=None if accumulated.strip() else "empty_response",
            model=self._model, effort=self._effort,
            first_content_s=first_content, total_s=time.monotonic() - start,
            response_sha256=hashlib.sha256(accumulated.encode()).hexdigest(),
            chunk_count=chunks,
        )
