#!/usr/bin/env python3
"""
Classifier task assessment and recommendation preflight.

Purpose:
- perform an initial assessment of label quality, modality coverage, and class
  imbalance before training.
- recommend classifier type/backbone and hyperparameter search strategy.
- optionally trigger /dogpile research when confidence is low.

Inputs:
- labels JSONL and task name.

Outputs:
- JSON report with recommendation, confidence, and optional dogpile notes.

Failure modes:
- malformed labels produce a deterministic non-zero exit with actionable errors.
"""

from __future__ import annotations
import os

import json
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger
import typer


DOGPILE_DIR = Path(__file__).resolve().parent.parent.parent / "dogpile"


def _load_labels(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _class_counts(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = Counter(str(row.get("label", "")).strip() for row in rows)
    return {key: int(value) for key, value in sorted(counts.items()) if key}


def _coverage(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    total = max(1, len(rows))
    image_hits = 0
    text_hits = 0
    layout_hits = 0
    for row in rows:
        payload = row.get("input", {}) if isinstance(row.get("input"), dict) else {}
        image_paths = payload.get("image_paths", [])
        if isinstance(image_paths, list) and image_paths:
            image_hits += 1

        text_value = payload.get("text")
        text_preview = payload.get("hf_text_preview")
        if (isinstance(text_value, str) and text_value.strip()) or (
            isinstance(text_preview, str) and text_preview.strip()
        ):
            text_hits += 1

        text_features = payload.get("text_features", {})
        if isinstance(text_features, dict) and text_features:
            layout_hits += 1

    return {
        "image_coverage": image_hits / total,
        "text_coverage": text_hits / total,
        "layout_feature_coverage": layout_hits / total,
    }


def _recommend_family(coverage: Dict[str, float]) -> str:
    image_cov = coverage["image_coverage"]
    text_cov = coverage["text_coverage"]
    layout_cov = coverage["layout_feature_coverage"]
    if image_cov >= 0.8 and text_cov < 0.4:
        return "vision"
    if text_cov >= 0.8 and image_cov < 0.3:
        return "text"
    if image_cov >= 0.5 and (text_cov >= 0.4 or layout_cov >= 0.4):
        return "hybrid"
    return "hybrid"


def _recommend_backbone(dataset_size: int, family: str) -> str:
    if family == "text":
        return "bert-base-uncased"
    if family == "vision":
        if dataset_size < 5000:
            return "efficientnet_b0"
        if dataset_size < 25000:
            return "convnextv2_nano.fcmae_ft_in22k_in1k"
        return "microsoft/dit-base"
    if dataset_size < 7000:
        return "efficientnet_b0"
    if dataset_size < 30000:
        return "convnextv2_nano.fcmae_ft_in22k_in1k"
    return "microsoft/dit-base"


def _imbalance_ratio(class_counts: Dict[str, int]) -> float:
    if not class_counts:
        return 0.0
    min_count = min(class_counts.values())
    max_count = max(class_counts.values())
    return float(min_count) / float(max(1, max_count))


def _confidence_score(
    *,
    dataset_size: int,
    class_counts: Dict[str, int],
    coverage: Dict[str, float],
) -> float:
    score = 1.0
    imbalance = _imbalance_ratio(class_counts)
    if dataset_size < 1000:
        score -= 0.25
    elif dataset_size < 3000:
        score -= 0.15
    if imbalance < 0.2:
        score -= 0.25
    elif imbalance < 0.4:
        score -= 0.15
    if coverage["image_coverage"] < 0.4 and coverage["text_coverage"] < 0.4:
        score -= 0.25
    if coverage["layout_feature_coverage"] < 0.2:
        score -= 0.10
    return max(0.0, min(1.0, score))


def _dogpile_query(task: str, family: str, backbone: str) -> str:
    return (
        f"best {family} classifier backbone for {task} document extraction "
        f"with class imbalance and layout features, compare against {backbone}"
    )


def _run_dogpile(query: str, timeout_sec: int = 180) -> Dict[str, Any]:
    if not DOGPILE_DIR.exists():
        return {"status": "missing_skill", "query": query}

    cmd = (
        f"cd {DOGPILE_DIR} && ./run.sh search "
        f"\"{query}\" --no-interactive --no-tailor --no-github-skill"
    )
    proc = subprocess.run(
        ["bash", "-lc", cmd],
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        check=False,
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )
    return {
        "status": "ok" if proc.returncode == 0 else "failed",
        "returncode": proc.returncode,
        "query": query,
        "stdout_tail": "\n".join(proc.stdout.splitlines()[-30:]),
        "stderr_tail": "\n".join(proc.stderr.splitlines()[-30:]),
    }


def assess_task(
    *,
    labels_path: Path,
    task_name: str,
    dogpile_when_uncertain: bool,
    dogpile_threshold: float,
) -> Dict[str, Any]:
    rows = _load_labels(labels_path)
    class_counts = _class_counts(rows)
    coverage = _coverage(rows)
    family = _recommend_family(coverage)
    backbone = _recommend_backbone(len(rows), family)
    imbalance = _imbalance_ratio(class_counts)
    confidence = _confidence_score(
        dataset_size=len(rows), class_counts=class_counts, coverage=coverage
    )
    uncertain = confidence < dogpile_threshold

    report: Dict[str, Any] = {
        "timestamp": int(time.time()),
        "task_name": task_name,
        "labels_path": str(labels_path),
        "dataset_size": len(rows),
        "class_counts": class_counts,
        "imbalance_ratio": imbalance,
        "coverage": coverage,
        "recommendation": {
            "family": family,
            "backbone": backbone,
            "run_hyperparameter_search": True,
            "hp_trials": 15 if len(rows) < 15000 else 25,
            "start_with_classifier_lab_benchmark": True,
        },
        "confidence_score": confidence,
        "uncertain": uncertain,
    }

    if dogpile_when_uncertain and uncertain:
        query = _dogpile_query(task_name, family, backbone)
        report["dogpile"] = _run_dogpile(query)
    return report


def main(
    labels: Path = typer.Option(..., exists=True, file_okay=True, dir_okay=False),
    task: str = typer.Option(..., help="Classifier task name"),
    output: Optional[Path] = typer.Option(
        None, help="Optional JSON output path for assessment report"
    ),
    dogpile_when_uncertain: bool = typer.Option(
        True, help="Run dogpile research if confidence is low"
    ),
    dogpile_threshold: float = typer.Option(
        0.70, min=0.0, max=1.0, help="Confidence threshold to trigger dogpile"
    ),
) -> None:
    """Run preflight assessment and print JSON report."""
    report = assess_task(
        labels_path=labels,
        task_name=task,
        dogpile_when_uncertain=dogpile_when_uncertain,
        dogpile_threshold=dogpile_threshold,
    )
    logger.info(
        "assess task={} confidence={:.3f} family={} backbone={}",
        task,
        report["confidence_score"],
        report["recommendation"]["family"],
        report["recommendation"]["backbone"],
    )
    print(json.dumps(report, indent=2))
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    typer.run(main)
