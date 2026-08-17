"""Transcript-to-LeetCode answerability gate.

The gate is intentionally a subprocess boundary to keep the sibling skill
independently testable. Live Evidence supplies only a stable question candidate
and optional clarification answers; it never sends raw meeting history.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
from pathlib import Path
from time import monotonic
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..config import AppSettings


class LeetCodeGateResult(BaseModel):
    """One transcript-to-leetcode analysis result."""

    model_config = ConfigDict(extra="allow")

    status: str
    solution_allowed: bool = False
    solver_prompt: str | None = None
    transcript_sha256: str | None = None
    clarifying_questions: list[dict[str, Any]] = Field(default_factory=list)
    selected_span: dict[str, Any] | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int = Field(ge=0)
    ok: bool = False
    detail: str

    @property
    def solver_prompt_sha256(self) -> str | None:
        if not self.solver_prompt:
            return None
        return hashlib.sha256(self.solver_prompt.encode("utf-8")).hexdigest()


class TranscriptToLeetCodeClient:
    """Run the sibling transcript-to-leetcode analyzer."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    async def analyze(
        self,
        question_candidate: dict[str, Any],
        *,
        answers: dict[str, str] | None = None,
    ) -> LeetCodeGateResult:
        runner = self._settings.leetcode_runner
        if runner is None:
            return LeetCodeGateResult(
                status="needs_clarification",
                solution_allowed=False,
                payload={},
                latency_ms=0,
                ok=False,
                detail="transcript-to-leetcode runner not configured",
            )
        return await asyncio.to_thread(self._run, runner, question_candidate, answers or {})

    def _run(
        self,
        runner: Path,
        question_candidate: dict[str, Any],
        answers: dict[str, str],
    ) -> LeetCodeGateResult:
        started = monotonic()
        command = [
            str(runner),
            "-",
            "--compact",
            "--language",
            "Python 3",
        ]
        if answers:
            command.extend(["--answers", json.dumps(answers, sort_keys=True)])
        try:
            result = subprocess.run(
                command,
                input=json.dumps(question_candidate, sort_keys=True),
                check=False,
                capture_output=True,
                env=_subprocess_env(),
                text=True,
                timeout=self._settings.subprocess_timeout_s,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return LeetCodeGateResult(
                status="needs_clarification",
                solution_allowed=False,
                payload={},
                latency_ms=int((monotonic() - started) * 1000),
                ok=False,
                detail=f"{type(exc).__name__}",
            )

        latency_ms = int((monotonic() - started) * 1000)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
            return LeetCodeGateResult(
                status="needs_clarification",
                solution_allowed=False,
                payload={},
                latency_ms=latency_ms,
                ok=False,
                detail=detail[:300],
            )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            return LeetCodeGateResult(
                status="needs_clarification",
                solution_allowed=False,
                payload={},
                latency_ms=latency_ms,
                ok=False,
                detail=f"malformed analyzer output: {exc}",
            )
        if not isinstance(payload, dict):
            return LeetCodeGateResult(
                status="needs_clarification",
                solution_allowed=False,
                payload={},
                latency_ms=latency_ms,
                ok=False,
                detail="malformed analyzer output: expected object",
            )
        status = str(payload.get("status") or "needs_clarification")
        solution_allowed = bool(payload.get("solution_allowed"))
        solver_prompt = payload.get("solver_prompt") if isinstance(payload.get("solver_prompt"), str) else None
        if solution_allowed and not solver_prompt:
            status = "needs_clarification"
            solution_allowed = False
        questions = payload.get("clarifying_questions")
        return LeetCodeGateResult(
            status=status,
            solution_allowed=solution_allowed,
            solver_prompt=solver_prompt,
            transcript_sha256=payload.get("transcript_sha256")
            if isinstance(payload.get("transcript_sha256"), str)
            else None,
            clarifying_questions=questions if isinstance(questions, list) else [],
            selected_span=payload.get("selected_span") if isinstance(payload.get("selected_span"), dict) else None,
            payload=payload,
            latency_ms=latency_ms,
            ok=True,
            detail=f"transcript-to-leetcode {status}",
        )


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT", "PYTHONHOME", "PYTHONPATH"):
        env.pop(key, None)
    env.setdefault("UV_LINK_MODE", "copy")
    return env
