#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["scikit-learn>=1.3", "loguru", "typer"]
# ///
"""Extractability predictor — learns which PDFs will succeed from S00 features.

Parses learn-datalake run logs to extract S00 features and extraction outcomes,
trains a logistic regression model, and persists it for preflight gating.

Features (all from S00 profile detector, available before extraction starts):
- page_count, estimated_timeout, estimated_sections (regex/font/toc)
- table_count, table_pages, image_pages, max_tables_per_page, table_pages_drawing
- has_formulas, has_figures, has_requirements, has_tables, has_structure
- derived: sections_disagreement (font vs regex spread), section_density (sections/pages)

Usage:
    uv run --script extractability_model.py train          # Train from logs
    uv run --script extractability_model.py predict <pdf>  # Predict extractability
    uv run --script extractability_model.py emit-labels    # Emit /create-classifier labels
"""

from __future__ import annotations

import json
import os
import pickle
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import typer
from loguru import logger

app = typer.Typer(no_args_is_help=True, add_completion=False)

SKILL_DIR = Path(__file__).resolve().parent
STATE_DIR = SKILL_DIR / "state"
MODEL_PATH = STATE_DIR / "extractability_model.pkl"
FEATURE_NAMES_PATH = STATE_DIR / "extractability_features.json"
TRAINING_DATA_PATH = STATE_DIR / "extractability_training.jsonl"
LABELS_PATH = STATE_DIR / "extractability_labels.jsonl"
LOG_DIR = STATE_DIR / "runs"

# Extraction run directories
_SKILLS_DIR = Path(__file__).resolve().parent.parent
_EMBRY_STORAGE = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb"))
EXTRACTED_RUNS_NVME = _SKILLS_DIR / "review-pdf" / "extracted_runs_staging"
EXTRACTED_RUNS_HDD = _EMBRY_STORAGE / "skills/review-pdf/extracted_runs"

# S00 features extracted from extract_timeout log lines
S00_FEATURE_KEYS = [
    "page_count",
    "step00_estimated",
    "step00_estimated_sections",
    "step00_estimated_sections_regex",
    "step00_estimated_sections_font",
    "step00_estimated_sections_toc",
    "step00_estimated_table_count",
    "step00_table_pages",
    "step00_image_pages",
    "step00_max_tables_per_page",
    "step00_table_pages_drawing",
    "step00_has_formulas",
    "step00_has_figures",
    "step00_has_requirements",
    "step00_has_tables",
    "step00_has_structure",
]

# Features from scanned_pdf.json + profile.json (available for all extracted runs)
RUN_DIR_FEATURES = [
    "is_scanned",             # 0/1 from scanned_pdf.json
    "text_page_ratio",        # 0.0-1.0 ratio of pages with text
    "total_text_chars",       # Total chars across sampled pages
    "text_chars_per_page",    # total_text_chars / max(page_count, 1)
    "file_size_mb",           # From profile.json
    "font_body_size",         # Body font size (0 if unavailable)
    "preset_confidence",      # Preset match confidence score
    "has_toc",                # 0/1 whether TOC was detected
    "toc_entry_count",        # Number of TOC entries
    "section_breakdown_total", # Sum of decimal+labeled+roman+alpha counts
    "section_breakdown_diversity", # How many non-zero breakdown categories
]

# Derived features computed from S00 raw features
DERIVED_FEATURES = [
    "sections_disagreement",   # max(regex, font, toc) - min(regex, font, toc)
    "section_density",         # estimated_sections / page_count
    "table_density",           # table_pages / page_count
    "has_any_content_signal",  # has_formulas | has_tables | has_figures | has_requirements
    "sections_to_pages_ratio", # estimated_sections / max(page_count, 1)
    "regex_font_ratio",        # regex / max(font, 1)
    "toc_coverage",            # toc / max(estimated_sections, 1)
    "bytes_per_page",          # file_size_mb * 1024 / max(page_count, 1)
    "text_density_signal",     # text_chars_per_page * has_structure
    "toc_section_ratio",       # toc_entry_count / max(estimated_sections, 1)
]


def _parse_kv_line(line: str) -> Dict[str, str]:
    """Parse key=value pairs from a log line."""
    pairs: Dict[str, str] = {}
    for match in re.finditer(r'(\w+)=(\S+)', line):
        pairs[match.group(1)] = match.group(2)
    return pairs


def _extract_features(kv: Dict[str, str]) -> Optional[Dict[str, float]]:
    """Extract numeric features from parsed key-value pairs (log-based)."""
    features: Dict[str, float] = {}
    for key in S00_FEATURE_KEYS:
        val = kv.get(key)
        if val is None:
            return None
        try:
            features[key] = float(val)
        except ValueError:
            return None

    # Run-dir features default to 0 when only log-based features are available
    for key in RUN_DIR_FEATURES:
        features.setdefault(key, 0.0)

    _compute_derived(features)
    return features


def _enrich_from_run_dir(features: Dict[str, float], pdf_path: str) -> Dict[str, float]:
    """Enrich features with data from the extraction run directory.

    Reads scanned_pdf.json and profile.json from the run dir to add
    features not available in the log lines.
    """
    run_dir = _find_run_dir(pdf_path)
    if run_dir is None:
        return features

    # scanned_pdf.json
    scanned_path = run_dir / "scanned_pdf.json"
    if scanned_path.exists():
        try:
            scanned = json.loads(scanned_path.read_text())
            features["is_scanned"] = float(scanned.get("is_scanned", False))
            features["text_page_ratio"] = float(scanned.get("text_page_ratio", 0.0))
            features["total_text_chars"] = float(scanned.get("total_text_chars", 0))
            pages = max(features.get("page_count", 1), 1)
            features["text_chars_per_page"] = features["total_text_chars"] / pages
        except (json.JSONDecodeError, ValueError):
            pass

    # profile.json
    profile_path = run_dir / "00_profile_detector" / "profile.json"
    if profile_path.exists():
        try:
            profile = json.loads(profile_path.read_text())
            features["file_size_mb"] = float(profile.get("file_size_mb", 0))
            h = profile.get("hierarchy", {})
            features["font_body_size"] = float(h.get("font_body_size", 0) or 0)
            pm = profile.get("preset_match", {})
            features["preset_confidence"] = float(pm.get("confidence", 0))
            toc = profile.get("toc", {})
            features["has_toc"] = float(toc.get("has_toc", False))
            features["toc_entry_count"] = float(len(toc.get("entries", [])))
            breakdown = h.get("section_breakdown", {})
            bd_vals = [float(breakdown.get(k, 0)) for k in ("decimal", "labeled", "roman", "alpha")]
            features["section_breakdown_total"] = sum(bd_vals)
            features["section_breakdown_diversity"] = float(sum(1 for v in bd_vals if v > 0))
        except (json.JSONDecodeError, ValueError):
            pass

    # Recompute derived features with enriched data
    _compute_derived(features)
    return features


def _find_run_dir(pdf_path: str) -> Optional[Path]:
    """Find the extraction run directory for a PDF path."""
    stem = Path(pdf_path).stem
    # Run dirs are named {stem}_{hash10} — search both locations
    for runs_dir in (EXTRACTED_RUNS_NVME, EXTRACTED_RUNS_HDD):
        if not runs_dir.is_dir():
            continue
        for entry in runs_dir.iterdir():
            if entry.name.startswith(stem):
                # Resolve symlinks
                target = entry.resolve() if entry.is_symlink() else entry
                if target.is_dir():
                    return target
    return None


def _compute_derived(features: Dict[str, float]) -> None:
    """Compute derived features in-place."""
    regex = features.get("step00_estimated_sections_regex", 0)
    font = features.get("step00_estimated_sections_font", 0)
    toc = features.get("step00_estimated_sections_toc", 0)
    pages = max(features.get("page_count", 1), 1)
    est_sections = max(features.get("step00_estimated_sections", 1), 1)

    features["sections_disagreement"] = max(regex, font, toc) - min(regex, font, toc)
    features["section_density"] = features.get("step00_estimated_sections", 0) / pages
    features["table_density"] = features.get("step00_table_pages", 0) / pages
    features["has_any_content_signal"] = float(
        features.get("step00_has_formulas", 0)
        or features.get("step00_has_tables", 0)
        or features.get("step00_has_figures", 0)
        or features.get("step00_has_requirements", 0)
    )
    features["sections_to_pages_ratio"] = features.get("step00_estimated_sections", 0) / pages
    features["regex_font_ratio"] = regex / max(font, 1)
    features["toc_coverage"] = toc / est_sections
    features["bytes_per_page"] = features.get("file_size_mb", 0) * 1024 / pages
    features["text_density_signal"] = (
        features.get("text_chars_per_page", 0)
        * features.get("step00_has_structure", 0)
    )
    features["toc_section_ratio"] = features.get("toc_entry_count", 0) / est_sections


def _build_training_data() -> Tuple[List[Dict[str, float]], List[int], List[str]]:
    """Parse all run logs to build (features, labels, pdf_paths) training data.

    For each PDF, we look for extract_timeout (features) followed by
    extract_missing status=extracted|extract_failed (outcome).
    """
    features_list: List[Dict[str, float]] = []
    labels: List[int] = []
    pdf_paths: List[str] = []
    seen_pdfs: set[str] = set()

    log_files = sorted(LOG_DIR.glob("learn_datalake_corpus_*.log"))
    if not log_files:
        logger.warning(f"No log files found in {LOG_DIR}")
        return [], [], []

    # Track pending features (extract_timeout seen, waiting for outcome)
    pending: Dict[str, Dict[str, float]] = {}  # pdf_path -> features

    for log_file in log_files:
        try:
            text = log_file.read_text(errors="replace")
        except Exception as e:
            logger.warning(f"Cannot read {log_file}: {e}")
            continue

        for line in text.split("\n"):
            # Parse extract_timeout lines for features
            if "extract_timeout" in line and "step00_estimated" in line:
                kv = _parse_kv_line(line)
                pdf = kv.get("pdf", "")
                if not pdf:
                    continue
                feats = _extract_features(kv)
                if feats is not None:
                    pending[pdf] = feats

            # Parse outcome lines
            elif "status=extracted" in line and "extract_missing" in line:
                kv = _parse_kv_line(line)
                pdf = kv.get("pdf", "")
                if pdf in pending and pdf not in seen_pdfs:
                    features_list.append(pending.pop(pdf))
                    labels.append(1)  # success
                    pdf_paths.append(pdf)
                    seen_pdfs.add(pdf)

            elif "status=extract_failed" in line and "extract_missing" in line:
                kv = _parse_kv_line(line)
                pdf = kv.get("pdf", "")
                if pdf in pending and pdf not in seen_pdfs:
                    features_list.append(pending.pop(pdf))
                    labels.append(0)  # failure
                    pdf_paths.append(pdf)
                    seen_pdfs.add(pdf)

    # Enrich with run-dir features (scanned_pdf.json, profile.json)
    enriched = 0
    for i, (feats, pdf) in enumerate(zip(features_list, pdf_paths)):
        before_keys = sum(1 for k in RUN_DIR_FEATURES if feats.get(k, 0) != 0)
        _enrich_from_run_dir(feats, pdf)
        after_keys = sum(1 for k in RUN_DIR_FEATURES if feats.get(k, 0) != 0)
        if after_keys > before_keys:
            enriched += 1

    logger.info(
        f"Training data: {len(features_list)} samples "
        f"({sum(labels)} success, {len(labels) - sum(labels)} failure) "
        f"from {len(log_files)} log files, "
        f"{enriched} enriched from run dirs"
    )
    return features_list, labels, pdf_paths


def _feature_names() -> List[str]:
    """Ordered list of all feature names (raw + run_dir + derived)."""
    return S00_FEATURE_KEYS + RUN_DIR_FEATURES + DERIVED_FEATURES


def _features_to_vector(features: Dict[str, float]) -> List[float]:
    """Convert feature dict to ordered vector."""
    return [features.get(name, 0.0) for name in _feature_names()]


@app.command()
def train(
    min_samples: int = typer.Option(50, help="Minimum samples required to train"),
) -> None:
    """Train extractability model from run logs."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_score
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    import numpy as np

    features_list, labels, pdf_paths = _build_training_data()

    if len(features_list) < min_samples:
        logger.error(
            f"Only {len(features_list)} samples (need {min_samples}). "
            "Run more extractions first."
        )
        raise typer.Exit(code=1)

    # Save training data for reproducibility
    TRAINING_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TRAINING_DATA_PATH, "w") as f:
        for feats, label, pdf in zip(features_list, labels, pdf_paths):
            f.write(json.dumps({"features": feats, "label": label, "pdf": pdf}) + "\n")
    logger.info(f"Training data saved to {TRAINING_DATA_PATH}")

    # Convert to arrays
    X = np.array([_features_to_vector(f) for f in features_list])
    y = np.array(labels)

    n_pos = int(y.sum())
    n_neg = len(y) - n_pos
    logger.info(f"Class balance: {n_pos} extractable, {n_neg} not extractable")

    # Train logistic regression with cross-validation
    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(
            class_weight="balanced",  # Handle class imbalance
            max_iter=1000,
            C=1.0,
            random_state=42,
        )),
    ])

    # Cross-validate
    cv_scores = cross_val_score(pipeline, X, y, cv=min(5, n_neg, n_pos), scoring="f1")
    logger.info(f"Cross-validation F1: {cv_scores.mean():.3f} +/- {cv_scores.std():.3f}")

    # Also check accuracy and precision/recall
    from sklearn.metrics import classification_report
    from sklearn.model_selection import cross_val_predict
    y_pred = cross_val_predict(pipeline, X, y, cv=min(5, n_neg, n_pos))
    report = classification_report(y, y_pred, target_names=["not_extractable", "extractable"])
    print(report)

    # Train final model on all data
    pipeline.fit(X, y)

    # Feature importance (logistic regression coefficients)
    coefs = pipeline.named_steps["clf"].coef_[0]
    feature_names = _feature_names()
    importance = sorted(
        zip(feature_names, coefs),
        key=lambda x: abs(x[1]),
        reverse=True,
    )
    print("\nFeature importance (logistic regression coefficients):")
    for name, coef in importance:
        direction = "+" if coef > 0 else "-"
        print(f"  {direction} {name:40s} {coef:+.4f}")

    # Save model
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(pipeline, f)

    # Save feature names for loading
    with open(FEATURE_NAMES_PATH, "w") as f:
        json.dump(feature_names, f)

    logger.info(f"Model saved to {MODEL_PATH}")

    # Print decision threshold info
    probas = pipeline.predict_proba(X)[:, 1]
    for threshold in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
        preds = (probas >= threshold).astype(int)
        tp = ((preds == 1) & (y == 1)).sum()
        fp = ((preds == 1) & (y == 0)).sum()
        fn = ((preds == 0) & (y == 1)).sum()
        tn = ((preds == 0) & (y == 0)).sum()
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        skip_rate = (tn + fn) / len(y)
        print(
            f"  threshold={threshold:.1f}: "
            f"precision={precision:.3f} recall={recall:.3f} "
            f"skip_rate={skip_rate:.1%} "
            f"(would skip {tn + fn}/{len(y)} PDFs, miss {fn} extractable)"
        )


@app.command()
def predict(
    pdf: Path = typer.Argument(..., help="Path to PDF file"),
) -> None:
    """Predict extractability for a single PDF using S00 features."""
    if not MODEL_PATH.exists():
        logger.error(f"No model found at {MODEL_PATH}. Run 'train' first.")
        raise typer.Exit(code=1)

    # Run S00 profile detector to get features
    features = _get_s00_features(pdf)
    if features is None:
        logger.error("Could not extract S00 features from PDF")
        raise typer.Exit(code=1)

    # Load model and predict
    with open(MODEL_PATH, "rb") as f:
        pipeline = pickle.load(f)

    X = [_features_to_vector(features)]
    proba = pipeline.predict_proba(X)[0][1]
    prediction = "extractable" if proba >= 0.5 else "not_extractable"

    print(json.dumps({
        "pdf": str(pdf),
        "prediction": prediction,
        "probability": round(proba, 4),
        "features": {k: round(v, 3) for k, v in features.items()},
    }, indent=2))


def _get_s00_features(pdf_path: Path) -> Optional[Dict[str, float]]:
    """Run S00-equivalent feature extraction on a PDF without full pipeline."""
    import subprocess
    # Use the extractor's S00 profile detector directly
    cmd = (
        f"cd {_SKILLS_DIR}/extractor && "
        f'uv run python -c "'
        f"from pathlib import Path; "
        f"import sys; sys.path.insert(0, 'src'); "
        f"from extractor.pipeline.steps.s00_profile_detector import run_profile_only; "
        f"import json; "
        f"result = run_profile_only(Path('{pdf_path}')); "
        f"print(json.dumps(result))"
        f'"'
    )
    try:
        proc = subprocess.run(
            ["bash", "-lc", cmd],
            capture_output=True, text=True, timeout=60,
        )
        if proc.returncode != 0:
            logger.warning(f"S00 profile failed: {proc.stderr[:200]}")
            return None
        data = json.loads(proc.stdout.strip())
        # Map profile.json fields to our feature keys
        return _profile_json_to_features(data)
    except Exception as e:
        logger.warning(f"S00 feature extraction failed: {e}")
        return None


def _profile_json_to_features(profile: Dict[str, Any]) -> Dict[str, float]:
    """Convert a profile.json dict to our flat feature dict."""
    h = profile.get("hierarchy", {})
    e = profile.get("elements", {})
    pages = max(profile.get("page_count", 1), 1)

    raw = {
        "page_count": float(profile.get("page_count", 0)),
        "step00_estimated": float(profile.get("estimated_timeout_seconds", 0)),
        "step00_estimated_sections": float(h.get("estimated_sections", 0)),
        "step00_estimated_sections_regex": float(h.get("estimated_sections_regex", 0)),
        "step00_estimated_sections_font": float(h.get("estimated_sections_font", 0)),
        "step00_estimated_sections_toc": float(h.get("estimated_sections_toc", 0)),
        "step00_estimated_table_count": float(e.get("estimated_table_count", 0)),
        "step00_table_pages": float(e.get("table_pages", 0)),
        "step00_image_pages": float(e.get("image_pages", 0)),
        "step00_max_tables_per_page": float(e.get("max_tables_per_page", 0)),
        "step00_table_pages_drawing": float(e.get("table_pages_drawing", 0)),
        "step00_has_formulas": float(e.get("formulas", False)),
        "step00_has_figures": float(e.get("figures", False)),
        "step00_has_requirements": float(e.get("requirements", False)),
        "step00_has_tables": float(e.get("tables", False)),
        "step00_has_structure": float(h.get("has_structure", False)),
    }

    # Compute derived features
    regex = raw["step00_estimated_sections_regex"]
    font = raw["step00_estimated_sections_font"]
    toc = raw["step00_estimated_sections_toc"]
    est_sections = max(raw["step00_estimated_sections"], 1)

    raw["sections_disagreement"] = max(regex, font, toc) - min(regex, font, toc)
    raw["section_density"] = raw["step00_estimated_sections"] / pages
    raw["table_density"] = raw["step00_table_pages"] / pages
    raw["has_any_content_signal"] = float(
        raw["step00_has_formulas"]
        or raw["step00_has_tables"]
        or raw["step00_has_figures"]
        or raw["step00_has_requirements"]
    )
    raw["sections_to_pages_ratio"] = raw["step00_estimated_sections"] / pages
    raw["regex_font_ratio"] = regex / max(font, 1)
    raw["toc_coverage"] = toc / est_sections

    # RUN_DIR_FEATURES from profile.json (same source, already in hand)
    pm = profile.get("preset_match", {})
    toc_data = profile.get("toc", {})
    breakdown = h.get("section_breakdown", {})
    bd_vals = [float(breakdown.get(k, 0)) for k in ("decimal", "labeled", "roman", "alpha")]

    raw["is_scanned"] = 0.0  # will be overridden by run-dir enrichment if available
    raw["text_page_ratio"] = 0.0
    raw["total_text_chars"] = 0.0
    raw["text_chars_per_page"] = 0.0
    raw["file_size_mb"] = float(profile.get("file_size_mb", 0))
    raw["font_body_size"] = float(h.get("font_body_size", 0) or 0)
    raw["preset_confidence"] = float(pm.get("confidence", 0))
    raw["has_toc"] = float(toc_data.get("has_toc", False))
    raw["toc_entry_count"] = float(len(toc_data.get("entries", [])))
    raw["section_breakdown_total"] = sum(bd_vals)
    raw["section_breakdown_diversity"] = float(sum(1 for v in bd_vals if v > 0))

    # Remaining derived features
    raw["bytes_per_page"] = raw["file_size_mb"] * 1024 / pages
    raw["text_density_signal"] = raw["text_chars_per_page"] * raw.get("step00_has_structure", 0)
    raw["toc_section_ratio"] = raw["toc_entry_count"] / est_sections

    return raw


@app.command("emit-labels")
def emit_labels() -> None:
    """Emit training labels in /create-classifier format for the extractability task."""
    if not TRAINING_DATA_PATH.exists():
        logger.error(f"No training data at {TRAINING_DATA_PATH}. Run 'train' first.")
        raise typer.Exit(code=1)

    LABELS_PATH.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with open(TRAINING_DATA_PATH) as fin, open(LABELS_PATH, "w") as fout:
        for line in fin:
            entry = json.loads(line)
            label = "extractable" if entry["label"] == 1 else "not_extractable"
            classifier_entry = {
                "id": Path(entry["pdf"]).stem,
                "task": "extractability",
                "input": {
                    "pdf_path": entry["pdf"],
                    "text_features": entry["features"],
                },
                "label": label,
                "confidence": 10,  # ground truth from actual extraction outcome
                "source": "extraction_outcome",
                "metadata": {
                    "model": "logistic_regression_s00",
                },
            }
            fout.write(json.dumps(classifier_entry) + "\n")
            count += 1

    logger.info(f"Emitted {count} labels to {LABELS_PATH}")


# --- Public API for importing into pdf_discovery.py ---

def load_model() -> Optional[Any]:
    """Load the trained model. Returns None if not available."""
    if not MODEL_PATH.exists():
        return None
    try:
        with open(MODEL_PATH, "rb") as f:
            return pickle.load(f)
    except Exception as e:
        logger.warning(f"Could not load extractability model: {e}")
        return None


def predict_extractability(
    features: Dict[str, float],
    model: Any = None,
) -> float:
    """Predict P(extractable) from S00 features. Returns probability 0-1."""
    if model is None:
        model = load_model()
    if model is None:
        return 1.0  # No model = assume extractable (don't block)
    try:
        X = [_features_to_vector(features)]
        return float(model.predict_proba(X)[0][1])
    except Exception as e:
        logger.warning(f"Prediction failed: {e}")
        return 1.0  # Fail open


def predict_from_log_kv(kv: Dict[str, str], model: Any = None) -> float:
    """Predict from parsed extract_timeout key-value pairs."""
    features = _extract_features(kv)
    if features is None:
        return 1.0
    return predict_extractability(features, model)


if __name__ == "__main__":
    app()
