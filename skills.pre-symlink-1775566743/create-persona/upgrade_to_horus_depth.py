#!/usr/bin/env python3
"""
Upgrade existing personas to Horus-depth.

Applies the depth from /home/graham/workspace/experiments/memory/persona:
1. Federated Taxonomy bridges (Precision, Resilience, Fragility, Corruption, Loyalty, Stealth)
2. Theory of Mind (BDI) initialization
3. Simulacrum validation with bridge traversal
4. Convergence loop for failing personas

Usage:
    python upgrade_to_horus_depth.py --scope personas --dry-run
    python upgrade_to_horus_depth.py --scope behavioral --threshold 0.7
    python upgrade_to_horus_depth.py --resume
"""

import typer
import json
import sys
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from persona import (
    Persona,
    get_persona,
    list_personas,
    create_persona,
    update_persona,
)
from theory_of_mind import (
    BRIDGE_ATTRIBUTES,
    extract_bridges,
    get_or_create_bdi_state,
    save_bdi_state,
    BDIState,
)
from quality import (
    diagnose_persona,
    validate_simulacrum,
    improve_persona,
)
from templates import get_default_bridges, get_mood_rules

from loguru import logger as log


# Default bridge assignments by domain/template
DOMAIN_BRIDGE_MAPPING = {
    # Film/Animation
    "film": {"Precision": 0.7, "Fragility": 0.6},
    "animation": {"Precision": 0.8, "Fragility": 0.7},
    "director": {"Precision": 0.7, "Loyalty": 0.5},
    "cinematograph": {"Precision": 0.9},

    # Music
    "music": {"Fragility": 0.7, "Resilience": 0.5},
    "composer": {"Precision": 0.8, "Fragility": 0.6},

    # Writing
    "writing": {"Fragility": 0.6, "Corruption": 0.5},
    "author": {"Fragility": 0.6},
    "screenwriter": {"Precision": 0.7, "Fragility": 0.5},

    # Science
    "science": {"Precision": 0.9, "Resilience": 0.6},
    "neuroscience": {"Precision": 0.9},
    "biology": {"Precision": 0.8, "Resilience": 0.5},
    "physics": {"Precision": 0.9},

    # Security
    "security": {"Stealth": 0.8, "Corruption": 0.7, "Precision": 0.7},
    "hacker": {"Stealth": 0.9, "Corruption": 0.8},
    "threat": {"Stealth": 0.9, "Corruption": 0.9},

    # Programming
    "programming": {"Precision": 0.9, "Resilience": 0.7},
    "coder": {"Precision": 0.9, "Resilience": 0.7},
    "developer": {"Precision": 0.8, "Resilience": 0.6},

    # Philosophy
    "philosophy": {"Fragility": 0.5, "Resilience": 0.6, "Loyalty": 0.6},
    "psychology": {"Fragility": 0.7, "Precision": 0.6},

    # Design
    "design": {"Precision": 0.8, "Fragility": 0.5},
    "vfx": {"Precision": 0.9},

    # Acting
    "acting": {"Fragility": 0.8, "Resilience": 0.5},
    "voice": {"Fragility": 0.7},
}


def infer_bridges_from_persona(persona: Persona) -> dict[str, float]:
    """
    Infer appropriate bridge weights from persona metadata.

    Uses domain, expertise, and template to determine bridges.
    """
    bridges = {}

    # Start with template defaults
    if persona.template:
        bridges.update(get_default_bridges(persona.template))

    # Add domain-specific bridges
    domain_lower = (persona.domain or "").lower()
    for keyword, domain_bridges in DOMAIN_BRIDGE_MAPPING.items():
        if keyword in domain_lower:
            for bridge, weight in domain_bridges.items():
                # Use max of existing or new weight
                bridges[bridge] = max(bridges.get(bridge, 0), weight)

    # Check expertise for additional hints
    for exp in persona.expertise:
        exp_lower = exp.lower()
        for keyword, exp_bridges in DOMAIN_BRIDGE_MAPPING.items():
            if keyword in exp_lower:
                for bridge, weight in exp_bridges.items():
                    bridges[bridge] = max(bridges.get(bridge, 0), weight * 0.9)

    # Extract from goals if present
    if persona.goals:
        text = " ".join(persona.goals)
        extracted = extract_bridges(text, max_bridges=2)
        for bridge in extracted:
            if bridge not in bridges:
                bridges[bridge] = 0.5

    # Ensure at least one bridge
    if not bridges:
        bridges["Precision"] = 0.5

    return bridges


def upgrade_persona(
    persona: Persona,
    scope: str,
    dry_run: bool = False,
) -> dict:
    """
    Upgrade a single persona to Horus-depth.

    Returns dict with upgrade results.
    """
    result = {
        "name": persona.name,
        "scope": scope,
        "upgraded": False,
        "bridges_added": [],
        "bdi_initialized": False,
        "actions": [],
    }

    # 1. Add bridges if missing
    if not persona.bridge_weights:
        inferred = infer_bridges_from_persona(persona)
        result["bridges_added"] = list(inferred.keys())
        result["actions"].append(f"Inferred bridges: {list(inferred.keys())}")

        if not dry_run:
            persona.bridge_weights = inferred
            persona.update_timestamp()
            create_persona(persona, store=True)
    else:
        result["actions"].append(f"Already has bridges: {list(persona.bridge_weights.keys())}")

    # 2. Initialize BDI state
    if not dry_run:
        bdi_state = get_or_create_bdi_state(persona.name, "default", scope)
        if bdi_state.interaction_count == 0:
            # First time - set up initial state
            save_bdi_state(bdi_state, scope)
            result["bdi_initialized"] = True
            result["actions"].append("Initialized BDI state")
    else:
        result["actions"].append("(dry-run) Would initialize BDI state")
        result["bdi_initialized"] = True

    result["upgraded"] = True
    return result


def run_simulacrum_validation(
    persona: Persona,
    scope: str,
    threshold: float = 0.7,
    dry_run: bool = False,
) -> dict:
    """
    Run simulacrum validation and improvement if needed.
    """
    result = {
        "name": persona.name,
        "initial_score": 0.0,
        "final_score": 0.0,
        "passed": False,
        "iterations": 0,
    }

    if dry_run:
        result["actions"] = ["(dry-run) Would run simulacrum validation"]
        return result

    # Run validation
    score = validate_simulacrum(persona.name, scope)
    result["initial_score"] = score.accuracy

    if score.accuracy >= threshold:
        result["passed"] = True
        result["final_score"] = score.accuracy
        return result

    # Run improvement loop
    improvement = improve_persona(
        persona.name,
        scope,
        quality_threshold=threshold,
        max_iterations=2,  # Light improvement
        dry_run=False,
    )

    result["iterations"] = improvement.iterations
    result["final_score"] = improvement.final_score
    result["passed"] = improvement.converged

    return result


app = typer.Typer(help="Upgrade personas to Horus-depth")


@app.command()
def main(
    scope: str = typer.Option("personas", help="Memory scope to process"),
    dry_run: bool = typer.Option(False, help="Preview without changes"),
    threshold: float = typer.Option(0.7, help="Simulacrum pass threshold"),
    limit: int = typer.Option(None, help="Max personas to process"),
    skip_validation: bool = typer.Option(False, help="Skip simulacrum validation"),
    resume: bool = typer.Option(False, help="Resume from checkpoint"),
    checkpoint: str = typer.Option("upgrade_checkpoint.json", help="Checkpoint file"),
):
    log.info("Starting Horus-depth upgrade")
    log.info(f"  Scope: {scope}")
    log.info(f"  Threshold: {threshold}")
    if dry_run:
        log.info("  Mode: DRY RUN")

    # Load checkpoint
    checkpoint_path = Path(checkpoint)
    completed = set()
    if resume and checkpoint_path.exists():
        checkpoint_data = json.loads(checkpoint_path.read_text())
        completed = set(checkpoint_data.get("completed", []))
        log.info(f"  Resuming from checkpoint: {len(completed)} already done")

    # Get personas
    personas = list_personas(scope=scope)
    if limit:
        personas = personas[:limit]

    log.info(f"  Found {len(personas)} personas")
    print()

    # Process
    results = {
        "total": len(personas),
        "upgraded": 0,
        "validated": 0,
        "passed": 0,
        "failed": 0,
        "details": [],
    }

    for i, persona in enumerate(personas, 1):
        name = persona.name

        if name in completed:
            log.info(f"[{i}/{len(personas)}] Skipping {name} (in checkpoint)")
            continue

        log.info(f"[{i}/{len(personas)}] Processing: {name}")

        # Upgrade
        upgrade_result = upgrade_persona(persona, scope, dry_run)
        if upgrade_result["upgraded"]:
            results["upgraded"] += 1

        for action in upgrade_result["actions"]:
            log.info(f"  {action}")

        # Simulacrum validation
        if not skip_validation:
            val_result = run_simulacrum_validation(
                persona, scope, threshold, dry_run
            )
            results["validated"] += 1

            if val_result["passed"]:
                results["passed"] += 1
                log.info(f"  Simulacrum: PASSED ({val_result['final_score']:.2f})")
            else:
                results["failed"] += 1
                log.info(f"  Simulacrum: FAILED ({val_result['final_score']:.2f})")

            upgrade_result["validation"] = val_result

        results["details"].append(upgrade_result)

        # Save checkpoint
        if not dry_run:
            completed.add(name)
            checkpoint_path.write_text(json.dumps({
                "completed": list(completed),
                "timestamp": datetime.now().isoformat(),
            }, indent=2))

    # Summary
    print()
    log.info("=" * 50)
    log.info("UPGRADE COMPLETE")
    log.info(f"  Total personas: {results['total']}")
    log.info(f"  Upgraded: {results['upgraded']}")
    if not skip_validation:
        log.info(f"  Validated: {results['validated']}")
        log.info(f"  Passed simulacrum: {results['passed']}")
        log.info(f"  Failed simulacrum: {results['failed']}")
        if results['validated'] > 0:
            pass_rate = results['passed'] / results['validated']
            log.info(f"  Pass rate: {pass_rate:.1%}")

    # Save full results
    results_path = Path(f"upgrade_results_{scope}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    results_path.write_text(json.dumps(results, indent=2))
    log.info(f"  Results saved to: {results_path}")


if __name__ == "__main__":
    app()
