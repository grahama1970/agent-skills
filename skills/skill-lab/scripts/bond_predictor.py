#!/usr/bin/env python3
"""Bond Predictor -- 3-tier cascade for skill composition prediction.

Predicts:
1. Bond type between two skills (covalent, ionic, none)
2. Success probability of a skill composition chain
3. Optimal ordering for a set of skills

Follows the /memory 3-tier cascade pattern:
    Tier 0:   Heuristic -- AFFINITIES dict + PRECEDES + taxonomy overlap
    Tier 0.5: Classifier -- trained on execution traces (sklearn RF on features)
    Tier 1.5: Small GPT -- trained via teacher-student loop (Qwen2.5-0.5B)
    Tier 2:   scillm teacher -- DeepSeek/Chutes for novel compositions

Training data flow:
    /scillm teacher labels -> /create-gpt SFT -> GGUF local -> shadow -> anneal

Usage:
    python bond_predictor.py predict --skill-a extractor --skill-b memory
    python bond_predictor.py chain --skills "extractor,review-pdf,memory"
    python bond_predictor.py shadow-report
    python bond_predictor.py --json

Split into modules:
    bond_types.py  -- BondFeatures, BOND_TYPES, extract_features, append_jsonl
    bond_tiers.py  -- tier0_heuristic, tier05_classifier, tier15_gpt, tier2_scillm
    bond_chain.py  -- predict_chain_success, log_execution_trace, sync_bonds_to_memory
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

# ---------------------------------------------------------------------------
# Re-exports -- preserve backward compatibility for all importers
# ---------------------------------------------------------------------------

from bond_types import (  # noqa: F401
    BOND_TYPES,
    BondFeatures,
    CLASSIFIER_MODEL,
    GPT_MODEL,
    METRICS_FILE,
    SCRIPTS_DIR,
    SHADOW_FILE,
    SKILLS_DIR,
    STATE_DIR,
    TRACES_FILE,
    append_jsonl,
    extract_features,
)
from bond_tiers import (  # noqa: F401
    _build_gpt_prompt,
    _build_teacher_prompt,
    _call_scillm,
    _parse_gpt_bond_response,
    tier0_heuristic,
    tier05_classifier,
    tier15_gpt,
    tier2_scillm,
)
from bond_chain import (  # noqa: F401
    log_execution_trace,
    predict_chain_success,
    sync_bonds_to_memory,
)

# Re-export energy_model names that consumers import via bond_predictor
from energy_model import (  # noqa: F401
    ATTRACTORS_FILE,
    DEFAULT_ENERGY,
    ELEGANCE_THRESHOLDS,
    ENERGY_COSTS,
    LEARNED_ENERGY_FILE,
    compute_chain_energy,
    compute_elegance,
    estimate_skill_energy,
    update_learned_energy,
)

# Import CascadeRunner with fallback
sys.path.insert(0, str(SKILLS_DIR / "common"))
try:
    from cascade import CascadeRunner, TierDef
except ImportError:
    CascadeRunner = None  # type: ignore
    TierDef = None  # type: ignore


# ---------------------------------------------------------------------------
# Build the cascade runner
# ---------------------------------------------------------------------------

def build_runner() -> "CascadeRunner | None":
    """Build the 3-tier cascade runner for bond prediction."""
    if CascadeRunner is None:
        return None

    tiers = [
        TierDef(
            tier=0,
            name="heuristic",
            fn=tier0_heuristic,
            threshold=0.7,  # Need 70% confidence to stop here
        ),
        TierDef(
            tier=0.5,
            name="classifier",
            fn=tier05_classifier,
            threshold=0.75,
            shadow_mode=True,  # Always compare with teacher initially
        ),
        TierDef(
            tier=1.5,
            name="gpt",
            fn=tier15_gpt,
            threshold=0.7,
            shadow_mode=True,
        ),
        TierDef(
            tier=2,
            name="scillm",
            fn=tier2_scillm,
            is_teacher=True,
        ),
    ]

    return CascadeRunner(
        tiers=tiers,
        shadow_file=SHADOW_FILE,
        metrics_file=METRICS_FILE,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

app = typer.Typer(help="Bond Predictor -- skill composition prediction")


@app.command()
def predict(
    skill_a: str = typer.Option(..., "--skill-a", help="First skill name"),
    skill_b: str = typer.Option(..., "--skill-b", help="Second skill name"),
    skills_root: str = typer.Option(str(SKILLS_DIR), help="Root of skills directory"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
    tier: Optional[float] = typer.Option(None, help="Force specific tier (0, 0.5, 1.5, 2)"),
) -> None:
    """Predict bond between two skills."""
    from scan_soup import scan_soup
    graph = scan_soup(Path(skills_root))
    features = extract_features(skill_a, skill_b, graph)
    input_data = {"features": features, "graph": graph}

    if tier is not None:
        tier_fns = {0: tier0_heuristic, 0.5: tier05_classifier, 1.5: tier15_gpt, 2: tier2_scillm}
        fn = tier_fns.get(tier, tier0_heuristic)
        result = fn(input_data, task="bond_predict", scope="skill-lab")
    else:
        runner = build_runner()
        if runner:
            result = runner.run(input_data, task="bond_predict", scope="skill-lab")
        else:
            result = tier0_heuristic(input_data, task="bond_predict", scope="skill-lab")

    if json_output:
        out = result.result if result else {}
        out["tier"] = result.tier if result else -1
        out["source"] = result.source if result else ""
        out["confidence"] = result.confidence if result else 0
        print(json.dumps(out, indent=2))
    else:
        r = result.result if result else {}
        print(f"Bond: {skill_a} <-> {skill_b}")
        print(f"  Type: {r.get('bond_type', 'unknown')}")
        print(f"  Success probability: {r.get('success_probability', 0):.2f}")
        print(f"  Confidence: {result.confidence:.2f}" if result else "  Confidence: 0")
        print(f"  Tier: {result.tier}" if result else "  Tier: -1")
        print(f"  Source: {result.source}" if result else "  Source: none")
        print(f"  Reason: {r.get('reason', '')}")


@app.command()
def chain(
    skills: str = typer.Option(..., help="Comma-separated skill names"),
    skills_root: str = typer.Option(str(SKILLS_DIR), help="Root of skills directory"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Predict chain success probability."""
    from scan_soup import scan_soup
    skill_list = [s.strip() for s in skills.split(",")]
    graph = scan_soup(Path(skills_root))
    runner = build_runner()

    prediction = predict_chain_success(skill_list, graph, runner)

    if json_output:
        print(json.dumps(prediction, indent=2))
    else:
        elegance = prediction.get("elegance", {})
        energy = prediction.get("energy", {})
        grade = elegance.get("grade", "?")

        print(f"Chain: {' -> '.join(prediction['chain'])}")
        print(f"Success probability: {prediction['success_probability']:.2%}")
        print(f"Elegance: {elegance.get('elegance_score', 0):.3f} ({grade})")
        print(f"Energy: {energy.get('total_energy', 0):.1f} ATP "
              f"({energy.get('skill_count', 0)} skills, "
              f"{energy.get('handoff_cost', 0):.1f} handoff, "
              f"{energy.get('length_penalty', 0):.1f} length penalty)")
        print()

        for bond in prediction["bonds"]:
            print(f"  {bond['from']} -> {bond['to']}: "
                  f"{bond['bond_type']} ({bond['success_probability']:.2f}) "
                  f"[tier {bond['tier']}]")

        print()
        print("Energy breakdown:")
        for item in energy.get("per_skill", []):
            print(f"  {item['skill']}: {item['energy']:.1f} ATP")

        if prediction["weakest_bond"]:
            wb = prediction["weakest_bond"]
            print(f"\nWeakest bond: {wb['from']} -> {wb['to']} "
                  f"({wb['success_probability']:.2f})")


@app.command(name="shadow-report")
def shadow_report(
    hours: int = typer.Option(24, help="Hours to look back"),
) -> None:
    """Show shadow mode agreement stats."""
    runner = build_runner()
    if runner:
        report = runner.shadow_report(task="bond_predict", hours=hours)
        print(json.dumps(report, indent=2))
    else:
        print("Cascade runner not available (missing common/cascade.py)")


@app.command(name="log-trace")
def log_trace(
    skills: str = typer.Option(..., help="Comma-separated skill names"),
    success: bool = typer.Option(False, help="Whether execution succeeded"),
    latency_ms: float = typer.Option(0, help="Execution latency in milliseconds"),
    error: str = typer.Option("", help="Error message if failed"),
) -> None:
    """Log an execution trace."""
    skill_list = [s.strip() for s in skills.split(",")]
    log_execution_trace(skill_list, success, latency_ms, error)
    print(f"Logged trace: {' -> '.join(skill_list)} success={success}")


if __name__ == "__main__":
    app()
