#!/usr/bin/env python3
"""Persona-dream -> Tau VLM (panel-reviewer) adapter.

Standing operator architecture rule: only Tau may reach scillm. Persona-dream
drivers must NOT POST images to scillm directly. This adapter is the single
persona-dream-side VLM dispatch point: it hands one local image + a
hash-recorded evidence-only review prompt to the sanctioned Tau panel-reviewer
VLM path

    tau_coding.persona_dream_panel_agent._review_panel_image_with_scillm

by importing it inside the Tau repo's own environment via ``uv run python`` and
returning the Tau ``scillm_vlm_review_receipt.v1`` receipt (http_status,
api_key_source, review_prompt_sha256, response_content, parsed fields).

This module performs ZERO LLM/VLM/scillm calls of its own - Tau owns scillm
access. Deterministic evidence handling (psychology filtering, packet assembly)
stays entirely on the persona-dream side; the VLM only DESCRIBES.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

TAU_REPO = Path(os.environ.get("TAU_REPO", os.path.expanduser("~/workspace/experiments/tau")))
DEFAULT_MODEL = os.environ.get("PERSONA_DREAM_VLM_MODEL", "gpt-5.5")

# Inline driver executed inside the Tau repo environment. Reads a JSON request
# on stdin, invokes the sanctioned panel-reviewer VLM function, prints the
# receipt as JSON on stdout.
_TAU_DRIVER = r"""
import json, sys
from pathlib import Path
from tau_coding import persona_dream_panel_agent as pa
req = json.load(sys.stdin)
panel = {
    "image_path": req["image_path"],
    "visual_review_prompt": req["prompt"],
    "scillm_vlm_model": req.get("model") or "gpt-5.5",
}
artifact_dir = Path(req["artifact_dir"])
artifact_dir.mkdir(parents=True, exist_ok=True)
receipt = pa._review_panel_image_with_scillm(panel, artifact_dir)
sys.stdout.write(json.dumps(receipt))
"""


class TauVlmRoutingError(RuntimeError):
    """Raised when the Tau panel-reviewer VLM node cannot be reached or fails."""


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def dispatch_vlm_review(
    image_path: str | Path,
    prompt: str,
    *,
    artifact_dir: str | Path,
    model: str | None = None,
    timeout_s: float = 240.0,
    tau_repo: Path | None = None,
) -> dict[str, Any]:
    """Route one single-image VLM review through the Tau panel-reviewer node.

    Returns the Tau ``scillm_vlm_review_receipt.v1`` receipt dict. The caller
    inspects ``http_status`` / ``live_call_performed`` and fails closed if the
    route did not return HTTP 200.
    """
    tau_repo = tau_repo or TAU_REPO
    if not tau_repo.exists():
        raise TauVlmRoutingError(f"Tau repo not found: {tau_repo}")
    image_path = Path(image_path).resolve()
    if not image_path.is_file():
        raise TauVlmRoutingError(f"Image not found: {image_path}")

    request = {
        "image_path": str(image_path),
        "prompt": prompt,
        "model": model or DEFAULT_MODEL,
        "artifact_dir": str(Path(artifact_dir).resolve()),
    }
    try:
        proc = subprocess.run(
            ["uv", "run", "python", "-c", _TAU_DRIVER],
            input=json.dumps(request),
            capture_output=True,
            text=True,
            cwd=str(tau_repo),
            timeout=timeout_s,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TauVlmRoutingError(f"Tau VLM dispatch failed: {exc}") from exc

    stdout = proc.stdout.strip()
    if not stdout:
        raise TauVlmRoutingError(
            f"Tau VLM node returned no receipt (rc={proc.returncode}): {proc.stderr[-500:]}"
        )
    try:
        receipt = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise TauVlmRoutingError(
            f"Tau VLM receipt not JSON: {exc}; stderr={proc.stderr[-300:]}"
        ) from exc

    if receipt.get("schema") != "tau.persona_dream.scillm_vlm_review_receipt.v1":
        raise TauVlmRoutingError(f"Unexpected Tau VLM receipt schema: {receipt.get('schema')!r}")
    return receipt


def receipt_provenance(receipt: dict[str, Any], *, purpose: str, frame_index: int | None = None) -> dict[str, Any]:
    """Compact tau_receipt entry for the observation packet's tau_receipts list."""
    content = receipt.get("response_content") or ""
    return {
        "route": "tau:persona-dream-panel-reviewer",
        "purpose": purpose,
        "model": receipt.get("model"),
        "api_key_source": receipt.get("api_key_source"),
        "prompt_sha256": receipt.get("review_prompt_sha256"),
        "content_sha256": "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "http_status": receipt.get("http_status"),
        "live_call_performed": receipt.get("live_call_performed"),
        "frame_index": frame_index,
    }
