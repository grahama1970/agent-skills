#!/usr/bin/env python3
"""Train Tier 0.5 sklearn classifiers from harvested teacher labels.

Reads JSONL training data produced by harvest.py, trains TF-IDF + LogReg
classifiers, and deploys them to ~/.pi/models/classifiers/ for use by
the /assistant validate() cascade.

Usage:
    python train_classifiers.py --all
    python train_classifiers.py --task qra-assessor
    python train_classifiers.py --task sparta-ambiguity --evaluate-only
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

from loguru import logger

TRAINING_DATA_DIR = Path.home() / ".pi" / "assistant" / "training_data"
CLASSIFIERS_DIR = Path.home() / ".pi" / "models" / "classifiers"
REGISTRY_PATH = Path(__file__).resolve().parent / "model_registry.json"


# ── Label normalization for tasks with verbose LLM outputs ──────────────────

# sparta-intent: Teacher LLM returns verbose natural-language descriptions
# instead of discrete categories. Normalize to canonical intent types.
_INTENT_KEYWORDS: list[tuple[str, list[str]]] = [
    ("identify_vulnerability", ["identify vulnerabilit", "identify risk", "identify challenge"]),
    ("identify_mitigation", ["identify.*mitigat", "identify.*measure", "identify mechanism", "identify.*security measure"]),
    ("understand_control", ["understand.*control", "understanding.*control", "role of.*control"]),
    ("understand_relationship", ["understand.*relationship", "understanding.*relationship"]),
    ("understand_impact", ["understand.*impact", "understanding.*impact", "understanding.*importance", "understanding.*danger"]),
    ("understand_defense", ["understand.*defense", "understanding.*defense", "understanding.*resilience"]),
    ("mitigation_strategy", ["mitigation strateg", "mitigat"]),
    ("implementation", ["implementation"]),
    ("technical_query", ["technical"]),
    ("apply_controls", ["application of"]),
]

import re

def _normalize_intent_label(raw: str) -> str:
    """Map verbose LLM intent description to canonical category."""
    lower = raw.lower().strip()
    if not lower:
        return "UNKNOWN"
    for canonical, patterns in _INTENT_KEYWORDS:
        for pat in patterns:
            if re.search(pat, lower):
                return canonical
    # Fallback: if it starts with a verb, use that verb
    first_word = lower.split()[0] if lower.split() else ""
    if first_word in ("identify", "understand", "understanding"):
        return first_word.rstrip("ing") + "_general"
    return "general_query"


def _get_intent_label(e: Dict) -> str:
    """Extract and normalize intent label from training entry."""
    raw = e["output"].get("action", e["output"].get("prediction", e.get("teacher_grade", "")))
    return _normalize_intent_label(str(raw))


def _get_pipeline_label(e: Dict) -> str:
    """Extract pipeline validator label, preferring teacher_grade."""
    out = e.get("output", {})
    label = out.get("action", out.get("grade", e.get("teacher_grade", "")))
    return str(label) if label else "UNKNOWN"


# Task → how to extract (text, label) from a training JSONL entry
TASK_EXTRACTORS: Dict[str, Dict[str, Any]] = {
    "qra-assessor": {
        "text_fn": lambda e: f"{e['input'].get('question', '')} {e['input'].get('answer', '')}",
        "label_fn": lambda e: e["output"].get("grade", e.get("teacher_grade", "UNKNOWN")),
        "classifier_name": "qra_grade_classifier.joblib",
        "registry_key": "qra-assessor",
    },
    "bridge-tagger": {
        "text_fn": lambda e: e["input"].get("text", e["input"].get("chunk", str(e["input"]))),
        "label_fn": lambda e: e["output"].get("tags", []) if isinstance(e["output"].get("tags"), list)
            else [str(e["output"].get("tag", e["output"].get("bridge", e.get("teacher_grade", ""))))],
        "classifier_name": "bridge_text_classifier.joblib",
        "registry_key": "bridge-tagger",
        "multi_label": True,
    },
    "edge-relevance-scorer": {
        "text_fn": lambda e: f"{e['input'].get('source', '')} {e['input'].get('target', '')} {e['input'].get('edge_text', '')}",
        "label_fn": lambda e: e["output"].get("relevant", e.get("teacher_grade", "UNKNOWN")),
        "classifier_name": "edge_relevance_classifier.joblib",
        "registry_key": "edge-relevance",
    },
    "sparta-pipeline-validator": {
        "text_fn": lambda e: f"{e['input'].get('question', '')} {e['input'].get('answer', '')}",
        "label_fn": _get_pipeline_label,
        "classifier_name": "sparta_pipeline_classifier.joblib",
        "registry_key": "sparta-pipeline-validator",
    },
    "sparta-ambiguity": {
        "text_fn": lambda e: e["input"].get("query", e["input"].get("text", str(e["input"]))),
        "label_fn": lambda e: e["output"].get("stance", e.get("teacher_grade", "UNKNOWN")),
        "classifier_name": "sparta_ambiguity_classifier.joblib",
        "registry_key": "sparta-ambiguity",
    },
    "sparta-intent": {
        "text_fn": lambda e: e["input"].get("query", e["input"].get("text", str(e["input"]))),
        "label_fn": _get_intent_label,
        "classifier_name": "sparta_intent_classifier.joblib",
        "registry_key": "sparta-intent",
    },
    "canvas-intent": {
        "text_fn": lambda e: e["input"].get("text", str(e["input"])),
        "label_fn": lambda e: e["output"].get("prediction", e.get("teacher_grade", "UNKNOWN")),
        "classifier_name": "canvas_intent_classifier.joblib",
        "registry_key": "canvas-intent",
    },
    "5ft-intent": {
        "text_fn": lambda e: e["input"].get("text", str(e["input"])),
        "label_fn": lambda e: e.get("teacher_grade", e["output"].get("prediction", "UNKNOWN")),
        "classifier_name": "5ft_intent_classifier.joblib",
        "registry_key": "5ft-intent",
    },
    "5ft-scope": {
        "text_fn": lambda e: e["input"].get("text", str(e["input"])),
        "label_fn": lambda e: e.get("teacher_grade", e["output"].get("prediction", "UNKNOWN")),
        "classifier_name": "5ft_scope_classifier.joblib",
        "registry_key": "5ft-scope",
    },
    "5ft-type": {
        "text_fn": lambda e: e["input"].get("text", str(e["input"])),
        "label_fn": lambda e: e.get("teacher_grade", e["output"].get("prediction", "UNKNOWN")),
        "classifier_name": "5ft_type_classifier.joblib",
        "registry_key": "5ft-type",
    },
    "lean4_provable": {
        "text_fn": lambda e: e["input"].get("text", str(e["input"])),
        "label_fn": lambda e: e.get("teacher_grade", e["output"].get("prediction", "UNKNOWN")),
        "classifier_name": "lean4_provable_classifier.joblib",
        "registry_key": "lean4_provable",
    },
    "viz-type-selector": {
        "text_fn": lambda e: e["input"].get("text", str(e["input"])),
        "label_fn": lambda e: e.get("teacher_grade", e["output"].get("prediction", "UNKNOWN")),
        "classifier_name": "viz_type_selector_classifier.joblib",
        "registry_key": "viz-type-selector",
    },
    "skill-chain-router": {
        "text_fn": lambda e: e["input"].get("text", str(e["input"])),
        "label_fn": lambda e: e.get("teacher_grade", e["output"].get("prediction", "UNKNOWN")),
        "classifier_name": "skill_chain_router_classifier.joblib",
        "registry_key": "skill-chain-router",
    },
    "url-content-quality": {
        "text_fn": lambda e: e["input"].get("text", str(e["input"])),
        "label_fn": lambda e: e.get("teacher_grade", e["output"].get("prediction", "UNKNOWN")),
        "classifier_name": "url_content_quality_classifier.joblib",
        "registry_key": "url-content-quality",
    },
}


def load_labels(task: str, exclude_mined: bool = False) -> List[Dict]:
    """Load all JSONL label files for a task.

    Args:
        task: Task name (directory under training_data/).
        exclude_mined: If True, skip labels_mined*.jsonl files. Useful when
            mined data degrades accuracy (e.g., 5ft-scope curated-only is
            85.2% vs 67% with mined data mixed in).
    """
    task_dir = TRAINING_DATA_DIR / task
    if not task_dir.exists():
        return []
    entries = []
    for f in sorted(task_dir.glob("labels_*.jsonl")):
        if exclude_mined and "mined" in f.name:
            logger.info(f"  Skipping mined data: {f.name}")
            continue
        for line in f.read_text().splitlines():
            if line.strip():
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def prepare_dataset(task: str, entries: List[Dict]) -> Tuple[List[str], Any]:
    """Extract (texts, labels) from entries using task-specific extractors.

    For multi_label tasks, labels is List[List[str]].
    For single-label tasks, labels is List[str].
    """
    extractor = TASK_EXTRACTORS[task]
    is_multi = extractor.get("multi_label", False)
    texts, labels = [], []
    for e in entries:
        try:
            text = extractor["text_fn"](e)
            label = extractor["label_fn"](e)
            if is_multi:
                # label_fn returns a list for multi-label tasks
                if not isinstance(label, list):
                    label = [str(label)] if label else []
                # Filter empty/unknown
                label = [l for l in label if l and l != "UNKNOWN"]
                if text and label:
                    texts.append(text)
                    labels.append(label)
            else:
                if text and label and label != "UNKNOWN":
                    texts.append(text)
                    labels.append(str(label))
        except (KeyError, TypeError):
            continue
    return texts, labels


def train_classifier(task: str, texts: List[str], labels: Any) -> Dict[str, Any]:
    """Train TF-IDF + LogReg classifier and save to disk.

    For multi_label tasks (e.g. bridge-tagger), uses OneVsRestClassifier
    with MultiLabelBinarizer so a single doc can have multiple tags.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_score
    from sklearn.pipeline import Pipeline

    import joblib

    extractor = TASK_EXTRACTORS[task]
    is_multi = extractor.get("multi_label", False)

    if is_multi:
        return _train_multilabel_classifier(task, texts, labels)

    unique_labels = sorted(set(labels))
    if len(unique_labels) < 2:
        return {"success": False, "error": f"Need >=2 classes, got {unique_labels}"}

    logger.info(f"Training {task}: {len(texts)} samples, {len(unique_labels)} classes: {unique_labels}")

    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(
            max_features=10000,
            ngram_range=(1, 2),
            sublinear_tf=True,
            strip_accents="unicode",
        )),
        ("clf", LogisticRegression(
            max_iter=1000,
            class_weight="balanced",
            C=1.0,
        )),
    ])

    # Cross-validate (skip if too many classes relative to samples)
    cv_accuracy = 0.0
    if len(texts) >= 10 and len(unique_labels) <= len(texts) // 3:
        n_splits = min(5, len(unique_labels), len(texts) // 3)
        if n_splits >= 2:
            try:
                scores = cross_val_score(pipeline, texts, labels, cv=n_splits, scoring="accuracy")
                cv_accuracy = scores.mean()
                logger.info(f"  CV accuracy: {cv_accuracy:.1%} (±{scores.std():.1%})")
            except ValueError as e:
                logger.warning(f"  CV failed ({e}), training without CV")
    elif len(unique_labels) > len(texts) // 3:
        logger.info(f"  Skipping CV: {len(unique_labels)} classes with {len(texts)} samples (need more data)")

    # Filter out very short texts that TF-IDF can't handle
    filtered = [(t, l) for t, l in zip(texts, labels) if len(t.split()) >= 3]
    if len(filtered) < 10:
        return {"success": False, "error": f"Only {len(filtered)} samples with 3+ words"}
    texts, labels = zip(*filtered)
    texts, labels = list(texts), list(labels)

    # Train on full dataset
    try:
        pipeline.fit(texts, labels)
    except ValueError as e:
        return {"success": False, "error": str(e)[:200]}

    # Save
    CLASSIFIERS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = CLASSIFIERS_DIR / TASK_EXTRACTORS[task]["classifier_name"]
    joblib.dump(pipeline, model_path)
    logger.info(f"  Saved: {model_path}")

    return {
        "success": True,
        "model_path": str(model_path),
        "samples": len(texts),
        "classes": unique_labels,
        "cv_accuracy": round(cv_accuracy, 4),
    }


def _train_multilabel_classifier(
    task: str, texts: List[str], labels: List[List[str]]
) -> Dict[str, Any]:
    """Train multi-label TF-IDF + OneVsRestClassifier(LogReg).

    Uses MultiLabelBinarizer to encode tag lists, then OneVsRestClassifier
    wrapping LogisticRegression for per-tag binary classification.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import f1_score
    from sklearn.model_selection import KFold
    from sklearn.multiclass import OneVsRestClassifier
    from sklearn.preprocessing import MultiLabelBinarizer

    import joblib
    import numpy as np

    # Collect all unique tags across all label lists
    all_tags = sorted({tag for tag_list in labels for tag in tag_list})
    if len(all_tags) < 2:
        return {"success": False, "error": f"Need >=2 classes, got {all_tags}"}

    logger.info(f"Training {task} (multi-label): {len(texts)} samples, {len(all_tags)} tags: {all_tags}")

    # Filter short texts
    filtered = [(t, l) for t, l in zip(texts, labels) if len(t.split()) >= 3]
    if len(filtered) < 10:
        return {"success": False, "error": f"Only {len(filtered)} samples with 3+ words"}
    texts, labels = zip(*filtered)
    texts, labels = list(texts), list(labels)

    # Binarize labels
    mlb = MultiLabelBinarizer(classes=all_tags)
    y = mlb.fit_transform(labels)

    # TF-IDF vectorize
    tfidf = TfidfVectorizer(
        max_features=10000,
        ngram_range=(1, 2),
        sublinear_tf=True,
        strip_accents="unicode",
    )
    X = tfidf.fit_transform(texts)

    # Cross-validate with macro F1
    cv_f1 = 0.0
    if len(texts) >= 20:
        n_splits = min(5, len(texts) // 5)
        if n_splits >= 2:
            kf = KFold(n_splits=n_splits, shuffle=True, random_state=42)
            f1_scores = []
            try:
                for train_idx, val_idx in kf.split(X):
                    clf = OneVsRestClassifier(LogisticRegression(
                        max_iter=1000, class_weight="balanced", C=5.0,
                    ))
                    clf.fit(X[train_idx], y[train_idx])
                    y_pred = clf.predict(X[val_idx])
                    f1 = f1_score(y[val_idx], y_pred, average="macro", zero_division=0)
                    f1_scores.append(f1)
                cv_f1 = float(np.mean(f1_scores))
                logger.info(f"  CV macro-F1: {cv_f1:.1%} (±{np.std(f1_scores):.1%})")
            except ValueError as e:
                logger.warning(f"  CV failed ({e}), training without CV")

    # Train final model on full data
    clf = OneVsRestClassifier(LogisticRegression(
        max_iter=1000, class_weight="balanced", C=5.0,
    ))
    try:
        clf.fit(X, y)
    except ValueError as e:
        return {"success": False, "error": str(e)[:200]}

    # Bundle: tfidf + clf + mlb so predict() is self-contained
    model_bundle = {
        "tfidf": tfidf,
        "clf": clf,
        "mlb": mlb,
        "multi_label": True,
    }

    CLASSIFIERS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = CLASSIFIERS_DIR / TASK_EXTRACTORS[task]["classifier_name"]
    joblib.dump(model_bundle, model_path)
    logger.info(f"  Saved multi-label bundle: {model_path}")

    return {
        "success": True,
        "model_path": str(model_path),
        "samples": len(texts),
        "classes": all_tags,
        "cv_accuracy": round(cv_f1, 4),
        "multi_label": True,
    }


def update_registry(task: str, result: Dict[str, Any]) -> None:
    """Update model_registry.json with the new classifier."""
    if not result["success"]:
        return

    registry = json.loads(REGISTRY_PATH.read_text()) if REGISTRY_PATH.exists() else {}
    classifiers = registry.setdefault("classifiers", {})

    registry_key = TASK_EXTRACTORS[task]["registry_key"]
    entry = {
        "model_path": result["model_path"],
        "type": "sklearn",
        "confidence_threshold": 0.60,
        "input_signature": {"type": "text", "task_hint": task},
        "cv_accuracy": result["cv_accuracy"],
        "training_samples": result["samples"],
        "classes": result["classes"],
        "shadow_mode": True,  # Start in shadow mode
        "note": f"Auto-trained from {result['samples']} teacher labels. CV={result['cv_accuracy']:.1%}",
    }
    if result.get("multi_label"):
        entry["multi_label"] = True
        entry["note"] = (
            f"Multi-label OneVsRest from {result['samples']} teacher labels. "
            f"Macro-F1={result['cv_accuracy']:.1%}"
        )
    classifiers[registry_key] = entry

    REGISTRY_PATH.write_text(json.dumps(registry, indent=2) + "\n")
    logger.info(f"  Registry updated: classifiers.{registry_key}")


import typer

app = typer.Typer()


@app.command()
def main(
    task: str = typer.Option(None, help="Specific task to train"),
    all_tasks: bool = typer.Option(False, "--all", help="Train all tasks with data"),
    evaluate_only: bool = typer.Option(False, "--evaluate-only", help=""),
    min_samples: int = typer.Option(20, help="Min samples to train"),
    exclude_mined: bool = typer.Option(False, "--exclude-mined",
                                       help="Skip labels_mined*.jsonl (use curated-only data)"),
):
    tasks = [task] if task else list(TASK_EXTRACTORS.keys()) if all_tasks else []
    if not tasks:
        logger.error("Specify --task or --all")
        raise typer.Exit(code=1)

    results = {}
    for t in tasks:
        if t not in TASK_EXTRACTORS:
            logger.warning(f"No extractor for task={t}, skipping")
            continue

        entries = load_labels(t, exclude_mined=exclude_mined)
        if not entries:
            logger.warning(f"No training data for task={t}")
            results[t] = {"success": False, "error": "no data"}
            continue

        texts, labels = prepare_dataset(t, entries)
        if len(texts) < min_samples:
            logger.warning(f"Only {len(texts)} usable samples for {t} (need {min_samples})")
            results[t] = {"success": False, "error": f"only {len(texts)} samples"}
            continue

        result = train_classifier(t, texts, labels)
        results[t] = result

        if result["success"] and not evaluate_only:
            update_registry(t, result)

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    app()
