"""Ask-backed code-question solving.

The Ask lane is downstream of local retrieval. It receives only the active
interviewer question plus a small, source-bound evidence packet, then preserves
the Ask run directory as the solution receipt.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess

from .subprocess_env import child_env
from pathlib import Path
from time import monotonic
from typing import Any

from pydantic import BaseModel, Field

from ..config import AppSettings
from ..reviewed_answer import binding_text, read_reviewed_answer
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

    async def solve(self, query: str, evidence: list[EvidenceSource], *, binding: dict | None = None) -> AskSolutionResult:
        """Return an Ask-authored solution source when the runner is configured."""

        runner = self._settings.ask_runner
        if runner is None:
            return AskSolutionResult(
                sources=[],
                latency_ms=0,
                detail="Ask runner not configured",
                ok=False,
            )
        if not binding:
            return AskSolutionResult(sources=[], latency_ms=0, detail="Review binding required", ok=False)
        prompt = _build_prompt(query, evidence) + '\n\n' + binding_text(binding) + (
            '\nROLE CONTRACT: The first handler is CREATOR, not reviewer. Return the complete '
            'answer inside ## Position, at most 2400 characters including all outer sections. '
            'Use the five required ### subheadings below even for trivial functions. '
            'Keep ## Evidence, ## Uncertainties and ## Blockers brief. Preserve code fences. '
            'Outside code fences and headings, use only short bullets (at most 120 characters each), '
            'including APPROACH, COMPLEXITY, Evidence, Uncertainties and Blockers. No prose paragraphs. '
            'The second handler is REVIEWER: perform a pass/fail review of the PRIOR CREATOR '
            'response, not of an answer you write yourself. Reject if any required subheading '
            '(### APPROACH, ### PSEUDOCODE, ### CODE, ### COMPLEXITY, ### OPTIMIZATIONS) is missing '
            'or empty, if code is incomplete, or claims are unsupported. Do not repair or rewrite '
            'the answer in your review. End with VERDICT: PASS or VERDICT: FAIL.'
        )
        return await asyncio.to_thread(self._run, runner, prompt, query, evidence, binding)

    def _run(
        self,
        runner: Path,
        prompt: str,
        query: str,
        evidence: list[EvidenceSource],
        binding: dict,
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
            "creator-reviewer",
            "--handler",
            self._settings.ask_handler,
            "--handler",
            os.getenv("LIVE_EVIDENCE_ASK_REVIEWER_HANDLER", "claude-fable-low"),
            "--topology",
            "sequential",
            "--execute",
            "--json",
        ]
        if self._settings.ask_allow_provider_calls:
            command.append("--allow-provider-calls")
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self._settings.ask_timeout_s,
                env=child_env(),
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
            failed_dir = _find_run_dir(_parse_json_output(result.stdout))
            detail = f"Ask failed (exit {result.returncode}); run_dir={failed_dir}" if failed_dir else (
                result.stderr.strip() or f"exit {result.returncode}")
            return AskSolutionResult(sources=[], latency_ms=latency_ms, detail=detail[:1000], ok=False)

        payload = _parse_json_output(result.stdout)
        run_dir = _find_run_dir(payload)
        try:
            if run_dir is None:
                raise ValueError("Ask run directory missing")
            response, approval = read_reviewed_answer(run_dir, binding)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return AskSolutionResult(sources=[], latency_ms=latency_ms,
                                     detail=f"Review not admitted: {exc}", ok=False)
        # Preserve line structure. Collapsing whitespace here destroyed every
        # fenced code block in the solver response before it reached the card,
        # so the browser's ```lang\n...``` extractor could never match and the
        # HUD fell back to a hard-coded implementation instead. Callers that
        # need a flattened form normalize at their own use site.
        response = response.strip()
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
                "answer_review": approval,
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
                    f"excerpt:\n{_source_context(source)}",
                ]
            )
        )
    evidence_block = "\n\n".join(evidence_lines) or "No local source evidence was found."
    return "\n\n".join(
        [
            "You are supporting Graham live in a coding interview. He is speaking "
            "while he reads this, so it must be scannable in a glance.",
            "Use only the supplied source evidence. If it is insufficient, say exactly what is missing.",
            # A candidate states the approach, walks pseudo-code, then writes real
            # code, then discusses trade-offs. Emitting the final implementation
            # first gives him nothing to say while he types.
            "Inside Ask's mandatory ## Position section, use these five subsections in order. "
            "They are required inside Position, not replacements for Ask's outer headings:",
            "\n".join(
                [
                    "### APPROACH",
                    "One or two lines naming the data structure and the invariant. This is what he says out loud first.",
                    "",
                    "### PSEUDOCODE",
                    "A fenced block, language-agnostic, 5-12 lines. Steps he can narrate while writing real code.",
                    "",
                    "### CODE",
                    "A fenced block with a language tag. Complete and runnable, no ellipses.",
                    "",
                    "### COMPLEXITY",
                    "One line: time and space, with the reason.",
                    "",
                    "### OPTIMIZATIONS",
                    "2-4 bullets. What to improve, and the follow-up questions an interviewer is "
                    "most likely to ask NEXT about this problem (harder constraints, streaming "
                    "input, memory limits, edge cases). These are what he should be ready for.",
                ]
            ),
            f"Question: {' '.join(query.split())[:1200]}",
            evidence_block,
        ]
    )


def _source_context(source: EvidenceSource) -> str:
    """Expand current ripgrep hits for the solver without reading outside the cited root."""
    if source.lane is RetrievalLane.RIPGREP and source.path and source.metadata.get("root"):
        try:
            path = Path(source.path).resolve(strict=True)
            root = Path(source.metadata["root"]).resolve(strict=True)
            if path.is_relative_to(root) and path.stat().st_size <= 262144:
                content = path.read_bytes()
                if hashlib.sha256(content).hexdigest() != source.metadata.get("content_sha256"):
                    return "Cited source changed after retrieval; do not use it."
                lines = content.decode("utf-8").splitlines()
                start = max(0, (source.line_start or 1) - 6)
                excerpt = "\n".join(lines[start:start + 35])
                if len(excerpt) <= 3000:
                    return f"Current file lines {start + 1}-{start + len(lines[start:start + 35])}:\n{excerpt}"
        except (OSError, ValueError, UnicodeError):
            return "Cited current source could not be verified; do not use it."
    return source.excerpt[:900]


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
