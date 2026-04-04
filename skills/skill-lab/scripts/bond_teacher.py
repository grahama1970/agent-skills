#!/usr/bin/env python3
"""Bond Teacher — generate training labels for bond prediction models.

Three label sources:
1. /scillm (Tier 2) — LLM-based bond analysis for novel pairs
2. /battle outcomes — competitive selection reveals which compositions win
3. Execution traces — historical success/failure data

Labels are used to train:
- Tier 0.5 classifier (sklearn RF → bond_classifier.pkl)
- Tier 1.5 GPT (QLoRA SFT → bond_gpt.gguf)

Follows the 5-phase teacher-student loop from /create-gpt:
    Bootstrap → Train → Deploy(gate) → Correct(shadow) → Anneal

Usage:
    # Bootstrap: generate initial labels from scillm + heuristics
    python bond_teacher.py bootstrap --skills-root /path/to/skills

    # Harvest: collect labels from battle outcomes + execution traces
    python bond_teacher.py harvest

    # Train classifier (Tier 0.5)
    python bond_teacher.py train-classifier

    # Export for GPT training (Tier 1.5 via /create-gpt)
    python bond_teacher.py export-sft --output bond_sft_data.jsonl

    # Full loop: bootstrap → train → evaluate → shadow
    python bond_teacher.py loop --skills-root /path/to/skills
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).parent
SKILLS_DIR = SCRIPTS_DIR.parent.parent

STATE_DIR = SCRIPTS_DIR.parent / "state"
STATE_DIR.mkdir(exist_ok=True)

sys.path.insert(0, str(SCRIPTS_DIR))
from bond_predictor import append_jsonl

# ModelFactory lifecycle integration
sys.path.insert(0, str(SKILLS_DIR / "common"))
from model_factory import ModelFactory, ModelFactoryConfig

BOND_REGISTRY = STATE_DIR / "bond_registry.json"


def get_bond_factory() -> ModelFactory:
    """Get a ModelFactory configured for skill-lab bond models."""
    return ModelFactory(ModelFactoryConfig(
        skills_dir=SKILLS_DIR,
        registry_path=BOND_REGISTRY,
        shadow_file=STATE_DIR / "shadow.jsonl",
        metrics_dir=STATE_DIR,
        promote_threshold=0.70,   # skill-lab uses lower threshold
        retrain_threshold=0.50,
        plateau_threshold=0.60,
        min_shadow_samples=20,
    ))

LABELS_FILE = STATE_DIR / "bond_labels.jsonl"
TRACES_FILE = STATE_DIR / "execution_traces.jsonl"
BATTLE_TRACES_FILE = STATE_DIR / "battle_outcomes.jsonl"
CLASSIFIER_MODEL = STATE_DIR / "bond_classifier.pkl"
TRAINING_METRICS = STATE_DIR / "training_metrics.json"


# ---------------------------------------------------------------------------
# Label schema
# ---------------------------------------------------------------------------

def make_label(
    skill_a: str,
    skill_b: str,
    bond_type: str,
    success_probability: float,
    source: str,  # "scillm", "battle", "trace", "heuristic"
    confidence: float = 1.0,
    reason: str = "",
    metadata: dict | None = None,
) -> dict:
    """Create a standardized training label."""
    return {
        "skill_a": skill_a,
        "skill_b": skill_b,
        "bond_type": bond_type,
        "success_probability": round(success_probability, 3),
        "source": source,
        "confidence": round(confidence, 3),
        "reason": reason,
        "metadata": metadata or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Source 1: scillm teacher labels (bootstrap)
# ---------------------------------------------------------------------------

def bootstrap_from_scillm(skills_root: Path, max_pairs: int = 50) -> list[dict]:
    """Generate initial labels from scillm for all known skill pairs.

    Focuses on pairs with existing affinity data or composition edges.
    """
    sys.path.insert(0, str(SCRIPTS_DIR))
    from scan_soup import scan_soup
    from bond_predictor import extract_features, _call_scillm, _build_teacher_prompt

    graph = scan_soup(skills_root)
    labels = []

    # Prioritize pairs with known relationships
    pairs_to_label = []

    # From composes edges
    for edge in graph.get("edges", []):
        pairs_to_label.append((edge["from"], edge["to"]))

    # From AFFINITIES
    from composer import AFFINITIES
    for skill, partners in AFFINITIES.items():
        for partner, weight in partners:
            if (skill, partner) not in pairs_to_label:
                pairs_to_label.append((skill, partner))

    # Deduplicate and limit
    seen = set()
    unique_pairs = []
    for a, b in pairs_to_label:
        key = tuple(sorted([a, b]))
        if key not in seen:
            seen.add(key)
            unique_pairs.append((a, b))

    unique_pairs = unique_pairs[:max_pairs]
    print(f"Bootstrapping {len(unique_pairs)} skill pairs via scillm...")

    for i, (a, b) in enumerate(unique_pairs):
        features = extract_features(a, b, graph)
        prompt = _build_teacher_prompt(features, graph)

        result = _call_scillm(prompt)
        if result:
            label = make_label(
                skill_a=a,
                skill_b=b,
                bond_type=result.get("bond_type", "none"),
                success_probability=result.get("success_probability", 0.5),
                source="scillm",
                confidence=result.get("confidence", 0.9),
                reason=result.get("reason", "teacher_bootstrap"),
            )
            labels.append(label)
            print(f"  [{i+1}/{len(unique_pairs)}] {a} ↔ {b}: "
                  f"{label['bond_type']} ({label['success_probability']:.2f})")
        else:
            # Fallback: use heuristic as weak label
            label = _heuristic_label(a, b, features)
            labels.append(label)
            print(f"  [{i+1}/{len(unique_pairs)}] {a} ↔ {b}: "
                  f"{label['bond_type']} (heuristic fallback)")

        # Rate limit protection
        time.sleep(0.5)

    return labels


def _heuristic_label(skill_a: str, skill_b: str, features) -> dict:
    """Generate a weak label from heuristics when scillm is unavailable."""
    max_aff = max(features.affinity_weight, features.reverse_affinity_weight)

    if features.a_composes_b or features.b_composes_a:
        bond_type = "covalent"
        success_prob = 0.85
    elif max_aff >= 0.7:
        bond_type = "covalent"
        success_prob = max_aff
    elif max_aff >= 0.4:
        bond_type = "ionic"
        success_prob = max_aff * 0.8
    elif features.shared_taxonomy_tags >= 2:
        bond_type = "van_der_waals"
        success_prob = 0.4
    else:
        bond_type = "none"
        success_prob = 0.1

    return make_label(
        skill_a=skill_a,
        skill_b=skill_b,
        bond_type=bond_type,
        success_probability=success_prob,
        source="heuristic",
        confidence=0.5,  # Lower confidence for heuristic labels
        reason="heuristic_fallback",
    )


# ---------------------------------------------------------------------------
# Source 2: /battle outcome harvesting
# ---------------------------------------------------------------------------

def harvest_battle_outcomes() -> list[dict]:
    """Harvest labels from /battle competition results.

    When /battle runs two skill compositions against each other,
    the winner's bonds are strengthened and the loser's weakened.

    For losers, we check execution trace data to use actual success
    rates instead of hardcoded values when sufficient data exists.
    """
    battle_dir = SKILLS_DIR / "battle"
    results_dir = battle_dir / "results"

    if not results_dir.exists():
        # Try state directory
        results_dir = battle_dir / "state" / "results"

    if not results_dir.exists():
        print("No battle results found")
        return []

    # Pre-load execution trace success rates for loser pairs
    trace_rates = _load_pair_success_rates()

    labels = []
    already_harvested = _load_harvested_battle_ids()

    for result_file in sorted(results_dir.glob("*.json")):
        try:
            data = json.loads(result_file.read_text())
        except (json.JSONDecodeError, OSError):
            continue

        battle_id = data.get("battle_id", result_file.stem)
        if battle_id in already_harvested:
            continue

        # Extract composition chains from battle
        winner = data.get("winner", {})
        loser = data.get("loser", {})
        winner_skills = winner.get("skills", []) or winner.get("chain", [])
        loser_skills = loser.get("skills", []) or loser.get("chain", [])

        # Winner bonds are strengthened
        for i in range(len(winner_skills) - 1):
            a, b = winner_skills[i], winner_skills[i + 1]
            labels.append(make_label(
                skill_a=a, skill_b=b,
                bond_type="covalent",
                success_probability=0.85,
                source="battle",
                confidence=0.9,
                reason=f"battle_winner:{battle_id}",
                metadata={"battle_id": battle_id, "outcome": "winner"},
            ))

        # Loser bonds — use trace data when available
        for i in range(len(loser_skills) - 1):
            a, b = loser_skills[i], loser_skills[i + 1]
            pair_key = f"{a}+{b}"
            reverse_key = f"{b}+{a}"
            trace_info = trace_rates.get(pair_key) or trace_rates.get(reverse_key)

            if trace_info and trace_info["total"] >= 3:
                # Have real data — use actual success rate, lower confidence
                labels.append(make_label(
                    skill_a=a, skill_b=b,
                    bond_type="ionic",
                    success_probability=trace_info["rate"],
                    source="battle",
                    confidence=0.6,
                    reason=f"battle_loser:{battle_id}",
                    metadata={
                        "battle_id": battle_id,
                        "outcome": "loser",
                        "weakening_source": "trace_data",
                        "trace_observations": trace_info["total"],
                    },
                ))
            else:
                # No trace data — use weaker assumption
                labels.append(make_label(
                    skill_a=a, skill_b=b,
                    bond_type="van_der_waals",
                    success_probability=0.5,
                    source="battle",
                    confidence=0.6,
                    reason=f"battle_loser:{battle_id}",
                    metadata={
                        "battle_id": battle_id,
                        "outcome": "loser",
                        "weakening_source": "no_trace_data",
                    },
                ))

        _mark_battle_harvested(battle_id)
        print(f"  Battle {battle_id}: "
              f"winner={'+'.join(winner_skills)} "
              f"loser={'+'.join(loser_skills)}")

    return labels


def _load_pair_success_rates() -> dict[str, dict]:
    """Load aggregated success rates per pair from execution traces."""
    if not TRACES_FILE.exists():
        return {}

    pair_stats: dict[str, dict] = {}
    for line in TRACES_FILE.read_text().splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            pair = entry.get("pair", "")
            if not pair:
                continue
            if pair not in pair_stats:
                pair_stats[pair] = {"total": 0, "successes": 0}
            pair_stats[pair]["total"] += 1
            if entry.get("success"):
                pair_stats[pair]["successes"] += 1
        except (json.JSONDecodeError, KeyError):
            continue

    # Compute rates
    result = {}
    for pair, stats in pair_stats.items():
        if stats["total"] > 0:
            result[pair] = {
                "total": stats["total"],
                "rate": round(stats["successes"] / stats["total"], 3),
            }
    return result


def _load_harvested_battle_ids() -> set:
    """Load set of already-harvested battle IDs."""
    harvest_state = STATE_DIR / "harvested_battles.json"
    if harvest_state.exists():
        return set(json.loads(harvest_state.read_text()))
    return set()


def _mark_battle_harvested(battle_id: str) -> None:
    """Mark a battle as harvested."""
    harvest_state = STATE_DIR / "harvested_battles.json"
    ids = _load_harvested_battle_ids()
    ids.add(battle_id)
    harvest_state.write_text(json.dumps(list(ids)))


# ---------------------------------------------------------------------------
# Source 3: execution trace harvesting
# ---------------------------------------------------------------------------

def harvest_execution_traces() -> list[dict]:
    """Convert execution traces into training labels."""
    if not TRACES_FILE.exists():
        print("No execution traces found")
        return []

    # Aggregate by pair
    pair_stats: dict[str, dict] = {}
    for line in TRACES_FILE.read_text().splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            pair = entry["pair"]
            if pair not in pair_stats:
                pair_stats[pair] = {"total": 0, "success": 0, "latencies": []}
            pair_stats[pair]["total"] += 1
            if entry.get("success"):
                pair_stats[pair]["success"] += 1
            pair_stats[pair]["latencies"].append(entry.get("latency_ms", 0))
        except (json.JSONDecodeError, KeyError):
            continue

    labels = []
    for pair, stats in pair_stats.items():
        if stats["total"] < 3:
            continue  # Need minimum observations

        skills = pair.split("+")
        if len(skills) != 2:
            continue

        success_rate = stats["success"] / stats["total"]

        # Classify bond type from success rate
        if success_rate >= 0.8:
            bond_type = "covalent"
        elif success_rate >= 0.5:
            bond_type = "ionic"
        elif success_rate >= 0.2:
            bond_type = "van_der_waals"
        else:
            bond_type = "none"

        # Confidence scales asymptotically with sample size
        # n=1→0.725, n=5→0.875, n=10→0.909, n=50→0.941, n=100→0.946
        n = stats["total"]
        confidence = min(0.95, 0.5 + 0.45 * (1 - 1 / (n + 1)))

        labels.append(make_label(
            skill_a=skills[0],
            skill_b=skills[1],
            bond_type=bond_type,
            success_probability=success_rate,
            source="trace",
            confidence=confidence,
            reason=f"trace_n={stats['total']}_rate={success_rate:.2f}",
            metadata={"sample_size": stats["total"]},
        ))

    print(f"Harvested {len(labels)} labels from {len(pair_stats)} pairs "
          f"({sum(s['total'] for s in pair_stats.values())} traces)")
    return labels


# ---------------------------------------------------------------------------
# Training: Tier 0.5 Classifier
# ---------------------------------------------------------------------------

def train_classifier() -> dict:
    """Train sklearn RandomForest classifier from collected labels.

    Returns training metrics dict.
    """
    if not LABELS_FILE.exists():
        print("No labels found. Run bootstrap or harvest first.")
        return {"status": "no_data"}

    # Load labels
    labels = []
    for line in LABELS_FILE.read_text().splitlines():
        if not line.strip():
            continue
        try:
            labels.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if len(labels) < 10:
        print(f"Only {len(labels)} labels. Need at least 10 for training.")
        return {"status": "insufficient_data", "count": len(labels)}

    print(f"Training classifier on {len(labels)} labels...")

    try:
        import numpy as np
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import cross_val_score
        import pickle
    except ImportError:
        print("sklearn not available. Install: pip install scikit-learn")
        return {"status": "missing_dependency"}

    sys.path.insert(0, str(SCRIPTS_DIR))
    from bond_predictor import extract_features
    from scan_soup import scan_soup

    graph = scan_soup(SKILLS_DIR)

    # Build feature matrix
    X = []
    y = []
    for label in labels:
        features = extract_features(label["skill_a"], label["skill_b"], graph)
        X.append(features.to_vector())
        y.append(label["bond_type"])

    X = np.array(X)
    y = np.array(y)

    # Train with cross-validation
    clf = RandomForestClassifier(
        n_estimators=100,
        max_depth=10,
        random_state=42,
        class_weight="balanced",
    )

    # 5-fold CV if enough data
    if len(labels) >= 20:
        scores = cross_val_score(clf, X, y, cv=5, scoring="accuracy")
        cv_accuracy = scores.mean()
        print(f"  Cross-validation accuracy: {cv_accuracy:.3f} (±{scores.std():.3f})")
    else:
        cv_accuracy = -1
        print("  Too few samples for cross-validation, training on all data")

    # Train final model
    clf.fit(X, y)

    # Save model
    with open(CLASSIFIER_MODEL, "wb") as f:
        pickle.dump(clf, f)

    # Feature importance
    feature_names = [
        "affinity_ab", "affinity_ba", "a_precedes_b", "b_precedes_a",
        "a_composes_b", "b_composes_a", "shared_taxonomy", "shared_caps",
        "co_occurrence", "success_rate", "avg_latency",
        "energy_a", "energy_b",
    ]
    importances = dict(zip(feature_names, clf.feature_importances_))
    top_features = sorted(importances.items(), key=lambda x: -x[1])[:5]

    metrics = {
        "status": "trained",
        "samples": len(labels),
        "classes": list(clf.classes_),
        "cv_accuracy": round(cv_accuracy, 4) if cv_accuracy >= 0 else "n/a",
        "top_features": {k: round(v, 4) for k, v in top_features},
        "model_path": str(CLASSIFIER_MODEL),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Save metrics
    TRAINING_METRICS.write_text(json.dumps(metrics, indent=2))

    # Register with ModelFactory for lifecycle tracking
    factory = get_bond_factory()
    factory.update_registry("bond-classifier", "classifier", {
        "model_path": str(CLASSIFIER_MODEL),
        "type": "sklearn",
        "shadow_mode": True,
        "cv_accuracy": metrics.get("cv_accuracy", "n/a"),
        "trained_at": metrics.get("timestamp", ""),
    })

    print(f"  Model saved: {CLASSIFIER_MODEL}")
    print(f"  Classes: {metrics['classes']}")
    print(f"  Top features: {', '.join(f'{k}={v:.3f}' for k, v in top_features)}")

    return metrics


# ---------------------------------------------------------------------------
# Export for GPT training (Tier 1.5)
# ---------------------------------------------------------------------------

def export_sft_data(output: Path) -> int:
    """Export labels as SFT chat format for /create-gpt training.

    Format: {"messages": [{"role": "system", ...}, {"role": "user", ...}, {"role": "assistant", ...}]}
    """
    if not LABELS_FILE.exists():
        print("No labels found")
        return 0

    sys.path.insert(0, str(SCRIPTS_DIR))
    from scan_soup import scan_soup
    from bond_predictor import extract_features, _build_gpt_prompt

    graph = scan_soup(SKILLS_DIR)
    count = 0

    with open(output, "w") as f:
        for line in LABELS_FILE.read_text().splitlines():
            if not line.strip():
                continue
            try:
                label = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Only use high-confidence labels
            if label.get("confidence", 0) < 0.7:
                continue

            features = extract_features(label["skill_a"], label["skill_b"], graph)
            user_prompt = _build_gpt_prompt(features, graph)

            # Expected response
            response = json.dumps({
                "bond_type": label["bond_type"],
                "success_probability": label["success_probability"],
                "confidence": label["confidence"],
                "reason": label.get("reason", ""),
            })

            sft_entry = {
                "messages": [
                    {"role": "system", "content": "You predict bond types between agent skills. Output valid JSON only."},
                    {"role": "user", "content": user_prompt},
                    {"role": "assistant", "content": response},
                ]
            }

            f.write(json.dumps(sft_entry) + "\n")
            count += 1

    print(f"Exported {count} SFT entries to {output}")
    return count


# ---------------------------------------------------------------------------
# Full training loop
# ---------------------------------------------------------------------------

def run_training_loop(skills_root: Path, max_bootstrap: int = 50) -> dict:
    """Run the complete teacher-student training loop.

    Phase 1: Bootstrap — scillm labels + heuristic labels
    Phase 2: Harvest — battle outcomes + execution traces
    Phase 3: Train — classifier (Tier 0.5)
    Phase 4: Export — SFT data for GPT (Tier 1.5)
    Phase 5: Evaluate — gate check on holdout
    """
    results = {"phases": {}}

    # Phase 1: Bootstrap
    print("=== Phase 1: Bootstrap (scillm teacher labels) ===")
    try:
        labels = bootstrap_from_scillm(skills_root, max_pairs=max_bootstrap)
    except Exception as e:
        print(f"  scillm unavailable ({e}), using heuristic fallback")
        # Generate heuristic labels as fallback
        sys.path.insert(0, str(SCRIPTS_DIR))
        from scan_soup import scan_soup
        from bond_predictor import extract_features
        from composer import AFFINITIES

        graph = scan_soup(skills_root)
        labels = []

        seen = set()
        for skill, partners in AFFINITIES.items():
            for partner, weight in partners:
                key = tuple(sorted([skill, partner]))
                if key not in seen:
                    seen.add(key)
                    features = extract_features(skill, partner, graph)
                    labels.append(_heuristic_label(skill, partner, features))

        # Add composes edges
        for edge in graph.get("edges", []):
            key = tuple(sorted([edge["from"], edge["to"]]))
            if key not in seen:
                seen.add(key)
                features = extract_features(edge["from"], edge["to"], graph)
                labels.append(_heuristic_label(edge["from"], edge["to"], features))

    # Save labels
    append_jsonl(LABELS_FILE, labels)
    results["phases"]["bootstrap"] = {"count": len(labels)}
    print(f"  Generated {len(labels)} bootstrap labels")

    # Phase 2: Harvest battle + traces
    print("\n=== Phase 2: Harvest (battle + execution traces) ===")
    battle_labels = harvest_battle_outcomes()
    trace_labels = harvest_execution_traces()
    harvest_labels = battle_labels + trace_labels

    append_jsonl(LABELS_FILE, harvest_labels)
    results["phases"]["harvest"] = {
        "battle": len(battle_labels),
        "traces": len(trace_labels),
    }

    # Phase 3: Train classifier
    print("\n=== Phase 3: Train Classifier (Tier 0.5) ===")
    train_metrics = train_classifier()
    results["phases"]["train"] = train_metrics

    # Phase 4: Export SFT for GPT
    print("\n=== Phase 4: Export SFT Data (for Tier 1.5 GPT) ===")
    sft_output = STATE_DIR / "bond_sft_data.jsonl"
    sft_count = export_sft_data(sft_output)
    results["phases"]["export"] = {"sft_entries": sft_count, "path": str(sft_output)}

    if sft_count > 0:
        print(f"\n  Training GPT (Tier 1.5) via ModelFactory...")
        factory = get_bond_factory()
        gpt_result = factory.train_gpt(
            "bond-predictor",
            labels_path=str(sft_output),
            base_model="Qwen/Qwen2.5-0.5B-Instruct",
        )
        results["phases"]["gpt_train"] = {
            "success": gpt_result.success,
            "model_path": gpt_result.model_path,
            "error": gpt_result.error,
        }
        if gpt_result.success:
            print(f"  GPT trained: {gpt_result.model_path}")
        else:
            print(f"  GPT training failed: {gpt_result.error}")
            print(f"  Manual fallback:")
            print(f"    {SKILLS_DIR}/create-gpt/run.sh train \\")
            print(f"      --data {sft_output} \\")
            print(f"      --name bond-predictor \\")
            print(f"      --base Qwen/Qwen2.5-0.5B-Instruct")

    # Phase 5: Evaluate gate
    print("\n=== Phase 5: Gate Check ===")
    if train_metrics.get("cv_accuracy", 0) and train_metrics["cv_accuracy"] != "n/a":
        accuracy = train_metrics["cv_accuracy"]
        gate_pass = accuracy >= 0.70  # 70% accuracy gate
        results["phases"]["gate"] = {
            "accuracy": accuracy,
            "threshold": 0.70,
            "passed": gate_pass,
        }
        if gate_pass:
            print(f"  GATE PASSED: accuracy={accuracy:.3f} >= 0.70")
        else:
            print(f"  GATE FAILED: accuracy={accuracy:.3f} < 0.70")
            print(f"  Need more training data or better features")
    else:
        results["phases"]["gate"] = {"status": "skipped", "reason": "insufficient_data"}
        print("  GATE SKIPPED: insufficient data for evaluation")

    results["timestamp"] = datetime.now(timezone.utc).isoformat()
    print(f"\n=== Training Loop Complete ===")
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

import typer

app = typer.Typer(help="Bond Teacher — training data generation")


@app.command()
def bootstrap(
    skills_root: str = typer.Option(str(SKILLS_DIR), help="Root of skills directory"),
    max_pairs: int = typer.Option(50, help="Maximum skill pairs to label"),
) -> None:
    """Generate initial labels from scillm."""
    labels = bootstrap_from_scillm(Path(skills_root), max_pairs)
    append_jsonl(LABELS_FILE, labels)
    print(f"\nSaved {len(labels)} labels to {LABELS_FILE}")


@app.command()
def harvest() -> None:
    """Harvest labels from battle + traces."""
    battle_labels = harvest_battle_outcomes()
    trace_labels = harvest_execution_traces()
    all_labels = battle_labels + trace_labels
    append_jsonl(LABELS_FILE, all_labels)
    print(f"\nTotal: {len(all_labels)} new labels "
          f"(battle={len(battle_labels)}, traces={len(trace_labels)})")


@app.command(name="train-classifier")
def train_classifier_cmd() -> None:
    """Train Tier 0.5 classifier."""
    train_classifier()


@app.command(name="export-sft")
def export_sft(
    output: str = typer.Option(str(STATE_DIR / "bond_sft_data.jsonl"), help="Output file path"),
) -> None:
    """Export SFT data for Tier 1.5 GPT."""
    export_sft_data(Path(output))


@app.command()
def loop(
    skills_root: str = typer.Option(str(SKILLS_DIR), help="Root of skills directory"),
    max_bootstrap: int = typer.Option(50, help="Maximum bootstrap pairs"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Full training loop."""
    results = run_training_loop(Path(skills_root), max_bootstrap)
    if json_output:
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    app()
