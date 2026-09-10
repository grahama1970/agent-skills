#!/usr/bin/env python3
"""Persona-dream -> Tau text-reasoning adapter.

Standing operator architecture rule: only Tau may reach scillm. Persona-dream
phases 13/14 must NOT POST to scillm directly. This adapter is the single
persona-dream-side dispatch point: it hands a caller-authored prompt (and an
optional caller-defined JSON output contract) to the sanctioned Tau text
reasoning node

    tau_coding.persona_dream_text_reasoning_agent

by subprocessing ``uv run python -m ...`` inside the Tau repo, captures the Tau
receipt (api_key_source, prompt_sha256, model, raw response_content) and returns
the parsed JSON object plus that receipt.

This module performs ZERO LLM/scillm calls of its own - it only invokes Tau.
Deterministic citation/grounding validation stays entirely in phase 13/14: the
LLM (through Tau) only DRAFTS; code decides admissibility.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
from pathlib import Path
from typing import Any

TAU_REPO = Path(os.environ.get("TAU_REPO", os.path.expanduser("~/workspace/experiments/tau")))
TAU_TEXT_MODULE = "tau_coding.persona_dream_text_reasoning_agent"
DEFAULT_MODEL = os.environ.get("PERSONA_DREAM_SCILLM_MODEL", "gpt-5.5")
# Quota walls on one provider must fall through to the next funded lane
# (operator 2026-09-10: zai GLM when codex-oauth hits its usage limit).
DEFAULT_CHAIN = "gpt-5.5,zai-glm,zai-glm-flash"


def _model_chain(model: str | None) -> list[str]:
    chain = [m.strip() for m in os.environ.get("PERSONA_DREAM_SCILLM_MODEL_CHAIN", DEFAULT_CHAIN).split(",") if m.strip()]
    if model:
        if model in chain:
            chain = chain[chain.index(model):]
        else:
            chain = [model] + chain
    # de-dup, preserve order
    seen: set[str] = set()
    ordered = [m for m in chain if not (m in seen or seen.add(m))]
    return ordered


class TauRoutingError(RuntimeError):
    """Raised when the Tau text-reasoning node cannot be reached or fails."""


class _WallClockTimeout(TimeoutError):
    """Raised when the adapter-level wall-clock guard expires."""


def _install_wall_clock_timeout(timeout_s: float):
    if timeout_s <= 0 or threading.current_thread() is not threading.main_thread():
        return None

    previous_handler = signal.getsignal(signal.SIGALRM)

    def _raise_timeout(_signum, _frame):
        raise _WallClockTimeout(f"Tau dispatch wall-clock timeout after {timeout_s}s")

    signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, timeout_s)
    return previous_handler


def _clear_wall_clock_timeout(previous_handler: Any) -> None:
    if previous_handler is None:
        return
    signal.setitimer(signal.ITIMER_REAL, 0)
    signal.signal(signal.SIGALRM, previous_handler)


def _terminate_process_group(proc: subprocess.Popen[str]) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=5)
    except Exception:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except Exception:
            pass


def _arm_process_group_timeout(proc: subprocess.Popen[str], timeout_s: float) -> tuple[threading.Timer | None, threading.Event]:
    timed_out = threading.Event()
    if timeout_s <= 0:
        return None, timed_out

    def _timeout() -> None:
        timed_out.set()
        _terminate_process_group(proc)

    timer = threading.Timer(timeout_s, _timeout)
    timer.daemon = True
    timer.start()
    return timer, timed_out


def _dispatch_once(
    prompt: str,
    role: str,
    *,
    output_contract: dict[str, Any] | None = None,
    caller_skill: str = "persona-dream",
    model: str | None = None,
    timeout_s: float = 240.0,
    tau_repo: Path | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Route one text-reasoning prompt through the Tau node (single model)."""
    tau_repo = tau_repo or TAU_REPO
    if not tau_repo.exists():
        raise TauRoutingError(f"Tau repo not found: {tau_repo}")

    request = {
        "prompt": prompt,
        "role": role,
        "model": model or DEFAULT_MODEL,
        "caller_skill": caller_skill,
        "timeout_s": timeout_s,
    }
    if output_contract is not None:
        request["output_contract"] = output_contract

    try:
        proc = subprocess.Popen(
            ["uv", "run", "python", "-m", TAU_TEXT_MODULE],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(tau_repo),
            start_new_session=True,
        )
    except OSError as exc:
        raise TauRoutingError(f"Tau dispatch failed: {exc}") from exc

    previous_alarm_handler = _install_wall_clock_timeout(timeout_s)
    timer, timer_timed_out = _arm_process_group_timeout(proc, timeout_s)
    try:
        stdout, stderr = proc.communicate(json.dumps(request), timeout=timeout_s)
    except (subprocess.TimeoutExpired, _WallClockTimeout) as exc:
        _terminate_process_group(proc)
        raise TauRoutingError(f"Tau dispatch timed out after {timeout_s}s") from exc
    finally:
        if timer is not None:
            timer.cancel()
        _clear_wall_clock_timeout(previous_alarm_handler)
    if timer_timed_out.is_set():
        raise TauRoutingError(f"Tau dispatch timed out after {timeout_s}s")

    stdout = stdout.strip()
    if not stdout:
        raise TauRoutingError(
            f"Tau node returned no receipt (rc={proc.returncode}): {stderr[-500:]}"
        )
    try:
        receipt = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise TauRoutingError(f"Tau receipt not JSON: {exc}; stderr={stderr[-300:]}") from exc

    if receipt.get("schema") != "tau.persona_dream.scillm_text_reasoning_receipt.v1":
        raise TauRoutingError(f"Unexpected Tau receipt schema: {receipt.get('schema')!r}")

    parsed = receipt.get("parsed_json") if receipt.get("status") == "PASS" else None
    return parsed, receipt


def dispatch_text_reasoning(
    prompt: str,
    role: str,
    *,
    output_contract: dict[str, Any] | None = None,
    caller_skill: str = "persona-dream",
    model: str | None = None,
    timeout_s: float = 240.0,
    tau_repo: Path | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Route one text-reasoning prompt through the Tau node with model fallback.

    Tries each model in the chain (default ``gpt-5.5,zai-glm,zai-glm-flash``;
    override with ``PERSONA_DREAM_SCILLM_MODEL_CHAIN``). A quota/rate-limited
    model (429 / exhausted groups) falls through to the next funded lane;
    ``TauRoutingError`` still raises. Returns ``(parsed_json, tau_receipt)``;
    the receipt carries ``model_chain`` and ``model_fallback_attempts``.
    """
    chain = _model_chain(model)
    attempts: list[dict[str, Any]] = []
    last_receipt: dict[str, Any] = {}
    for candidate in chain:
        parsed, receipt = _dispatch_once(
            prompt, role,
            output_contract=output_contract,
            caller_skill=caller_skill,
            model=candidate,
            timeout_s=timeout_s,
            tau_repo=tau_repo,
        )
        if parsed is not None:
            receipt = dict(receipt)
            receipt["model_chain"] = chain
            receipt["model_fallback_attempts"] = attempts
            return parsed, receipt
        attempts.append({
            "model": candidate,
            "http_status": receipt.get("http_status"),
            "error": str(receipt.get("error"))[:300],
        })
        last_receipt = receipt
    final = dict(last_receipt)
    final["model_chain"] = chain
    final["model_fallback_attempts"] = attempts
    return None, final


def receipt_provenance(receipt: dict[str, Any]) -> dict[str, Any]:
    """Compact provenance summary of a Tau text-reasoning receipt for phase output."""
    return {
        "route": "tau:persona-dream-text-reasoning",
        "tau_receipt_schema": receipt.get("schema"),
        "model": receipt.get("model"),
        "api_key_source": receipt.get("api_key_source"),
        "model_fallback_attempts": receipt.get("model_fallback_attempts"),
        "prompt_sha256": receipt.get("prompt_sha256"),
        "output_contract_sha256": receipt.get("output_contract_sha256"),
        "http_status": receipt.get("http_status"),
        "status": receipt.get("status"),
        "live_call_performed": receipt.get("live_call_performed"),
    }
