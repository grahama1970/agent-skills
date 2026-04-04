#!/usr/bin/env python3
"""
Hugging Face data augmentation for classifier training.

Purpose:
- augment local labels only when local data is sparse or class-imbalanced.
- enforce provenance + license constraints for every imported example.
- output an auditable augmentation report and an augmented JSONL dataset.

Inputs:
- local labels JSONL, task name, and augmentation policy/config.

Outputs:
- augmented labels JSONL (or original passthrough) and JSON report metadata.

Failure modes:
- if Hugging Face dependencies/network are unavailable, returns a non-fatal
  report and leaves labels unchanged.
"""

from __future__ import annotations

import json
import random
import re
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml
from loguru import logger
import typer


DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "configs" / "hf_augmentation.yaml"
)


@dataclass
class AugmentDecision:
    """Decision about whether augmentation should run."""

    should_augment: bool
    reason: str
    min_class_count: int
    max_class_count: int
    imbalance_ratio: float


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def _class_distribution(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = Counter(str(row.get("label", "")) for row in rows)
    return {label: int(count) for label, count in sorted(counts.items()) if label}


def decide_augmentation(
    *,
    class_counts: Dict[str, int],
    min_samples_per_class: int,
    imbalance_ratio_threshold: float,
) -> AugmentDecision:
    """Decide if augmentation is needed from class support and imbalance."""
    if not class_counts:
        return AugmentDecision(
            should_augment=True,
            reason="no_local_labels",
            min_class_count=0,
            max_class_count=0,
            imbalance_ratio=0.0,
        )

    min_count = min(class_counts.values())
    max_count = max(class_counts.values())
    ratio = float(min_count) / float(max(1, max_count))

    sparse = min_count < min_samples_per_class
    imbalanced = ratio < imbalance_ratio_threshold

    if sparse and imbalanced:
        reason = "sparse_and_imbalanced"
    elif sparse:
        reason = "sparse"
    elif imbalanced:
        reason = "imbalanced"
    else:
        reason = "healthy"

    return AugmentDecision(
        should_augment=(sparse or imbalanced),
        reason=reason,
        min_class_count=min_count,
        max_class_count=max_count,
        imbalance_ratio=ratio,
    )


def _load_hf_modules() -> Tuple[Any, Any, Optional[str]]:
    try:
        from datasets import load_dataset  # type: ignore
        from huggingface_hub import HfApi  # type: ignore

        return load_dataset, HfApi, None
    except Exception as exc:  # pragma: no cover
        return None, None, str(exc)


def _normalize_license(value: Any) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, list):
        return ",".join(str(item).strip().lower() for item in value)
    return str(value).strip().lower()


def _allowed_license(license_value: str, allowed: List[str]) -> bool:
    if not allowed:
        return True
    chunks = [chunk.strip() for chunk in license_value.split(",") if chunk.strip()]
    if not chunks:
        return False
    allowed_set = {item.strip().lower() for item in allowed}
    return all(chunk in allowed_set for chunk in chunks)


def _load_policy(config_path: Path, task_name: str) -> Dict[str, Any]:
    if not config_path.exists():
        return {"defaults": {}, "task": {}, "datasets": []}
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    defaults = payload.get("defaults", {}) or {}
    tasks = payload.get("tasks", {}) or {}
    task = tasks.get(task_name, {}) or tasks.get("default", {}) or {}
    datasets = task.get("datasets", []) or []
    return {"defaults": defaults, "task": task, "datasets": datasets}


def _raw_label_to_text(raw_label: Any, label_names: Optional[List[str]]) -> str:
    if raw_label is None:
        return ""
    if isinstance(raw_label, int) and label_names and 0 <= raw_label < len(label_names):
        return str(label_names[raw_label]).strip().lower()
    return str(raw_label).strip().lower()


def _map_label(raw_label: str, label_map: Dict[str, str]) -> Optional[str]:
    if not raw_label:
        return None
    if raw_label in label_map:
        return label_map[raw_label]
    for key, value in label_map.items():
        if re.search(key, raw_label):
            return value
    return None


def _materialize_image(example: Dict[str, Any], image_field: str, out_dir: Path, sample_id: str) -> List[str]:
    if not image_field:
        return []
    image_value = example.get(image_field)
    if image_value is None:
        return []

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{sample_id}.png"

    try:
        if hasattr(image_value, "save"):
            image_value.save(out_path)
            return [str(out_path)]
        if isinstance(image_value, dict) and image_value.get("bytes"):
            out_path.write_bytes(image_value["bytes"])
            return [str(out_path)]
    except Exception:
        return []
    return []


def augment_labels_if_needed(
    *,
    labels_path: Path,
    task_name: str,
    output_dir: Path,
    config_path: Path = DEFAULT_CONFIG_PATH,
    min_samples_per_class: int = 300,
    imbalance_ratio_threshold: float = 0.35,
    max_new_samples: int = 3000,
    allowed_licenses: Optional[List[str]] = None,
    seed: int = 42,
) -> Dict[str, Any]:
    """Conditionally augment labels from Hugging Face datasets."""
    rng = random.Random(seed)
    rows = _load_jsonl(labels_path)
    local_counts = _class_distribution(rows)
    target_labels = set(local_counts.keys())
    decision = decide_augmentation(
        class_counts=local_counts,
        min_samples_per_class=min_samples_per_class,
        imbalance_ratio_threshold=imbalance_ratio_threshold,
    )

    policy = _load_policy(config_path, task_name)
    defaults = policy["defaults"]
    task_cfg = policy["task"]
    datasets_cfg = policy["datasets"]

    min_samples_per_class = int(task_cfg.get("min_samples_per_class", defaults.get("min_samples_per_class", min_samples_per_class)))
    imbalance_ratio_threshold = float(task_cfg.get("imbalance_ratio_threshold", defaults.get("imbalance_ratio_threshold", imbalance_ratio_threshold)))
    max_new_samples = int(task_cfg.get("max_new_samples", defaults.get("max_new_samples", max_new_samples)))
    allowed = allowed_licenses or task_cfg.get("allowed_licenses", defaults.get("allowed_licenses", [])) or []

    report: Dict[str, Any] = {
        "status": "skipped",
        "task_name": task_name,
        "labels_path": str(labels_path),
        "local_class_counts": local_counts,
        "decision": {
            "should_augment": decision.should_augment,
            "reason": decision.reason,
            "min_class_count": decision.min_class_count,
            "max_class_count": decision.max_class_count,
            "imbalance_ratio": decision.imbalance_ratio,
        },
        "policy": {
            "config_path": str(config_path),
            "min_samples_per_class": min_samples_per_class,
            "imbalance_ratio_threshold": imbalance_ratio_threshold,
            "max_new_samples": max_new_samples,
            "allowed_licenses": allowed,
        },
        "datasets_considered": [],
        "datasets_used": [],
        "imported_samples": 0,
    }

    refreshed_decision = decide_augmentation(
        class_counts=local_counts,
        min_samples_per_class=min_samples_per_class,
        imbalance_ratio_threshold=imbalance_ratio_threshold,
    )
    report["decision"] = {
        "should_augment": refreshed_decision.should_augment,
        "reason": refreshed_decision.reason,
        "min_class_count": refreshed_decision.min_class_count,
        "max_class_count": refreshed_decision.max_class_count,
        "imbalance_ratio": refreshed_decision.imbalance_ratio,
    }

    if not refreshed_decision.should_augment:
        report["status"] = "not_needed"
        report["output_labels_path"] = str(labels_path)
        return report

    if not datasets_cfg:
        report["status"] = "no_dataset_policy"
        report["output_labels_path"] = str(labels_path)
        return report

    load_dataset, hf_api_cls, import_err = _load_hf_modules()
    if import_err:
        report["status"] = "dependency_missing"
        report["error"] = import_err
        report["output_labels_path"] = str(labels_path)
        return report

    hf_api = hf_api_cls()
    imported_rows: List[Dict[str, Any]] = []
    image_out_dir = output_dir / "hf_images"
    augmentation_started_at = int(time.time())

    for ds_cfg in datasets_cfg:
        if len(imported_rows) >= max_new_samples:
            break
        dataset_id = str(ds_cfg.get("id", "")).strip()
        if not dataset_id:
            continue

        split = str(ds_cfg.get("split", "train"))
        config_name = ds_cfg.get("config")
        label_field = str(ds_cfg.get("label_field", "label"))
        image_field = str(ds_cfg.get("image_field", "")).strip()
        text_field = str(ds_cfg.get("text_field", "text"))
        require_image = bool(ds_cfg.get("require_image", True))
        per_dataset_limit = int(ds_cfg.get("max_samples", max_new_samples))
        label_map_raw = ds_cfg.get("label_map", {}) or {}
        label_map = {str(key).strip().lower(): str(value).strip() for key, value in label_map_raw.items()}

        considered: Dict[str, Any] = {
            "id": dataset_id,
            "split": split,
            "config": config_name,
            "status": "unknown",
        }
        report["datasets_considered"].append(considered)

        try:
            info = hf_api.dataset_info(dataset_id)
            card_data = getattr(info, "cardData", None) or {}
            ds_license = _normalize_license(card_data.get("license"))
            considered["license"] = ds_license
            considered["provenance"] = f"huggingface:{dataset_id}"
        except Exception as exc:
            considered["status"] = "metadata_error"
            considered["error"] = str(exc)
            continue

        if not _allowed_license(considered.get("license", "unknown"), allowed):
            considered["status"] = "license_rejected"
            continue

        try:
            dataset = load_dataset(dataset_id, name=config_name, split=split, streaming=True)
        except Exception as exc:
            considered["status"] = "load_failed"
            considered["error"] = str(exc)
            continue

        label_names: Optional[List[str]] = None
        try:
            features = getattr(dataset, "features", None)
            if features is not None:
                label_feature = features.get(label_field)
                label_names = list(getattr(label_feature, "names", []) or [])
        except Exception:
            label_names = None

        used = 0
        seen = 0
        for sample_index, example in enumerate(dataset):
            if len(imported_rows) >= max_new_samples or used >= per_dataset_limit:
                break
            seen += 1
            raw_label = _raw_label_to_text(example.get(label_field), label_names)
            mapped_label = _map_label(raw_label, label_map)
            if not mapped_label or mapped_label not in target_labels:
                continue

            sample_id = f"hf_{dataset_id.replace('/', '_')}_{sample_index}"
            image_paths = _materialize_image(example, image_field, image_out_dir, sample_id)
            if require_image and not image_paths:
                continue

            text_value = example.get(text_field, "")
            text_preview = str(text_value)[:500] if text_value is not None else ""
            item = {
                "id": sample_id,
                "task": task_name,
                "input": {
                    "pdf_path": "",
                    "image_paths": image_paths,
                    "text_features": {
                        "hf_source": dataset_id,
                        "hf_split": split,
                        "has_hf_text": bool(text_preview),
                    },
                    "hf_text_preview": text_preview,
                },
                "label": mapped_label,
                "confidence": float(ds_cfg.get("sample_confidence", 0.8)),
                "source": "huggingface",
                "provenance": {
                    "provider": "huggingface",
                    "dataset": dataset_id,
                    "config": config_name,
                    "split": split,
                    "license": considered.get("license", "unknown"),
                    "sample_index": sample_index,
                    "retrieved_at": augmentation_started_at,
                },
            }
            imported_rows.append(item)
            used += 1

        if used > 0:
            considered["status"] = "used"
            considered["samples_used"] = used
            considered["samples_seen"] = seen
            report["datasets_used"].append(dataset_id)
        else:
            considered["status"] = considered.get("status", "no_mappable_samples")
            considered["samples_seen"] = seen

    if not imported_rows:
        report["status"] = "no_imported_samples"
        report["output_labels_path"] = str(labels_path)
        return report

    rng.shuffle(imported_rows)
    merged = list(rows) + imported_rows
    output_dir.mkdir(parents=True, exist_ok=True)
    output_labels_path = output_dir / f"{labels_path.stem}.augmented.jsonl"
    _write_jsonl(output_labels_path, merged)

    report["status"] = "augmented"
    report["imported_samples"] = len(imported_rows)
    report["output_labels_path"] = str(output_labels_path)
    report["augmented_class_counts"] = _class_distribution(merged)
    return report


def main(
    labels: Path = typer.Option(..., exists=True, file_okay=True, dir_okay=False),
    task: str = typer.Option(..., help="Task name"),
    output_dir: Path = typer.Option(..., help="Output directory"),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, help="Augmentation policy config"),
    min_samples_per_class: int = typer.Option(300, min=1),
    imbalance_ratio_threshold: float = typer.Option(0.35, min=0.0, max=1.0),
    max_new_samples: int = typer.Option(3000, min=0),
    allowed_licenses: str = typer.Option(
        "", help="Comma-separated license allowlist override"
    ),
    report_path: Optional[Path] = typer.Option(
        None, help="Optional JSON report output path"
    ),
) -> None:
    """Run conditional HF augmentation and print JSON report."""
    allowed = [item.strip().lower() for item in allowed_licenses.split(",") if item.strip()]
    result = augment_labels_if_needed(
        labels_path=labels,
        task_name=task,
        output_dir=output_dir,
        config_path=config,
        min_samples_per_class=min_samples_per_class,
        imbalance_ratio_threshold=imbalance_ratio_threshold,
        max_new_samples=max_new_samples,
        allowed_licenses=allowed,
    )

    logger.info(
        "HF augmentation status={} imported_samples={}",
        result.get("status"),
        result.get("imported_samples", 0),
    )
    print(json.dumps(result, indent=2))

    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    typer.run(main)
