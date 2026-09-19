"""Privacy-gated Jev shadow classification for approved Python source.

This adapter invokes the existing Jev skill rather than duplicating its provider
client. Every attempt writes an ai_detection.jev_shadow.v1 receipt. Jev remains
advisory: its answer never changes detector output, Battle scoring, or release
status. Provider upload requires an explicit per-call authorization flag.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_detection.io import atomic_json, digest

PINNED_JEV_MODEL = "jev-1.13.0"


class JevAnswer(BaseModel):
    type: Literal["choice"]
    choice: Literal["machine_signal", "human_signal", "mixed_signal", "insufficient_evidence"]
    probabilities: dict[str, float]
    confidence: float = Field(ge=0, le=1)


class JevReceipt(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    schema_name: Literal["jev.receipt.v1"] = Field(alias="schema")
    decision: Literal["accept", "abstain"]
    answers: dict[str, JevAnswer]
    bindings: dict[str, Any]
    took_ms: int = Field(ge=0)


class ShadowReceipt(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    schema_name: Literal["ai_detection.jev_shadow.v1"] = Field(
        default="ai_detection.jev_shadow.v1", alias="schema")
    outcome: Literal["accepted", "abstained", "blocked", "failed"]
    advisory_only: Literal[True] = True
    production_disposition_changed: Literal[False] = False
    battle_authority: Literal[False] = False
    provider_upload_authorized: bool
    source_sha256: str
    model: str = PINNED_JEV_MODEL
    jev_receipt: JevReceipt | None = None
    error: str | None = None


def run_shadow(source: Path, output: Path, *, allow_provider_upload: bool,
               agent_skills_root: Path) -> ShadowReceipt:
    """Run one pinned Jev shadow call and retain a durable outcome receipt."""
    text = source.read_text(encoding="utf-8")
    source_sha256 = digest(text.encode())
    if not allow_provider_upload:
        receipt = ShadowReceipt(outcome="blocked", provider_upload_authorized=False,
                                source_sha256=source_sha256,
                                error="Explicit --allow-provider-upload is required.")
        atomic_json(output, receipt.model_dump(mode="json", by_alias=True))
        return receipt

    jev = agent_skills_root / "skills" / "jev" / "run.sh"
    questions = Path(__file__).resolve().parents[2] / "research" / "jev_code_authorship.v1.json"
    if not jev.is_file() or not questions.is_file():
        receipt = ShadowReceipt(outcome="failed", provider_upload_authorized=True,
                                source_sha256=source_sha256,
                                error="Jev skill or frozen question map is unavailable.")
        atomic_json(output, receipt.model_dump(mode="json", by_alias=True))
        return receipt

    state = output.with_suffix(".state.json")
    provider_receipt = output.with_suffix(".jev.json")
    atomic_json(state, {"language": "python", "source": text})
    env = os.environ.copy()
    env["JEV_MODEL"] = PINNED_JEV_MODEL
    command = [str(jev), "ask", "--questions", f"@{questions}", "--state", f"@{state}",
               "--allow-egress", "--out", str(provider_receipt)]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=20,
                                   check=False, env=env)
        if provider_receipt.is_file():
            parsed = JevReceipt.model_validate_json(provider_receipt.read_text(encoding="utf-8"))
            outcome = "accepted" if parsed.decision == "accept" else "abstained"
            receipt = ShadowReceipt(outcome=outcome, provider_upload_authorized=True,
                                    source_sha256=source_sha256, jev_receipt=parsed)
        else:
            detail = completed.stdout.strip() or completed.stderr.strip() or "Jev returned no receipt."
            receipt = ShadowReceipt(outcome="abstained" if completed.returncode == 3 else "failed",
                                    provider_upload_authorized=True, source_sha256=source_sha256,
                                    error=detail[:1000])
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        receipt = ShadowReceipt(outcome="failed", provider_upload_authorized=True,
                                source_sha256=source_sha256, error=str(exc)[:1000])
    finally:
        state.unlink(missing_ok=True)
    atomic_json(output, receipt.model_dump(mode="json", by_alias=True))
    return receipt
