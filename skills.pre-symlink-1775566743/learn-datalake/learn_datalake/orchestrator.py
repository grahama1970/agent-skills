"""Orchestrator for self-improvement loops.

Implements the logic to chain tunable skills (tune) -> data aggregation -> model training.
Includes the Shadow-LEGO feedback loop: harvest S05 outcomes → train classifier → register.
"""

import os
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional

from loguru import logger

# Must match _CAT_ENCODER in extractor strategy_selector.py
_KNOWN_CATEGORIES = ["unknown", "scientific", "defense", "financial", "medical", "legal", "general"]
_CAT_ENCODER = {cat: i for i, cat in enumerate(_KNOWN_CATEGORIES)}
# Case-insensitive lookup
_CAT_ENCODER.update({cat.capitalize(): i for i, cat in enumerate(_KNOWN_CATEGORIES)})


def _encode_category(raw: str) -> int:
    """Encode category string to int matching strategy_selector._CAT_ENCODER."""
    return _CAT_ENCODER.get(raw, 0)


from .config import (
    ASSISTANT_RUN,
    DEBUG_TABLE_PATH,
    EXTRACTOR_ROOT,
    MIN_PROMOTION_EXAMPLES,
    MIN_TRAINING_EXAMPLES,
    PROMOTION_F1_THRESHOLD,
    STRATEGY_MODEL_DIR,
    STRATEGY_OUTCOMES_EXTRA_DIRS,
    STRATEGY_OUTCOMES_GLOB,
    STRATEGY_TRAINING_DIR,
)


def harvest_strategy_outcomes(data_root: Optional[Path] = None) -> int:
    """Harvest 05_strategy_outcomes.jsonl from all extraction runs.

    Globs across data dirs, deduplicates by (pdf_stem, page_num),
    transforms into classifier-lab tabular JSONL, writes labels.jsonl.

    Returns record count written.
    """
    if data_root is None:
        data_root = EXTRACTOR_ROOT

    outcome_files = sorted(data_root.glob(STRATEGY_OUTCOMES_GLOB))
    # Also search extra dirs (e.g. review-pdf extracted runs on storage)
    for extra_dir in STRATEGY_OUTCOMES_EXTRA_DIRS:
        if extra_dir.exists():
            outcome_files.extend(sorted(extra_dir.glob("**/05_strategy_outcomes.jsonl")))
    if not outcome_files:
        logger.info("No strategy outcome files found")
        return 0
    logger.info(f"Found {len(outcome_files)} strategy outcome files")

    seen = set()
    records = []

    for fpath in outcome_files:
        # Derive pdf_stem from extraction output dir
        # File is at .../pdf_name/05_table_extractor/visual_output/05_strategy_outcomes.jsonl
        # Walk up from file to find the extraction output dir (parent of 05_table_extractor)
        pdf_stem = fpath.parent.name  # default: immediate parent
        for parent in fpath.parents:
            if parent.name == "05_table_extractor":
                pdf_stem = parent.parent.name
                break
        try:
            for line in fpath.read_text().strip().splitlines():
                rec = json.loads(line)
                page_num = rec.get("page_num")
                key = (pdf_stem, page_num)
                if key in seen:
                    continue
                seen.add(key)

                actual = rec.get("actual_best")
                if not actual:
                    continue

                # Build feature dict from S00 profile + page-level stats
                page_stats = rec.get("page_stats", {})
                frag_scores = rec.get("fragmentation_scores", {})
                frag_vals = [v for v in frag_scores.values() if isinstance(v, (int, float))]

                # Per-strategy fragmentation scores (key signal)
                all_strategies = [
                    "lattice_default", "lattice_strong",
                    "stream_default", "stream_tight", "stream_wide",
                    "stream_columns", "agent_tuned", "memory_learned",
                ]
                strat_feats = {}
                for s in all_strategies:
                    val = frag_scores.get(s, -1)  # -1 = not tried
                    strat_feats[f"frag_{s}"] = val if isinstance(val, (int, float)) else -1

                features = {
                    # S00 profile features
                    "table_style_borderless": int(rec.get("s00_table_style") == "borderless"),
                    "table_style_bordered": int(rec.get("s00_table_style") == "bordered"),
                    "table_style_mixed": int(rec.get("s00_table_style") == "mixed"),
                    "domain_scientific": int(rec.get("s00_domain") == "scientific"),
                    "domain_defense": int(rec.get("s00_domain") == "defense"),
                    "domain_engineering": int(rec.get("s00_domain") == "engineering"),
                    "category": _encode_category(rec.get("category", "unknown")),
                    # Page-level features (from page_stats if available)
                    "num_tables": page_stats.get("num_tables", len(frag_scores)),
                    "num_strategies_tried": page_stats.get("num_strategies_tried", len(rec.get("strategies_tried", []))),
                    "max_fragmentation": page_stats.get("max_fragmentation", max(frag_vals) if frag_vals else 0),
                    "has_fragmentation": page_stats.get("has_fragmentation", int(any(f > 0 for f in frag_vals))),
                    "lattice_found": page_stats.get("lattice_found", 0),
                    "stream_found": page_stats.get("stream_found", 0),
                    # Per-strategy fragmentation scores
                    **strat_feats,
                }

                records.append({
                    "features": features,
                    "label": actual,
                })
        except Exception as exc:
            logger.warning(f"Failed to parse {fpath}: {exc}")
            continue

    if not records:
        logger.info("No valid strategy outcome records after dedup")
        return 0

    STRATEGY_TRAINING_DIR.mkdir(parents=True, exist_ok=True)
    labels_path = STRATEGY_TRAINING_DIR / "labels.jsonl"
    with open(labels_path, "w") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    logger.info(f"Harvested {len(records)} strategy outcomes → {labels_path}")
    return len(records)


def train_strategy_classifier() -> Optional[Dict]:
    """Phase 2: Train strategy classifier via /classifier-lab tabular benchmark.

    Uses /classifier-lab to benchmark backbones and save the winning model.
    Falls back to bespoke train_strategy.py if classifier-lab is unavailable.

    Returns metrics dict or None if insufficient data.
    """
    labels_path = STRATEGY_TRAINING_DIR / "labels.jsonl"
    if not labels_path.exists():
        logger.info("No labels.jsonl found — skipping training")
        return None

    n_lines = sum(1 for _ in open(labels_path))
    if n_lines < MIN_TRAINING_EXAMPLES:
        logger.info(f"Only {n_lines} examples (need {MIN_TRAINING_EXAMPLES}) — skipping training")
        return None

    STRATEGY_MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # Try /classifier-lab first (Embry OS design pattern)
    from .config import CLASSIFIER_LAB_SCRIPTS, CLASSIFIER_LAB_VENV

    benchmark_py = CLASSIFIER_LAB_SCRIPTS / "benchmark.py"
    lab_python = CLASSIFIER_LAB_VENV / "bin" / "python"

    if benchmark_py.exists() and lab_python.exists():
        try:
            result = subprocess.run(
                [
                    str(lab_python), str(benchmark_py),
                    "--modality", "tabular",
                    "--labels-jsonl", str(labels_path),
                    "--backbones", "gradient_boosting,random_forest,logistic_regression",
                    "--output-dir", str(STRATEGY_MODEL_DIR),
                    "--output-json", str(STRATEGY_MODEL_DIR / "benchmark_report.json"),
                    "--no-store-memory",
                ],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(CLASSIFIER_LAB_SCRIPTS),
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            if result.returncode == 0:
                report = json.loads(result.stdout)
                if report.get("status") == "ok":
                    metrics = {
                        "accuracy": report["selected_metrics"]["accuracy"],
                        "macro_f1": report["selected_metrics"]["macro_f1"],
                        "n_samples": n_lines,
                        "best_model": report["selected_backbone"],
                        "source": "classifier-lab",
                    }
                    logger.info(f"classifier-lab training complete: {metrics}")
                    return metrics
                else:
                    logger.warning(f"classifier-lab returned non-ok: {report.get('reason')}")
            else:
                logger.warning(f"classifier-lab failed (rc={result.returncode}): {result.stderr[:200]}")
        except Exception as exc:
            logger.warning(f"classifier-lab error: {exc}")

    # Fallback: bespoke train_strategy.py
    logger.info("Falling back to bespoke train_strategy.py")
    from .train_strategy import train_and_evaluate

    metrics = train_and_evaluate(labels_path, STRATEGY_MODEL_DIR)
    logger.info(f"Training complete (fallback): {metrics}")
    return metrics


def register_with_assistant() -> bool:
    """Register/update the table-strategy-selector in /assistant registry."""
    if not ASSISTANT_RUN.exists():
        logger.warning(f"/assistant run.sh not found at {ASSISTANT_RUN}")
        return False

    try:
        result = subprocess.run(
            [
                str(ASSISTANT_RUN), "register",
                "--task", "table-strategy-selector",
                "--type", "sklearn",
                "--model-path", str(STRATEGY_MODEL_DIR / "model.joblib"),
                "--threshold", "0.85",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode == 0:
            logger.info("Registered table-strategy-selector with /assistant")
            return True
        else:
            logger.warning(f"/assistant register failed: {result.stderr}")
            return False
    except Exception as exc:
        logger.warning(f"/assistant register error: {exc}")
        return False


def check_promotion_gate(metrics: Optional[Dict] = None) -> bool:
    """Check if trained model meets promotion threshold (shadow → active).

    Does NOT auto-flip the env var. Writes PROMOTE_READY.md recommendation.
    Returns True if model meets promotion criteria.
    """
    if metrics is None:
        metrics_path = STRATEGY_MODEL_DIR / "metrics.json"
        if not metrics_path.exists():
            return False
        metrics = json.loads(metrics_path.read_text())

    macro_f1 = metrics.get("macro_f1", 0.0)
    n_samples = metrics.get("n_samples", 0)

    if macro_f1 >= PROMOTION_F1_THRESHOLD and n_samples >= MIN_PROMOTION_EXAMPLES:
        # Write promotion recommendation
        promote_path = STRATEGY_MODEL_DIR / "PROMOTE_READY.md"
        promote_path.write_text(
            f"# Strategy Classifier Ready for Promotion\n\n"
            f"- **macro_f1**: {macro_f1:.4f} (threshold: {PROMOTION_F1_THRESHOLD})\n"
            f"- **n_samples**: {n_samples} (threshold: {MIN_PROMOTION_EXAMPLES})\n\n"
            f"To promote from shadow to active:\n"
            f"```bash\n"
            f"export STRATEGY_SELECTOR_MODE=active\n"
            f"```\n\n"
            f"Or update `/assistant` registry: set `shadow_mode: false`\n"
        )

        # Update /assistant registry shadow_mode if available
        try:
            subprocess.run(
                [
                    str(ASSISTANT_RUN), "register",
                    "--task", "table-strategy-selector",
                    "--type", "sklearn",
                    "--model-path", str(STRATEGY_MODEL_DIR / "model.joblib"),
                    "--threshold", str(PROMOTION_F1_THRESHOLD),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
        except Exception:
            pass

        logger.info(f"Promotion gate PASSED: f1={macro_f1:.4f}, n={n_samples}")
        return True

    logger.info(
        f"Promotion gate not met: f1={macro_f1:.4f} (need {PROMOTION_F1_THRESHOLD}), "
        f"n={n_samples} (need {MIN_PROMOTION_EXAMPLES})"
    )
    return False


def run_learning_cycle(data_root: Optional[Path] = None) -> Dict:
    """Run the full Shadow-LEGO learning cycle.

    Phase 1:   Tune corpus (table-lab) — existing
    Phase 1.5: Harvest strategy outcomes
    Phase 2:   Train classifier (if sufficient data)
    Phase 2.5: Register with /assistant
    Phase 3:   Check promotion gate

    Returns summary dict.
    """
    summary = {"phase_1_5_harvested": 0, "phase_2_trained": False, "phase_3_promoted": False}

    # Phase 1.5: Harvest strategy outcomes
    logger.info("Phase 1.5: Harvesting strategy outcomes...")
    n_harvested = harvest_strategy_outcomes(data_root)
    summary["phase_1_5_harvested"] = n_harvested

    if n_harvested < MIN_TRAINING_EXAMPLES:
        logger.info(f"Insufficient data ({n_harvested}/{MIN_TRAINING_EXAMPLES}) — stopping")
        return summary

    # Phase 2: Train classifier
    logger.info("Phase 2: Training strategy classifier...")
    metrics = train_strategy_classifier()
    if metrics is not None:
        summary["phase_2_trained"] = True
        summary["metrics"] = metrics

        # Phase 2.5: Register with /assistant
        register_with_assistant()

        # Phase 3: Check promotion gate
        promoted = check_promotion_gate(metrics)
        summary["phase_3_promoted"] = promoted

    return summary


def run_table_loop(glob_pattern: str, dry_run: bool = False, monitor: bool = True) -> None:
    """Run the Table Extraction Improvement Loop.

    Phase 1: Tune Corpus (table-lab)
    Phase 1.5-3: Shadow-LEGO feedback loop (harvest → train → promote)
    """
    logger.info("Phase 1: Tuning corpus tables...")

    cmd = [
        str(DEBUG_TABLE_PATH / "run.sh"),
        "tune-corpus",
        "--glob",
        glob_pattern,
    ]

    if monitor:
        cmd.append("--task-monitor")

    logger.debug(f"Executing: {' '.join(cmd)}")

    if dry_run:
        logger.info("[Dry Run] Would execute table-lab tune-corpus")
        return

    try:
        # Stream output from subprocess
        with subprocess.Popen(
            cmd,
            cwd=DEBUG_TABLE_PATH,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        ) as proc:
            for line in proc.stdout:
                print(line, end="")  # Pass through stdout

            proc.wait()

            if proc.returncode != 0:
                logger.error(f"Phase 1 failed with exit code {proc.returncode}")
                # Read stderr specifically for error details
                print(proc.stderr.read(), file=sys.stderr)
                raise subprocess.CalledProcessError(proc.returncode, cmd)

        # Phase 1.5–3: Shadow-LEGO feedback loop
        logger.info("Phase 1 complete. Running Shadow-LEGO feedback loop...")
        summary = run_learning_cycle()
        logger.info(f"Learning cycle summary: {summary}")

    except FileNotFoundError:
        logger.error(f"Could not find run.sh at {DEBUG_TABLE_PATH}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Table loop failed: {e}")
        sys.exit(1)
