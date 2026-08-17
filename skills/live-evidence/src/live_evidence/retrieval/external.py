"""Manual Brave and Dogpile skill composition.

These clients are never called from automatic transcript handling. They receive
only the explicit bounded query supplied by the operator and preserve command
failure as a degraded lane instead of inventing results.
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess

from .subprocess_env import child_env
from pathlib import Path
from time import monotonic
from typing import Any

from pydantic import BaseModel, Field

from ..config import AppSettings
from ..models import EvidenceSource, Freshness, RetrievalLane


class ExternalResult(BaseModel):
    """Manual external-skill result."""

    sources: list[EvidenceSource] = Field(default_factory=list)
    latency_ms: int = Field(ge=0)
    detail: str
    ok: bool


class ExternalSkillClient:
    """Invoke allowlisted sibling research skill runners."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    async def retrieve(self, lane: RetrievalLane, query: str) -> ExternalResult:
        """Execute one manual Brave or Dogpile request."""

        derived_query = derive_manual_search_query(query)
        if not derived_query:
            return ExternalResult(sources=[], latency_ms=0, detail="No bounded manual query", ok=False)
        if lane is RetrievalLane.BRAVE:
            runner = self._settings.brave_runner
            args = ["web", derived_query, "--count", "5"]
        elif lane is RetrievalLane.DOGPILE:
            runner = self._settings.dogpile_runner
            args = ["search", derived_query]
        else:
            return ExternalResult(sources=[], latency_ms=0, detail="Unsupported external lane", ok=False)
        if runner is None:
            return ExternalResult(
                sources=[],
                latency_ms=0,
                detail=f"{lane.value} runner not configured",
                ok=False,
            )
        return await asyncio.to_thread(self._run, runner, lane, args, derived_query)

    def _run(
        self,
        runner: Path,
        lane: RetrievalLane,
        args: list[str],
        query: str,
    ) -> ExternalResult:
        started = monotonic()
        try:
            result = subprocess.run(
                [str(runner), *args],
                check=False,
                capture_output=True,
                text=True,
                timeout=max(self._settings.subprocess_timeout_s, 30.0),
                env=child_env(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return ExternalResult(
                sources=[],
                latency_ms=int((monotonic() - started) * 1000),
                detail=f"{type(exc).__name__}",
                ok=False,
            )
        latency_ms = int((monotonic() - started) * 1000)
        if result.returncode != 0:
            return ExternalResult(
                sources=[],
                latency_ms=latency_ms,
                detail=f"exit {result.returncode}",
                ok=False,
            )
        sources = _parse_external(lane, query, result.stdout)
        return ExternalResult(
            sources=sources,
            latency_ms=latency_ms,
            detail=f"{lane.value} {len(sources)}",
            ok=bool(sources),
        )


def _parse_external(lane: RetrievalLane, query: str, stdout: str) -> list[EvidenceSource]:
    text = stdout.strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return [
            EvidenceSource(
                lane=lane,
                label=f"{lane.value.title()} result",
                excerpt=text[:4_000],
                score=0.50,
                freshness=Freshness.EXTERNAL,
                url=f"manual:{lane.value}:{query[:120]}",
                metadata={"manual": True},
            )
        ]
    candidates: list[Any]
    if isinstance(payload, list):
        candidates = payload
    elif isinstance(payload, dict):
        candidates = payload.get("results") or payload.get("web", {}).get("results") or [payload]
    else:
        candidates = []
    sources: list[EvidenceSource] = []
    for item in candidates[:8]:
        if not isinstance(item, dict):
            continue
        excerpt = _first_text(item, "description", "snippet", "text", "content", "title")
        url = _first_text(item, "url", "link")
        if not excerpt:
            continue
        sources.append(
            EvidenceSource(
                lane=lane,
                label=_first_text(item, "title", "name") or f"{lane.value.title()} result",
                excerpt=excerpt[:4_000],
                score=0.55,
                freshness=Freshness.EXTERNAL,
                url=url or f"manual:{lane.value}:{query[:120]}",
                metadata={"manual": True},
            )
        )
    return sources


def derive_manual_search_query(text: str, *, max_chars: int = 180) -> str:
    """Derive a bounded external-search query from a question, not transcript history."""

    clean = " ".join(text.split())
    if not clean:
        return ""
    question_matches = re.findall(r"([^?.!]{8,}\?)", clean)
    candidate = question_matches[-1] if question_matches else clean
    candidate = re.sub(r"(?i)\b(interviewer|candidate|graham|speaker\s*\d+)\s*:\s*", "", candidate)
    candidate = candidate.strip(" -:;,.")
    return candidate[:max_chars].rstrip(" -:;,.")


def _first_text(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())
    return ""
