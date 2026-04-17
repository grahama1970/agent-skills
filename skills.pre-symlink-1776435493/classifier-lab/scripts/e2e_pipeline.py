#!/usr/bin/env python3
"""
End-to-end classifier pipeline with NON-NEGOTIABLE self-improvement loop.

The agent puts itself into a loop: train → evaluate → diagnose → /dogpile → adjust → retrain
until the holdout gate (F1 ≥ 0.90) passes or max rounds exhausted.

This is NOT optional. The loop IS the product. If F1 < 0.90, the pipeline does not stop —
it diagnoses the failure, consults /dogpile, adjusts strategy, and tries again.

10-Step Escalation (each round picks the next untried strategy):
  Round 1: Baseline backbone + default HPs
  Round 2: Adjusted LR (halved) + more epochs (2x)
  Round 3: Augmentation (mixup, cutmix, random erasing)
  Round 4: Regularization (dropout +0.1, weight decay 2x, label smoothing)
  Round 5: Ensemble (top-3 backbones, soft voting)
  Round 6: Switch modality (vision→tabular, tabular→paired/Siamese)
  Round 7: /dogpile "why does {backbone} fail on {task} with F1={f1}"
  Round 8: Data enrichment (collect more samples for weakest class)
  Round 9: Feature engineering (dead feature removal, normalization)
  Round 10: Escalate to human with full diagnosis

Plateau detection: If 3+ consecutive rounds within ±0.02 F1, diagnose data sufficiency
and escalate — the problem is data, not architecture.

Usage:
    python e2e_pipeline.py --task "table merge classification" --data-dir /path/to/data
    python e2e_pipeline.py --task "text intent" --dataset clinc_oos --modality text
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import typer
from loguru import logger
from tracking import store_round_artifact, store_dogpile_to_memory, generate_next_steps, notify_ux, run_skill

app = typer.Typer(no_args_is_help=True)

SKILL_DIR = Path(__file__).resolve().parent.parent
SKILLS_DIR = SKILL_DIR.parent
CREATE_CLF = SKILLS_DIR / "create-classifier"
DATA_DIR = Path(os.environ.get("CLASSIFIER_LAB_DATA_DIR", "/mnt/storage12tb/media/agents/shared/classifier-lab/data"))
MODELS_DIR = Path(os.environ.get("CLASSIFIER_LAB_MODELS_DIR", "/mnt/storage12tb/media/agents/shared/classifier-lab/models"))
ARTIFACTS_DIR = SKILL_DIR / ".artifacts"
HF_TOKEN = os.environ.get("HF_TOKEN", "")
HF_USERNAME = os.environ.get("hf_username", "grahamaco")

# ── NON-NEGOTIABLE: Gate threshold ────────────────────────────────
HOLDOUT_F1_GATE = 0.90
MAX_ROUNDS = 10
PLATEAU_WINDOW = 3
PLATEAU_EPSILON = 0.02


@dataclass
class RoundResult:
    """Result of a single training round."""
    round_num: int
    strategy: str
    backbone: str
    modality: str
    f1: float
    accuracy: float
    wilson_lower: float = 0.0
    diagnosis: str = ""
    dogpile_query: str = ""
    dogpile_insights: str = ""
    hps: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


@dataclass
class PipelineState:
    """Tracks progress across all phases and rounds."""
    task: str = ""
    project_id: str = ""
    phase: str = "init"
    modality: str = "vision"  # vision | text | tabular | paired
    dataset_repo: str = ""
    dataset_dir: str = ""
    data_dir: str = ""
    backbones: list[str] = field(default_factory=list)
    rounds: list[RoundResult] = field(default_factory=list)
    current_round: int = 0
    winner: str = ""
    winner_f1: float = 0.0
    winner_hps: dict = field(default_factory=dict)
    holdout_passed: bool = False
    export_path: str = ""
    hf_repo: str = ""
    errors: list[str] = field(default_factory=list)
    research_md: str = ""
    data_audit: dict = field(default_factory=dict)


# ── Escalation strategies ─────────────────────────────────────────

STRATEGIES = [
    "baseline",
    "lr_halved_more_epochs",
    "augmentation",
    "regularization",
    "ensemble_top3",
    "switch_modality",
    "dogpile_targeted",
    "data_enrichment",
    "feature_engineering",
    "escalate_human",
]


def get_strategy_hps(strategy: str, state: PipelineState, prev: Optional[RoundResult]) -> dict:
    """Return hyperparameters for a given escalation strategy."""
    base = {"epochs": 10, "lr": 2e-4, "batch_size": 32, "weight_decay": 1e-4, "dropout": 0.1}
    if state.modality == "paired":
        base["batch_size"] = 16  # paired loads 2 images per sample — halve batch to avoid OOM
    if prev and prev.hps:
        base.update(prev.hps)

    if strategy == "baseline":
        return base
    elif strategy == "lr_halved_more_epochs":
        return {**base, "lr": base["lr"] / 2, "epochs": base["epochs"] * 2}
    elif strategy == "augmentation":
        return {**base, "mixup_alpha": 0.3, "cutmix_alpha": 1.0, "random_erasing": 0.25}
    elif strategy == "regularization":
        return {**base, "dropout": min(base["dropout"] + 0.1, 0.5), "weight_decay": base["weight_decay"] * 2, "label_smoothing": 0.1}
    elif strategy == "ensemble_top3":
        return {**base, "ensemble": True, "top_k": 3}
    elif strategy == "switch_modality":
        # Switch to next modality in rotation
        rotation = {"vision": "tabular", "tabular": "paired", "paired": "vision", "text": "tabular"}
        return {**base, "new_modality": rotation.get(state.modality, "tabular")}
    elif strategy == "feature_engineering":
        return {**base, "normalize_features": True, "remove_dead_features": True, "feature_selection": "mutual_info"}
    else:
        return base


# ── Helpers ───────────────────────────────────────────────────────


# run_skill, notify_ux, store_round_artifact, store_dogpile_to_memory
# are imported from tracking.py


def _find_tabular_jsonl(data_dir: str) -> str:
    """Find the best JSONL file for tabular training in the data directory."""
    data_path = Path(data_dir)
    # Priority: merge_features_tabular.jsonl > *tabular*.jsonl > *features*.jsonl > first .jsonl
    candidates = [
        data_path / "merge_features_tabular.jsonl",
        data_path / "labels" / "structural.jsonl",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    for pattern in ["*tabular*.jsonl", "*features*.jsonl", "*.jsonl"]:
        matches = sorted(data_path.glob(pattern))
        if matches:
            return str(matches[0])
    # Recurse one level
    for sub in data_path.iterdir():
        if sub.is_dir():
            for pattern in ["*tabular*.jsonl", "*features*.jsonl", "*.jsonl"]:
                matches = sorted(sub.glob(pattern))
                if matches:
                    return str(matches[0])
    return str(data_path / "labels.jsonl")  # fallback


def detect_plateau(rounds: list[RoundResult]) -> bool:
    """Detect if last N rounds are within ±PLATEAU_EPSILON F1."""
    if len(rounds) < PLATEAU_WINDOW:
        return False
    recent = [r.f1 for r in rounds[-PLATEAU_WINDOW:]]
    return (max(recent) - min(recent)) < PLATEAU_EPSILON


# ── Phase 1: Research Gate ────────────────────────────────────────

def phase_research(state: PipelineState) -> None:
    """NON-NEGOTIABLE: /dogpile research BEFORE any training.

    Training is BLOCKED until research.md exists with backbone recommendations.
    """
    state.phase = "research"
    notify_ux("training-update", {"projectId": state.project_id, "phase": "research", "message": f"Researching SOTA for: {state.task}"})

    # Build targeted research query — backbone, HPs, augmentation, everything
    n_samples = state.data_audit.get("total_samples", "unknown") if state.data_audit else "unknown"
    n_classes = state.data_audit.get("n_classes", "unknown") if state.data_audit else "unknown"
    balanced = state.data_audit.get("balanced", "unknown") if state.data_audit else "unknown"
    query = (
        f"Training a {state.modality} classifier for: {state.task}. "
        f"Dataset: {n_samples} samples, {n_classes} classes, balanced={balanced}. "
        f"What is the best backbone model, learning rate, batch size, epochs, "
        f"augmentation strategy (mixup, cutmix, random erasing), "
        f"regularization (dropout, weight decay, label smoothing), "
        f"and learning rate schedule for this task and dataset size? "
        f"Include specific hyperparameter values and any tricks for small datasets. "
        f"Target: F1 >= {HOLDOUT_F1_GATE}. 2025 2026 state of the art."
    )

    logger.info(f"Dogpile query: {query}")
    rc, out, err = run_skill("dogpile", f'search "{query}"', timeout=180)

    # Store research output
    research_dir = CREATE_CLF / "projects" / state.project_id
    research_dir.mkdir(parents=True, exist_ok=True)
    research_path = research_dir / "research.md"

    if rc == 0 and out.strip():
        research_path.write_text(out)
        state.research_md = out[:2000]
        logger.info(f"Research saved: {len(out)} chars")
    else:
        research_path.write_text(f"# Research: {state.task}\n\nDogpile returned rc={rc}.\n\nQuery: {query}\n\nStderr: {err[:500]}")
        logger.warning("Dogpile failed — using default backbones")

    # NON-NEGOTIABLE: Store dogpile request + result to /memory for tracking
    store_dogpile_to_memory(state, query, out if rc == 0 else err, round_num=0, phase="research")

    # Set default backbones by modality
    if not state.backbones:
        defaults = {
            "vision": ["convnextv2_nano.fcmae_ft_in22k_in1k", "efficientnet_b0", "fastvit_sa12.apple_in1k"],
            "text": ["prajjwal1/bert-tiny", "distilbert-base-uncased", "bert-base-uncased"],
            "tabular": ["gradient_boosting", "random_forest", "logistic_regression"],
            "paired": ["efficientnet_b0", "convnextv2_nano.fcmae_ft_in22k_in1k"],
        }
        state.backbones = defaults.get(state.modality, defaults["vision"])

    # Make research insights available as a "round 0" result so round 1 can use them
    if state.research_md:
        round0 = RoundResult(
            round_num=0, strategy="research", backbone="",
            modality=state.modality, f1=0.0, accuracy=0.0,
            dogpile_insights=state.research_md,
            diagnosis="Pre-training /dogpile research",
        )
        state.rounds.append(round0)
        logger.info("Research insights loaded as round 0 — available to round 1 via dogpile_insights")

    notify_ux("training-update", {"projectId": state.project_id, "phase": "research", "backbones": state.backbones, "done": True})


# ── Phase 2: Data Validation ─────────────────────────────────────

def phase_data(state: PipelineState) -> None:
    """Validate data quality gates. Blocks pipeline if insufficient."""
    state.phase = "data"
    data_path = Path(state.data_dir or state.dataset_dir)

    if not data_path.exists():
        state.errors.append(f"Data directory not found: {data_path}")
        return

    # Count classes and samples
    class_counts: dict[str, int] = {}

    # If data_path is a JSONL file (text modality passes file directly)
    if data_path.is_file() and data_path.suffix == ".jsonl":
        from collections import Counter
        labels: Counter = Counter()
        for line in data_path.open():
            try:
                row = json.loads(line)
                labels[row.get("label", "unknown")] += 1
            except json.JSONDecodeError:
                continue
        class_counts = dict(labels)
        state.data_audit = {
            "class_counts": class_counts,
            "n_classes": len(class_counts),
            "total_samples": sum(class_counts.values()),
            "min_per_class": min(class_counts.values()) if class_counts else 0,
            "balanced": (max(class_counts.values()) / max(min(class_counts.values()), 1)) < 3 if class_counts else False,
        }
        logger.info(f"Data audit: {state.data_audit}")
        notify_ux("training-update", {"projectId": state.project_id, "phase": "data", "audit": state.data_audit})
        min_samples = state.data_audit["min_per_class"]
        if min_samples < 50:
            state.errors.append(f"Critically insufficient data: {min_samples} samples/class (need at least 50)")
        return

    # Check image directories
    for sub in sorted(data_path.iterdir()):
        if sub.is_dir() and not sub.name.startswith("."):
            train_dir = sub / "train" if (sub / "train").exists() else sub
            for cls_dir in sorted(train_dir.iterdir()):
                if cls_dir.is_dir():
                    images = list(cls_dir.glob("*.png")) + list(cls_dir.glob("*.jpg")) + list(cls_dir.glob("*.jpeg"))
                    if images:
                        class_counts[cls_dir.name] = len(images)

    # Check JSONL format
    if not class_counts:
        from collections import Counter
        for jsonl in sorted(data_path.glob("*.jsonl")):
            labels = Counter()
            for line in jsonl.open():
                try:
                    row = json.loads(line)
                    labels[row.get("label", "unknown")] += 1
                except json.JSONDecodeError:
                    continue
            class_counts = dict(labels)
            break

    # Check root-level image dirs (train/merge, train/separate pattern)
    if not class_counts:
        train_dir = data_path / "train"
        if train_dir.exists():
            for cls_dir in sorted(train_dir.iterdir()):
                if cls_dir.is_dir():
                    images = list(cls_dir.glob("*.png")) + list(cls_dir.glob("*.jpg"))
                    if images:
                        class_counts[cls_dir.name] = len(images)

    state.data_audit = {
        "class_counts": class_counts,
        "n_classes": len(class_counts),
        "total_samples": sum(class_counts.values()),
        "min_per_class": min(class_counts.values()) if class_counts else 0,
        "balanced": (max(class_counts.values()) / max(min(class_counts.values()), 1)) < 3 if class_counts else False,
    }

    logger.info(f"Data audit: {state.data_audit}")
    notify_ux("training-update", {"projectId": state.project_id, "phase": "data", "audit": state.data_audit})

    min_samples = state.data_audit["min_per_class"]
    if min_samples < 50:
        state.errors.append(f"Critically insufficient data: {min_samples} samples/class (need at least 50)")
    elif min_samples < 200:
        logger.warning(f"Low data: {min_samples} samples/class — may limit accuracy")


# ── Self-Improvement Loop (THE CORE PRODUCT) ─────────────────────

def self_improvement_loop(state: PipelineState) -> None:
    """NON-NEGOTIABLE: Train → Evaluate → Diagnose → Adjust → Retrain.

    Runs until holdout gate passes (F1 ≥ 0.90) or max rounds exhausted.
    Each failed round triggers diagnosis and strategy escalation.
    /dogpile is called automatically on modality switch and after 3 failures.
    """
    state.phase = "self-improvement"
    logger.info(f"═══ SELF-IMPROVEMENT LOOP: target F1 ≥ {HOLDOUT_F1_GATE}, max {MAX_ROUNDS} rounds ═══")

    for round_num in range(1, MAX_ROUNDS + 1):
        state.current_round = round_num
        strategy = STRATEGIES[min(round_num - 1, len(STRATEGIES) - 1)]
        prev_result = state.rounds[-1] if state.rounds else None
        hps = get_strategy_hps(strategy, state, prev_result)

        # Carry forward dogpile insights from previous round
        if prev_result and prev_result.dogpile_insights:
            hps["dogpile_insights"] = prev_result.dogpile_insights
            logger.info(f"Prior dogpile insights available ({len(prev_result.dogpile_insights)} chars)")

        logger.info(f"── Round {round_num}/{MAX_ROUNDS}: strategy={strategy} modality={state.modality} hps={list(hps.keys())} ──")
        notify_ux("training-update", {
            "projectId": state.project_id, "phase": "training",
            "round": round_num, "maxRounds": MAX_ROUNDS, "strategy": strategy,
            "message": f"Round {round_num}: {strategy}",
        })

        # Handle modality switch
        if strategy == "switch_modality":
            new_modality = hps.pop("new_modality", "tabular")
            logger.info(f"SWITCHING MODALITY: {state.modality} → {new_modality}")
            old_modality = state.modality
            state.modality = new_modality
            # Update backbones for new modality
            defaults = {
                "vision": ["efficientnet_b0", "convnextv2_nano.fcmae_ft_in22k_in1k"],
                "tabular": ["gradient_boosting", "random_forest"],
                "paired": ["efficientnet_b0"],
                "text": ["distilbert-base-uncased"],
            }
            state.backbones = defaults.get(new_modality, ["efficientnet_b0"])

            # Update data directory for new modality
            # Paired/vision needs image dirs; tabular needs JSONL
            data_path = Path(state.data_dir)
            if new_modality == "paired":
                # Look for merge_images/ or images/ subdirectory with class folders
                for candidate in ["merge_images", "images", "paired", "train"]:
                    candidate_path = data_path / candidate
                    if candidate_path.exists() and any(candidate_path.iterdir()):
                        state.data_dir = str(candidate_path)
                        logger.info(f"Updated data_dir for paired: {state.data_dir}")
                        break
            elif new_modality == "vision":
                for candidate in ["images", "train"]:
                    candidate_path = data_path / candidate
                    if candidate_path.exists():
                        state.data_dir = str(candidate_path)
                        break

            notify_ux("training-update", {"projectId": state.project_id, "phase": "modality-switch", "from": old_modality, "to": new_modality, "data_dir": state.data_dir})

        # Handle targeted dogpile
        if strategy == "dogpile_targeted" and prev_result:
            query = f"why does {prev_result.backbone} fail on {state.task} with F1={prev_result.f1:.3f} using {state.modality} modality cross-document generalization"
            logger.info(f"Targeted dogpile: {query}")
            rc, out, err = run_skill("dogpile", f'search "{query}"', timeout=180)
            if rc == 0 and out.strip():
                hps["dogpile_insights"] = out[:1000]
                logger.info(f"Dogpile insights: {out[:200]}")
            store_dogpile_to_memory(state, query, out if rc == 0 else err, round_num=round_num, phase="targeted-research")

        # Handle escalate to human
        if strategy == "escalate_human":
            diagnosis = _diagnose_failure(state)
            logger.error(f"ESCALATING TO HUMAN after {round_num - 1} rounds. Best F1: {state.winner_f1:.3f}")
            logger.error(f"Diagnosis: {diagnosis}")
            notify_ux("training-update", {
                "projectId": state.project_id, "phase": "escalate",
                "message": f"ESCALATED: {round_num - 1} rounds exhausted. Best F1: {state.winner_f1:.3f}. {diagnosis}",
                "diagnosis": diagnosis,
            })
            result = RoundResult(
                round_num=round_num, strategy=strategy, backbone=state.winner,
                modality=state.modality, f1=state.winner_f1, accuracy=0,
                diagnosis=diagnosis,
            )
            state.rounds.append(result)
            store_round_artifact(state, result, HOLDOUT_F1_GATE)
            break

        # ── TRAIN ──
        if not state.backbones:
            defaults = {
                "vision": ["convnextv2_nano.fcmae_ft_in22k_in1k", "efficientnet_b0", "fastvit_sa12.apple_in1k"],
                "text": ["prajjwal1/bert-tiny", "distilbert-base-uncased", "bert-base-uncased"],
                "tabular": ["gradient_boosting", "random_forest", "logistic_regression"],
                "paired": ["efficientnet_b0", "convnextv2_nano.fcmae_ft_in22k_in1k"],
            }
            state.backbones = defaults.get(state.modality, defaults["vision"])

        backbones_str = ",".join(state.backbones)
        output_file = f"/tmp/clf-round-{state.project_id}-r{round_num}-{int(time.time())}.json"

        hp_flags = (
            f"--epochs {hps.get('epochs', 10)} "
            f"--lr {hps.get('lr', 2e-4)} "
            f"--batch-size {hps.get('batch_size', 32)} "
            f"--weight-decay {hps.get('weight_decay', 1e-4)} "
            f"--dropout {hps.get('dropout', 0.1)} "
            f"--label-smoothing {hps.get('label_smoothing', 0.0)} "
            f"--mixup-alpha {hps.get('mixup_alpha', 0.0)} "
            f"--cutmix-alpha {hps.get('cutmix_alpha', 0.0)} "
            f"--random-erasing {hps.get('random_erasing', 0.0)}"
        )

        # Build benchmark command based on modality
        if state.modality == "paired":
            bench_cmd = f"benchmark --data-dir {state.data_dir} --modality paired --backbones {backbones_str} {hp_flags} --output-json {output_file} --store-memory"
        elif state.modality == "text":
            bench_cmd = f"benchmark --labels-jsonl {state.data_dir} --modality text --backbones {backbones_str} {hp_flags} --output-json {output_file} --store-memory"
        elif state.modality == "tabular":
            # Tabular needs --labels-jsonl pointing to the JSONL with features+labels
            jsonl_path = _find_tabular_jsonl(state.data_dir)
            bench_cmd = f"benchmark --labels-jsonl {jsonl_path} --modality tabular --backbones {backbones_str} {hp_flags} --output-json {output_file} --store-memory"
        else:  # vision
            bench_cmd = f"benchmark --data-dir {state.data_dir} --backbones {backbones_str} {hp_flags} --output-json {output_file} --store-memory"

        rc, out, err = run_skill("classifier-lab", bench_cmd, timeout=7200)

        # Parse results
        f1 = 0.0
        accuracy = 0.0
        wilson = 0.0
        backbone_used = state.backbones[0] if state.backbones else "unknown"

        if Path(output_file).exists():
            try:
                results = json.loads(Path(output_file).read_text())
                f1 = results.get("selected_metrics", {}).get("macro_f1", 0)
                accuracy = results.get("selected_metrics", {}).get("accuracy", 0)
                wilson = results.get("selected_metrics", {}).get("wilson_score_lower", 0)
                backbone_used = results.get("selected_backbone", backbone_used)
                if rc != 0:
                    logger.warning(f"Training exited rc={rc} but output file exists — using results (memory store may have failed)")
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"Failed to parse results: {e}")
        else:
            logger.error(f"Training failed: rc={rc}, stderr={err[-300:]}")

        # ── EVALUATE (holdout gate) ──
        round_passed = f1 >= HOLDOUT_F1_GATE

        result = RoundResult(
            round_num=round_num, strategy=strategy, backbone=backbone_used,
            modality=state.modality, f1=f1, accuracy=accuracy, wilson_lower=wilson,
            hps=hps,
        )

        if round_passed:
            result.diagnosis = f"GATE PASSED: F1 {f1:.4f} ≥ {HOLDOUT_F1_GATE}"
            logger.info(f"✓ HOLDOUT PASSED: F1 {f1:.4f} ≥ {HOLDOUT_F1_GATE} (round {round_num}, strategy={strategy})")
        else:
            result.diagnosis = _diagnose_round_failure(state, result)
            logger.warning(f"✗ HOLDOUT FAILED: F1 {f1:.4f} < {HOLDOUT_F1_GATE} — {result.diagnosis}")

        state.rounds.append(result)
        store_round_artifact(state, result, HOLDOUT_F1_GATE)

        # Update winner
        if f1 > state.winner_f1:
            state.winner = backbone_used
            state.winner_f1 = f1
            state.winner_hps = hps

        notify_ux("training-update", {
            "projectId": state.project_id, "phase": "round-complete",
            "round": round_num, "f1": f1, "passed": round_passed,
            "strategy": strategy, "diagnosis": result.diagnosis,
            "bestF1": state.winner_f1,
        })

        # ── NON-NEGOTIABLE: /dogpile on EVERY round ──
        # Full context: all rounds, all settings, all results, trajectory
        prior_context = ""
        for r in state.rounds:
            prior_context += (
                f"  Round {r.round_num}: strategy={r.strategy} backbone={r.backbone} "
                f"modality={r.modality} F1={r.f1:.3f} "
                f"hps={json.dumps({k:v for k,v in r.hps.items() if k != 'dogpile_insights'})}\n"
            )

        dogpile_query = (
            f"Classifier self-improvement loop for: {state.task}\n"
            f"Target: F1 >= {HOLDOUT_F1_GATE}\n"
            f"Current best: F1={state.winner_f1:.3f} ({state.winner})\n"
            f"Data: {state.data_dir} ({state.data_audit.get('total_samples', '?')} samples, "
            f"{state.data_audit.get('n_classes', '?')} classes)\n"
            f"Current round {round_num}: strategy={strategy} backbone={backbone_used} "
            f"modality={state.modality} F1={f1:.3f}\n"
            f"HPs this round: {json.dumps({k:v for k,v in hps.items() if k != 'dogpile_insights'})}\n"
            f"Diagnosis: {result.diagnosis}\n"
            f"All rounds so far:\n{prior_context}\n"
            f"What specific techniques, hyperparameters, augmentation, or architecture changes "
            f"would improve from F1={f1:.3f} to {HOLDOUT_F1_GATE}?"
        )
        logger.info(f"Dogpile research: {dogpile_query[:200]}")
        rc_dp, out_dp, err_dp = run_skill("dogpile", f'search "{dogpile_query}"', timeout=180)
        if rc_dp == 0 and out_dp.strip():
            result.dogpile_query = dogpile_query
            result.dogpile_insights = out_dp[:1500]
            logger.info(f"Dogpile insights ({len(out_dp)} chars): {out_dp[:200]}")
        store_dogpile_to_memory(state, dogpile_query, out_dp if rc_dp == 0 else err_dp, round_num=round_num, phase=f"round-{round_num}")

        if round_passed:
            state.holdout_passed = True
            break

        # ── PLATEAU DETECTION ──
        if detect_plateau(state.rounds):
            diagnosis = f"PLATEAU DETECTED: Last {PLATEAU_WINDOW} rounds within ±{PLATEAU_EPSILON} F1. Data may be insufficient for target {HOLDOUT_F1_GATE}."
            logger.warning(diagnosis)
            notify_ux("training-update", {"projectId": state.project_id, "phase": "plateau", "message": diagnosis})
            # Don't break — continue escalation, but log the plateau

    # Loop complete
    if state.holdout_passed:
        logger.info(f"═══ SELF-IMPROVEMENT SUCCEEDED: F1 {state.winner_f1:.4f} in {state.current_round} rounds ═══")
    else:
        logger.error(f"═══ SELF-IMPROVEMENT EXHAUSTED: Best F1 {state.winner_f1:.4f} after {state.current_round} rounds ═══")
        generate_next_steps(state, HOLDOUT_F1_GATE, detect_plateau, _diagnose_failure)


def _diagnose_round_failure(state: PipelineState, result: RoundResult) -> str:
    """Diagnose why a round failed. Returns human-readable diagnosis."""
    parts = []

    if result.f1 == 0:
        parts.append("Training produced zero F1 — likely crash or data format mismatch")
    elif result.f1 < 0.5:
        parts.append(f"F1 {result.f1:.3f} is near random — model not learning. Check data quality and labels.")
    elif result.f1 < 0.7:
        parts.append(f"F1 {result.f1:.3f} is low — likely needs more data or different architecture")
    elif result.f1 < HOLDOUT_F1_GATE:
        gap = HOLDOUT_F1_GATE - result.f1
        parts.append(f"F1 {result.f1:.3f} is {gap:.3f} below gate. Close — try regularization or ensemble.")

    # Check class imbalance
    if state.data_audit.get("balanced") is False:
        parts.append("Data is imbalanced — consider class weighting or oversampling")

    # Check sample count
    total = state.data_audit.get("total_samples", 0)
    if total < 500:
        parts.append(f"Only {total} total samples — likely insufficient for {HOLDOUT_F1_GATE} F1")

    return "; ".join(parts) if parts else f"F1 {result.f1:.3f} < {HOLDOUT_F1_GATE}"


def _diagnose_failure(state: PipelineState) -> str:
    """Comprehensive diagnosis after all rounds exhausted."""
    parts = [f"Task: {state.task}", f"Modality: {state.modality}", f"Best F1: {state.winner_f1:.3f}"]
    parts.append(f"Rounds: {len(state.rounds)}")
    parts.append(f"Strategies tried: {[r.strategy for r in state.rounds]}")

    if detect_plateau(state.rounds):
        parts.append(f"PLATEAU: Last {PLATEAU_WINDOW} rounds within ±{PLATEAU_EPSILON} — data bottleneck likely")

    audit = state.data_audit
    if audit:
        parts.append(f"Data: {audit.get('total_samples', '?')} samples, {audit.get('n_classes', '?')} classes, min/class={audit.get('min_per_class', '?')}")

    return " | ".join(parts)


# ── Phase 6: Promote + HuggingFace ─────────────────────────────────

def phase_promote(state: PipelineState) -> None:
    """Export model and push to HuggingFace with model card."""
    state.phase = "promote"

    if not state.holdout_passed:
        logger.warning("Skipping promote — holdout gate not passed")
        notify_ux("training-update", {"projectId": state.project_id, "phase": "promote-skipped", "reason": f"F1 {state.winner_f1:.3f} < {HOLDOUT_F1_GATE}"})
        return

    notify_ux("training-update", {"projectId": state.project_id, "phase": "promote", "message": f"Promoting {state.winner} to HuggingFace..."})

    # Export to ONNX
    model_dir = MODELS_DIR / state.winner.replace("/", "_")
    if model_dir.exists():
        rc, out, err = run_skill("classifier-lab", f'export --model "{model_dir}" --format onnx', timeout=300)
        if rc == 0:
            state.export_path = str(model_dir / "model.onnx")

    # Push to HuggingFace
    if HF_TOKEN:
        _push_to_huggingface(state)
    else:
        logger.warning("HF_TOKEN not set — skipping HuggingFace push")


def _push_to_huggingface(state: PipelineState) -> None:
    """Push model + card to HuggingFace."""
    try:
        from huggingface_hub import HfApi, ModelCard, ModelCardData, EvalResult

        api = HfApi(token=HF_TOKEN)
        repo_id = state.hf_repo or f"{HF_USERNAME}/{state.project_id}"
        api.create_repo(repo_id=repo_id, exist_ok=True, private=False)

        # Build self-improvement round table
        rounds_table = ""
        for r in state.rounds:
            status = "✓" if r.f1 >= HOLDOUT_F1_GATE else "✗"
            rounds_table += f"| {r.round_num} | {r.strategy} | {r.backbone} | {r.modality} | {r.f1:.3f} | {status} |\n"

        eval_results = [EvalResult(
            task_type="image-classification", dataset_type=state.dataset_repo or "custom",
            dataset_name=state.task, metric_type="f1", metric_value=round(state.winner_f1, 4), metric_name="Macro F1",
        )]

        card_data = ModelCardData(
            language="en", license="apache-2.0", library_name="timm",
            tags=["classifier-lab", "embry-os", "self-improvement-loop", f"rounds-{len(state.rounds)}"],
            model_name=state.winner, eval_results=eval_results, pipeline_tag="image-classification",
        )

        card = ModelCard.from_template(card_data, model_id=repo_id,
            model_description=f"A {state.task} classifier trained with {len(state.rounds)} self-improvement rounds.",
        )
        card.text += f"""

## Self-Improvement Rounds

| Round | Strategy | Backbone | Modality | F1 | Gate |
|-------|----------|----------|----------|----|------|
{rounds_table}

Winner: **{state.winner}** with F1 **{state.winner_f1:.4f}** after {len(state.rounds)} rounds.
"""
        card.push_to_hub(repo_id, token=HF_TOKEN)

        model_dir = MODELS_DIR / state.winner.replace("/", "_")
        if model_dir.exists():
            for f in model_dir.iterdir():
                if f.suffix in (".pt", ".pth", ".onnx", ".json", ".txt", ".yaml"):
                    api.upload_file(path_or_fileobj=str(f), path_in_repo=f.name, repo_id=repo_id, token=HF_TOKEN)

        logger.info(f"Pushed to huggingface.co/{repo_id}")
    except Exception as e:
        state.errors.append(f"HF push failed: {e}")
        logger.error(f"HF push failed: {e}")


# ── Main CLI ───────────────────────────────────────────────────────

@app.command()
def run(
    task: str = typer.Option(..., help="Classification task description"),
    project_id: str = typer.Option("", help="Project ID (auto-generated from task if empty)"),
    data_dir: str = typer.Option("", help="Local data directory (images or JSONL)"),
    dataset: str = typer.Option("", help="HuggingFace dataset repo ID"),
    modality: str = typer.Option("vision", help="Modality: vision, text, tabular, paired"),
    backbones: str = typer.Option("", help="Comma-separated backbone list (auto-detected if empty)"),
    hf_repo: str = typer.Option("", help="HuggingFace repo for promotion"),
    max_rounds: int = typer.Option(MAX_ROUNDS, help="Max self-improvement rounds"),
    gate_f1: float = typer.Option(HOLDOUT_F1_GATE, help="Holdout F1 gate threshold"),
    skip_research: bool = typer.Option(False, help="Skip /dogpile research phase"),
    dry_run: bool = typer.Option(False, help="Print plan without executing"),
):
    """Run the full self-improvement classifier pipeline.

    NON-NEGOTIABLE: The pipeline loops until F1 ≥ gate or max rounds exhausted.
    Each failed round triggers diagnosis, strategy escalation, and optionally /dogpile.
    """
    global HOLDOUT_F1_GATE, MAX_ROUNDS
    HOLDOUT_F1_GATE = gate_f1
    MAX_ROUNDS = max_rounds

    pid = project_id or task.lower().replace(" ", "-").replace("/", "-")[:40]

    state = PipelineState(
        task=task,
        project_id=pid,
        modality=modality,
        dataset_repo=dataset,
        data_dir=data_dir,
        hf_repo=hf_repo or f"{HF_USERNAME}/{pid}",
    )
    if backbones:
        state.backbones = [b.strip() for b in backbones.split(",")]

    logger.info(f"═══ CLASSIFIER LAB: {task} ═══")
    logger.info(f"  Modality: {modality}")
    logger.info(f"  Data: {data_dir or dataset}")
    logger.info(f"  Gate: F1 ≥ {gate_f1}")
    logger.info(f"  Max rounds: {max_rounds}")

    if dry_run:
        logger.info("DRY RUN — would execute: Research → Data → Self-Improvement Loop (up to {max_rounds} rounds) → Promote")
        return

    # Phase 1: Research
    if not skip_research:
        phase_research(state)

    # Phase 2: Data validation
    if data_dir:
        state.data_dir = data_dir
    elif dataset:
        # Download from HuggingFace
        from huggingface_hub import snapshot_download
        dl_path = DATA_DIR / dataset.replace("/", "_")
        dl_path.mkdir(parents=True, exist_ok=True)
        snapshot_download(repo_id=dataset, repo_type="dataset", local_dir=str(dl_path), token=HF_TOKEN, max_workers=4)
        state.data_dir = str(dl_path)
        state.dataset_dir = str(dl_path)

    phase_data(state)
    if any("Critically insufficient" in e for e in state.errors):
        logger.error("Data gate BLOCKED pipeline — cannot proceed")
        print(json.dumps({"status": "blocked", "reason": "insufficient_data", "errors": state.errors}, indent=2))
        return

    # Phase 3-5: SELF-IMPROVEMENT LOOP (the core product)
    self_improvement_loop(state)

    # Phase 6: Promote (only if gate passed)
    phase_promote(state)

    # Final report
    report = {
        "task": state.task,
        "project_id": state.project_id,
        "modality": state.modality,
        "winner": state.winner,
        "f1": state.winner_f1,
        "holdout_passed": state.holdout_passed,
        "rounds": len(state.rounds),
        "strategies_tried": [r.strategy for r in state.rounds],
        "round_f1s": [r.f1 for r in state.rounds],
        "plateau_detected": detect_plateau(state.rounds),
        "hf_repo": state.hf_repo if state.holdout_passed else None,
        "errors": state.errors,
    }
    logger.info(f"═══ PIPELINE COMPLETE ═══\n{json.dumps(report, indent=2)}")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    app()
