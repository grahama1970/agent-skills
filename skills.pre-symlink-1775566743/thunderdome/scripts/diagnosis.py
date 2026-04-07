"""Failure diagnosis and /dogpile research for failed rounds."""
from __future__ import annotations

from loguru import logger

from .manifest import ThunderdomeManifest
from .research import dogpile_research
from .scoring import RoundResult
from .tracking import store_dogpile


def diagnose_round(rr: RoundResult, all_rounds: list[RoundResult],
                   manifest: ThunderdomeManifest) -> str:
    """Build diagnosis string from round failure."""
    parts = []
    if rr.winner_score == 0.0:
        parts.append("All strategies scored zero — training crashed or output missing")
    elif rr.winner_score < manifest.scoring.gate_threshold * 0.5:
        parts.append(f"Best {rr.winner_score:.4f} is below 50% of gate — fundamental approach issue")
    else:
        gap = manifest.scoring.gate_threshold - rr.winner_score
        parts.append(f"Gap to gate: {gap:.4f} (best={rr.winner_score:.4f})")

    scores = sorted(rr.strategy_scores, key=lambda s: s.score, reverse=True)
    if len(scores) >= 2:
        spread = scores[0].score - scores[-1].score
        if spread < 0.01:
            parts.append("All strategies nearly identical — data bottleneck likely")

    if rr.plateau_detected:
        parts.append("PLATEAU detected")
    if rr.regression_detected:
        parts.append("REGRESSION detected")

    return " | ".join(parts)


def round_dogpile(rr: RoundResult, all_rounds: list[RoundResult],
                  manifest: ThunderdomeManifest) -> str:
    """Call /dogpile with full tournament context after a failed round."""
    history = "\n".join(
        f"  Round {r.round_num}: winner={r.winner_name} score={r.winner_score:.4f} "
        f"({', '.join(f'{s.name}={s.score:.3f}' for s in r.strategy_scores)})"
        for r in all_rounds
    )
    query = (
        f"Classifier tournament: {manifest.description or manifest.name}. "
        f"Target: F1>={manifest.scoring.gate_threshold}. "
        f"Best so far: {rr.winner_name}={rr.winner_score:.3f}. "
        f"Round history:\n{history}\n"
        f"What specific changes would improve beyond {manifest.scoring.gate_threshold}?"
    )
    result = dogpile_research(query, manifest.memory_scope)
    store_dogpile(manifest.name, query, result, rr.round_num, "round-failure",
                  manifest.memory_scope)
    return result[:2000]
