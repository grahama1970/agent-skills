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
from pathlib import Path
from typing import Any

TAU_REPO = Path(os.environ.get("TAU_REPO", os.path.expanduser("~/workspace/experiments/tau")))
TAU_TEXT_MODULE = "tau_coding.persona_dream_text_reasoning_agent"
DEFAULT_MODEL = os.environ.get("PERSONA_DREAM_SCILLM_MODEL", "gpt-5.5")


class TauRoutingError(RuntimeError):
    """Raised when the Tau text-reasoning node cannot be reached or fails."""


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
    """Route one text-reasoning prompt through the Tau node.

    Returns ``(parsed_json, tau_receipt)``. ``parsed_json`` is ``None`` when the
    node did not return a parseable JSON object (fail-closed for the caller).
    """
    tau_repo = tau_repo or TAU_REPO
    if not tau_repo.exists():
        raise TauRoutingError(f"Tau repo not found: {tau_repo}")

    request = {
        "prompt": prompt,
        "role": role,
        "model": model or DEFAULT_MODEL,
        "caller_skill": caller_skill,
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

    try:
        stdout, stderr = proc.communicate(json.dumps(request), timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=5)
        except Exception:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                pass
        raise TauRoutingError(f"Tau dispatch timed out after {timeout_s}s") from exc

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


def receipt_provenance(receipt: dict[str, Any]) -> dict[str, Any]:
    """Compact provenance summary of a Tau text-reasoning receipt for phase output."""
    return {
        "route": "tau:persona-dream-text-reasoning",
        "tau_receipt_schema": receipt.get("schema"),
        "model": receipt.get("model"),
        "api_key_source": receipt.get("api_key_source"),
        "prompt_sha256": receipt.get("prompt_sha256"),
        "output_contract_sha256": receipt.get("output_contract_sha256"),
        "http_status": receipt.get("http_status"),
        "status": receipt.get("status"),
        "live_call_performed": receipt.get("live_call_performed"),
    }
