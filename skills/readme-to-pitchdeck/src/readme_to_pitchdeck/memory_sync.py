"""Store an emitted UI deck bundle into /memory (ArangoDB) via the memory skill CLI.

Inputs: a deck.data.json produced by `emit-ui` (validated against UiDeckBundle
before anything is sent). Output: one memory document per deck, tagged for
`/memory recall`, stored exclusively through `skills/memory/run.sh learn` —
this module never touches ArangoDB directly (ArangoDB access policy).
Failure modes: missing/invalid bundle raises ValueError; a failing memory CLI
call raises RuntimeError with the captured stderr.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from loguru import logger

from .models import OperationClaims, OperationReceipt, Readiness, SeamValidation
from .ui_emitter import UiDeckBundle

MEMORY_TIMEOUT_S = 60


def _memory_run_sh() -> Path:
    override = os.environ.get("README_TO_PITCHDECK_MEMORY_RUN")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3] / "memory" / "run.sh"


def _deck_summary(bundle: UiDeckBundle) -> tuple[str, str]:
    problem = (
        f"What does the '{bundle.title}' pitch deck ({bundle.deck_id}) claim, "
        f"and what is its claim-review state?"
    )
    slide_lines = [
        f"{slide.order}. [{slide.layout}] {slide.title} — {slide.message}"
        for slide in bundle.slides
    ]
    claim_state = ", ".join(f"{count} {status}" for status, count in sorted(bundle.claim_summary.items()))
    solution = "\n".join(
        [
            f"Deck '{bundle.title}' ({bundle.visibility}, audience: {bundle.audience}; "
            f"validation: {bundle.validation_readiness}; claims: {claim_state or 'none'}).",
            "Slides:",
            *slide_lines,
            "Built by /readme-to-pitchdeck emit-ui; manifests and receipts in the "
            "source-controlled bundle are the ground truth.",
        ]
    )
    return problem, solution


def sync_deck_to_memory(
    deck_data: Path,
    *,
    verify: bool = True,
) -> OperationReceipt:
    """Validate deck.data.json and store a recallable summary via memory learn."""
    if not deck_data.exists():
        raise ValueError(f"deck data not found: {deck_data}")
    bundle = UiDeckBundle.model_validate(json.loads(deck_data.read_text(encoding="utf-8")))
    if bundle.seam_validation.status != "PASS":
        raise ValueError("deck bundle is missing its seam_validation PASS stamp")

    memory_cli = _memory_run_sh()
    if not memory_cli.exists():
        raise ValueError(f"memory skill CLI not found: {memory_cli}")

    problem, solution = _deck_summary(bundle)
    tags = ["pitchdeck", "readme-to-pitchdeck", bundle.deck_id, bundle.visibility]
    command = [
        str(memory_cli),
        "learn",
        "--problem",
        problem,
        "--solution",
        solution,
        # "agent-skills" is an exempt operational scope in the memory quality
        # gate; deck summaries rarely map onto taxonomy bridge keywords.
        "--scope",
        "agent-skills",
    ]
    for tag in tags:
        command.extend(["--tag", tag])
    if verify:
        command.append("--verify")

    logger.info("storing deck '{}' via memory learn (verify={})", bundle.deck_id, verify)
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=MEMORY_TIMEOUT_S,
        check=False,
    )
    if result.returncode != 0:
        logger.error("memory learn failed for deck '{}': {}", bundle.deck_id, result.stderr.strip())
        raise RuntimeError(f"memory learn failed (exit {result.returncode}): {result.stderr.strip()[:500]}")

    return OperationReceipt(
        schema="readme_to_pitchdeck.memory_sync_receipt.v1",
        operation="memory-sync",
        readiness=Readiness.READY,
        mocked=False,
        live=True,
        inputs={"deck_data": str(deck_data.resolve()), "deck_id": bundle.deck_id},
        outputs={
            "memory_tags": ",".join(tags),
            "memory_stdout_tail": result.stdout.strip()[-500:],
        },
        counts={"slides": len(bundle.slides), "claims": sum(bundle.claim_summary.values())},
        gaps=[] if verify else ["Stored without --verify read-back; recall not proven."],
        claims=OperationClaims(
            proves=[
                "A deck summary document was submitted through the memory skill CLI.",
                *(
                    ["The memory CLI reported a successful verify read-back."]
                    if verify
                    else []
                ),
            ],
            does_not_prove=[
                "The stored summary reflects later edits to the deck bundle.",
                "Claim approval states in memory stay current; re-sync after ledger changes.",
            ],
        ),
        seam_validation=SeamValidation(kind="memory_sync_receipt"),
    )
