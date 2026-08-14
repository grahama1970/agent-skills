"""Ask-backed code-question solving.

The Ask lane is downstream of local retrieval. It receives only the active
interviewer question plus a small, source-bound evidence packet, then preserves
the Ask run directory as the solution receipt.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path
from time import monotonic
from typing import Any

from pydantic import BaseModel, Field

from ..config import AppSettings
from ..models import EvidenceSource, Freshness, RetrievalLane


class AskSolutionResult(BaseModel):
    """One Ask solution attempt with explicit degradation."""

    sources: list[EvidenceSource] = Field(default_factory=list)
    latency_ms: int = Field(ge=0)
    detail: str
    ok: bool


class AskSolutionClient:
    """Invoke the sibling Ask runtime for bounded code-question solutions."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    async def solve(self, query: str, evidence: list[EvidenceSource]) -> AskSolutionResult:
        """Return an Ask-authored solution source when the runner is configured."""

        runner = self._settings.ask_runner
        if runner is None:
            return AskSolutionResult(
                sources=[],
                latency_ms=0,
                detail="Ask runner not configured",
                ok=False,
            )
        prompt = _build_prompt(query, evidence)
        return await asyncio.to_thread(self._run, runner, prompt, query, evidence)

    def _run(
        self,
        runner: Path,
        prompt: str,
        query: str,
        evidence: list[EvidenceSource],
    ) -> AskSolutionResult:
        started = monotonic()
        command = [
            str(runner),
            "tau-dag",
            prompt,
            "--repo",
            "local/live-evidence",
            "--target",
            "live-evidence-code-question",
            "--immutable-goal",
            "Return a concise code-question solution grounded only in the supplied evidence, with receipt-backed Ask artifacts.",
            "--dag-template",
            "single-call",
            "--handler",
            self._settings.ask_handler,
            "--execute",
            "--json",
        ]
        if self._settings.ask_allow_provider_calls:
            command.append("--allow-provider-calls")
        env = os.environ.copy()
        env.pop("UV_PROJECT_ENVIRONMENT", None)
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                env=env,
                text=True,
                timeout=self._settings.ask_timeout_s,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return AskSolutionResult(
                sources=[],
                latency_ms=int((monotonic() - started) * 1000),
                detail=f"{type(exc).__name__}",
                ok=False,
            )

        latency_ms = int((monotonic() - started) * 1000)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
            return AskSolutionResult(sources=[], latency_ms=latency_ms, detail=detail[:240], ok=False)

        payload = _parse_json_output(result.stdout)
        run_dir = _find_run_dir(payload)
        response = _read_ask_response(run_dir) if run_dir else ""
        if not response:
            response = _response_from_payload(payload) or result.stdout.strip()
        response = " ".join(response.split())
        if not response:
            return AskSolutionResult(
                sources=[],
                latency_ms=latency_ms,
                detail="Ask returned no response text",
                ok=False,
            )

        source = EvidenceSource(
            lane=RetrievalLane.ASK,
            label="Ask code solution",
            excerpt=response[:4_000],
            score=0.93,
            freshness=Freshness.UNKNOWN,
            repository="ask",
            path=str(run_dir) if run_dir else None,
            metadata={
                "handler": self._settings.ask_handler,
                "run_dir": str(run_dir) if run_dir else None,
                "seed_source_count": len(evidence),
                "query": query[:500],
            },
        )
        return AskSolutionResult(
            sources=[source],
            latency_ms=latency_ms,
            detail=f"Ask solution ({self._settings.ask_handler})",
            ok=True,
        )


def _build_prompt(query: str, evidence: list[EvidenceSource]) -> str:
    bounded = evidence[:4]
    evidence_lines = []
    for index, source in enumerate(bounded, start=1):
        evidence_lines.append(
            "\n".join(
                [
                    f"Evidence {index}:",
                    f"lane: {source.lane.value}",
                    f"locator: {_safe_locator(source)}",
                    f"excerpt: {' '.join(source.excerpt.split())[:900]}",
                ]
            )
        )
    evidence_block = "\n\n".join(evidence_lines) or "No local source evidence was found."
    return "\n\n".join(
        [
            "You are answering a live coding interview question for Graham.",
            "If the question is a general algorithm prompt, solve it directly from the prompt.",
            "Use supplied source evidence only for repo-specific claims. If source evidence is insufficient for a repo claim, say exactly what is missing.",
            "Return a concise solution the human can scan in real time: approach, code sketch or pseudocode, complexity, and one caution.",
            f"Question: {' '.join(query.split())[:1200]}",
            evidence_block,
        ]
    )


def _safe_locator(source: EvidenceSource) -> str:
    if source.repository and source.path:
        return f"{source.repository}/{Path(source.path).name}:{source.line_start or ''}".rstrip(":")
    if source.path:
        return f"{Path(source.path).name}:{source.line_start or ''}".rstrip(":")
    if source.url:
        return source.url[:500]
    return source.label[:500]


def _parse_json_output(stdout: str) -> Any:
    text = stdout.strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        for line in reversed(text.splitlines()):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return {"response": text}


def _find_run_dir(payload: Any) -> Path | None:
    if isinstance(payload, dict):
        for key in ("run_dir", "run_directory", "output_dir"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return Path(value).expanduser().resolve()
        for value in payload.values():
            found = _find_run_dir(value)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _find_run_dir(item)
            if found is not None:
                return found
    return None


def _read_ask_response(run_dir: Path | None) -> str:
    if run_dir is None or not run_dir.is_dir():
        return ""
    candidates = sorted(run_dir.glob("node-artifacts/handler-*/response.md"))
    candidates.extend(sorted(run_dir.glob("node-artifacts/*/response.md")))
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            return text
    return ""


def _response_from_payload(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("response", "answer", "text", "content"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value
        for value in payload.values():
            found = _response_from_payload(value)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _response_from_payload(item)
            if found:
                return found
    return ""
