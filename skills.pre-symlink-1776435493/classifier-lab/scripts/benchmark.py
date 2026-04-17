#!/usr/bin/env python3
"""
Classifier-lab backbone benchmark entrypoint.

Purpose:
- benchmark candidate vision backbones on a local dataset.
- select the best backbone by validation macro-F1, then accuracy.
- emit a deterministic JSON report for downstream automation.

Inputs:
- either a directory dataset (`--data-dir`) or JSONL labels (`--labels-jsonl`).
- comma-separated backbone list and quick-train controls.

Outputs:
- benchmark JSON report to stdout and optional `--output-json` file.

Failure modes:
- returns non-zero if no viable backbone succeeds.
"""

from __future__ import annotations
import os

import json
import random
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from loguru import logger
from PIL import Image
import timm
import torch
from torch import nn, optim
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms
import typer


app = typer.Typer(no_args_is_help=True, add_completion=False)
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
SKILL_DIR = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = SKILL_DIR / ".artifacts"
_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent
TAXONOMY_SKILL_DIR = _SKILLS_DIR / "taxonomy"
MEMORY_SKILL_DIR = _SKILLS_DIR / "memory"
DEFAULT_MEMORY_EVENTS = ARTIFACTS_DIR / "classifier_lab_memory_events.jsonl"


@dataclass(frozen=True)
class Sample:
    image_path: Path
    label: str


class _ImageDataset(Dataset):  # type: ignore[type-arg]
    """Simple image dataset with label-to-index mapping."""

    def __init__(
        self,
        samples: Sequence[Sample],
        label_to_idx: Dict[str, int],
        image_size: int,
        *,
        augment: bool = False,
        random_erasing: float = 0.0,
    ) -> None:
        self.samples = list(samples)
        self.label_to_idx = label_to_idx
        transform_steps: List[Any] = [transforms.Resize((image_size, image_size))]
        if augment:
            transform_steps.extend(
                [
                    transforms.RandomHorizontalFlip(),
                    transforms.RandomRotation(3),
                ]
            )
        transform_steps.extend(
            [
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225],
                ),
            ]
        )
        if augment and random_erasing > 0:
            transform_steps.append(transforms.RandomErasing(p=min(max(random_erasing, 0.0), 1.0)))
        self.transform = transforms.Compose(transform_steps)

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int) -> Tuple[torch.Tensor, int]:
        sample = self.samples[index]
        image = Image.open(sample.image_path).convert("RGB")
        return self.transform(image), self.label_to_idx[sample.label]


def _append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except Exception as e:
        logger.debug("JSON parse failed: {}", e)
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    snippet = stripped[start : end + 1]
    try:
        return json.loads(snippet)
    except Exception:
        return None


def _taxonomy_extract(summary_text: str, taxonomy_collection: str) -> Dict[str, Any]:
    if not TAXONOMY_SKILL_DIR.exists():
        return {"status": "failed", "error": "taxonomy_skill_missing"}
    command = (
        f"cd {TAXONOMY_SKILL_DIR} && "
        f"./run.sh extract --text {json.dumps(summary_text)} "
        f"--collection {taxonomy_collection} --fast"
    )
    proc = subprocess.run(
        ["bash", "-lc", command],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )
    parsed = _extract_json_object(proc.stdout)
    if proc.returncode != 0 or parsed is None:
        return {
            "status": "failed",
            "returncode": proc.returncode,
            "stdout_tail": "\n".join(proc.stdout.splitlines()[-20:]),
            "stderr_tail": "\n".join(proc.stderr.splitlines()[-20:]),
        }
    return {"status": "ok", "result": parsed}


def _memory_store_event(
    *,
    report: Dict[str, Any],
    taxonomy: Dict[str, Any],
    memory_scope: str,
    memory_events_path: Path,
    taxonomy_collection: str,
) -> Dict[str, Any]:
    timestamp = int(time.time())
    selected_metrics = report.get("selected_metrics") or {}
    selected_backbone = report.get("selected_backbone")
    event: Dict[str, Any] = {
        "event_type": "classifier_lab_benchmark",
        "timestamp": timestamp,
        "status": report.get("status"),
        "selected_backbone": selected_backbone,
        "selected_metrics": selected_metrics,
        "candidate_count": len(report.get("results", [])),
        "source": report.get("source", {}),
        "taxonomy": taxonomy,
    }
    _append_jsonl(memory_events_path, event)

    if not MEMORY_SKILL_DIR.exists():
        return {
            "status": "failed",
            "error": "memory_skill_missing",
            "memory_events_path": str(memory_events_path),
        }

    event_file = memory_events_path.parent / f"classifier_lab_event_{timestamp}.json"
    event_file.write_text(json.dumps(event, indent=2), encoding="utf-8")
    bridge_tags = []
    if taxonomy.get("status") == "ok":
        maybe_tags = taxonomy.get("result", {}).get("bridge_tags", [])
        if isinstance(maybe_tags, list):
            bridge_tags = [str(item).strip() for item in maybe_tags if str(item).strip()]

    problem = (
        "classifier-lab benchmark "
        f"status={report.get('status')} selected_backbone={selected_backbone}"
    )
    solution_payload = {
        "selected_metrics": selected_metrics,
        "candidate_count": len(report.get("results", [])),
        "source": report.get("source", {}),
        "taxonomy": taxonomy,
        "event_file": str(event_file),
    }
    solution = json.dumps(solution_payload, ensure_ascii=True)

    cmd = [
        "./run.sh",
        "learn",
        "--problem",
        problem,
        "--solution",
        solution,
        "--scope",
        memory_scope,
        "--tag",
        "classifier-lab",
        "--tag",
        "benchmark",
        "--tag",
        f"collection:{taxonomy_collection}",
    ]
    for tag in bridge_tags[:6]:
        normalized = tag.lower().replace(" ", "_")
        cmd.extend(["--tag", f"bridge:{normalized}"])

    proc = subprocess.run(
        cmd,
        cwd=MEMORY_SKILL_DIR,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )
    return {
        "status": "ok" if proc.returncode == 0 else "failed",
        "returncode": proc.returncode,
        "memory_scope": memory_scope,
        "memory_events_path": str(memory_events_path),
        "event_file": str(event_file),
        "stdout_tail": "\n".join(proc.stdout.splitlines()[-20:]),
        "stderr_tail": "\n".join(proc.stderr.splitlines()[-20:]),
    }


def _resolve_image_path(raw_path: str, base_dir: Path) -> Optional[Path]:
    candidate = Path(raw_path)
    if candidate.is_file():
        return candidate.resolve()
    joined = (base_dir / raw_path).resolve()
    if joined.is_file():
        return joined
    return None


def _samples_from_jsonl(labels_jsonl: Path) -> List[Sample]:
    rows = [line.strip() for line in labels_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    samples: List[Sample] = []
    base_dir = labels_jsonl.parent
    for line in rows:
        row = json.loads(line)
        label = str(row.get("label", "")).strip()
        if not label:
            continue

        raw_paths: List[str] = []
        if isinstance(row.get("image_path"), str):
            raw_paths.append(str(row["image_path"]))
        if isinstance(row.get("image_paths"), list):
            raw_paths.extend(str(item) for item in row["image_paths"] if isinstance(item, str))
        input_block = row.get("input", {})
        if isinstance(input_block, dict):
            input_paths = input_block.get("image_paths")
            if isinstance(input_paths, list):
                raw_paths.extend(str(item) for item in input_paths if isinstance(item, str))

        if not raw_paths:
            continue
        resolved = _resolve_image_path(raw_paths[0], base_dir)
        if resolved is None:
            continue
        samples.append(Sample(image_path=resolved, label=label))
    return samples


def _samples_from_data_dir(data_dir: Path) -> Tuple[List[Sample], List[Sample]]:
    train_dir = data_dir / "train"
    val_dir = data_dir / "val"
    if train_dir.is_dir() and val_dir.is_dir():
        return _samples_from_class_dirs(train_dir), _samples_from_class_dirs(val_dir)
    all_samples = _samples_from_class_dirs(data_dir)
    train, val = _stratified_split(all_samples, val_ratio=0.15, seed=42)
    return train, val


def _samples_from_class_dirs(root: Path) -> List[Sample]:
    samples: List[Sample] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTS:
            continue
        label = path.parent.name.strip()
        if not label:
            continue
        samples.append(Sample(image_path=path.resolve(), label=label))
    return samples


def _stratified_split(samples: Sequence[Sample], val_ratio: float, seed: int) -> Tuple[List[Sample], List[Sample]]:
    rng = random.Random(seed)
    by_label: Dict[str, List[Sample]] = {}
    for sample in samples:
        by_label.setdefault(sample.label, []).append(sample)
    train: List[Sample] = []
    val: List[Sample] = []
    for label, items in sorted(by_label.items()):
        bucket = list(items)
        rng.shuffle(bucket)
        if len(bucket) <= 1:
            train.extend(bucket)
            continue
        n_val = max(1, int(round(len(bucket) * val_ratio)))
        n_val = min(n_val, len(bucket) - 1)
        val.extend(bucket[:n_val])
        train.extend(bucket[n_val:])
        logger.debug("split label={} train={} val={}", label, len(bucket) - n_val, n_val)
    rng.shuffle(train)
    rng.shuffle(val)
    if not val and len(train) > 1:
        val.append(train.pop())
    return train, val


def _macro_f1(preds: Sequence[int], labels: Sequence[int], num_classes: int) -> float:
    if not labels:
        return 0.0
    f1_values: List[float] = []
    for class_idx in range(num_classes):
        tp = sum(1 for pred, label in zip(preds, labels) if pred == class_idx and label == class_idx)
        fp = sum(1 for pred, label in zip(preds, labels) if pred == class_idx and label != class_idx)
        fn = sum(1 for pred, label in zip(preds, labels) if pred != class_idx and label == class_idx)
        denom = (2 * tp) + fp + fn
        f1_values.append(0.0 if denom == 0 else (2 * tp) / denom)
    return float(sum(f1_values) / max(1, len(f1_values)))


def _wilson_score_lower(accuracy: float, n: int, z: float = 2.576) -> float:
    """Wilson score confidence interval lower bound.

    Default z=2.576 gives 99% CI (safety-critical promotion decisions).
    Use z=1.96 for 95% CI.
    """
    if n == 0:
        return 0.0
    p = accuracy
    denom = 1 + z ** 2 / n
    center = (p + z ** 2 / (2 * n)) / denom
    spread = z * (p * (1 - p) / n + z ** 2 / (4 * n ** 2)) ** 0.5 / denom
    return float(center - spread)


def _evaluate(
    *,
    model: nn.Module,
    loader: DataLoader[Tuple[torch.Tensor, int]],
    device: str,
    num_classes: int,
) -> Dict[str, Any]:
    model.eval()
    preds: List[int] = []
    labels: List[int] = []
    with torch.no_grad():
        for images, targets in loader:
            images = images.to(device)
            targets = targets.to(device)
            logits = model(images)
            predicted = torch.argmax(logits, dim=1)
            preds.extend(predicted.cpu().tolist())
            labels.extend(targets.cpu().tolist())
    if not labels:
        empty_cm = [[0 for _ in range(num_classes)] for _ in range(num_classes)]
        empty_per_class = {
            str(class_idx): {"precision": 0.0, "recall": 0.0, "f1": 0.0, "support": 0}
            for class_idx in range(num_classes)
        }
        return {
            "accuracy": 0.0,
            "macro_f1": 0.0,
            "confusion_matrix": empty_cm,
            "per_class": empty_per_class,
        }
    correct = sum(1 for pred, label in zip(preds, labels) if pred == label)
    confusion_matrix = [[0 for _ in range(num_classes)] for _ in range(num_classes)]
    for pred, label in zip(preds, labels):
        if 0 <= label < num_classes and 0 <= pred < num_classes:
            confusion_matrix[label][pred] += 1

    per_class: Dict[str, Dict[str, float | int]] = {}
    for class_idx in range(num_classes):
        tp = confusion_matrix[class_idx][class_idx]
        row_total = sum(confusion_matrix[class_idx])
        col_total = sum(confusion_matrix[row][class_idx] for row in range(num_classes))
        fp = col_total - tp
        fn = row_total - tp
        precision = float(tp / (tp + fp)) if (tp + fp) > 0 else 0.0
        recall = float(tp / (tp + fn)) if (tp + fn) > 0 else 0.0
        denom = (2 * tp) + fp + fn
        f1 = float((2 * tp) / denom) if denom > 0 else 0.0
        per_class[str(class_idx)] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": int(row_total),
        }

    return {
        "accuracy": float(correct / len(labels)),
        "macro_f1": _macro_f1(preds, labels, num_classes),
        "confusion_matrix": confusion_matrix,
        "per_class": per_class,
    }


def _mixup_batch(
    images: torch.Tensor,
    labels: torch.Tensor,
    alpha: float,
) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, float]:
    if alpha <= 0:
        return images, labels, labels, 1.0
    lam = float(torch.distributions.Beta(alpha, alpha).sample().item())
    index = torch.randperm(images.size(0), device=images.device)
    mixed = (lam * images) + ((1.0 - lam) * images[index, :])
    return mixed, labels, labels[index], lam


def _cutmix_batch(
    images: torch.Tensor,
    labels: torch.Tensor,
    alpha: float,
) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, float]:
    if alpha <= 0:
        return images, labels, labels, 1.0
    lam = float(torch.distributions.Beta(alpha, alpha).sample().item())
    batch_size, _channels, height, width = images.size()
    index = torch.randperm(batch_size, device=images.device)

    cut_ratio = (1.0 - lam) ** 0.5
    cut_w = int(width * cut_ratio)
    cut_h = int(height * cut_ratio)

    cx = int(torch.randint(0, width, (1,), device=images.device).item())
    cy = int(torch.randint(0, height, (1,), device=images.device).item())

    x1 = max(cx - cut_w // 2, 0)
    y1 = max(cy - cut_h // 2, 0)
    x2 = min(cx + cut_w // 2, width)
    y2 = min(cy + cut_h // 2, height)

    patched = images.clone()
    patched[:, :, y1:y2, x1:x2] = images[index, :, y1:y2, x1:x2]
    area = max((x2 - x1) * (y2 - y1), 1)
    lam_adjusted = 1.0 - (area / float(width * height))
    return patched, labels, labels[index], lam_adjusted


def _benchmark_backbone(
    *,
    backbone: str,
    train_samples: Sequence[Sample],
    val_samples: Sequence[Sample],
    label_to_idx: Dict[str, int],
    device: str,
    image_size: int,
    batch_size: int,
    epochs: int,
    lr: float,
    weight_decay: float,
    label_smoothing: float,
    dropout: float,
    mixup_alpha: float,
    cutmix_alpha: float,
    random_erasing: float,
    max_steps: int,
    num_workers: int,
    seed: int,
) -> Dict[str, Any]:
    torch.manual_seed(seed)
    num_classes = len(label_to_idx)
    idx_to_label = {idx: label for label, idx in label_to_idx.items()}
    classes = [str(idx_to_label.get(i, i)) for i in range(num_classes)]
    train_dataset = _ImageDataset(
        train_samples,
        label_to_idx=label_to_idx,
        image_size=image_size,
        augment=(mixup_alpha > 0 or cutmix_alpha > 0 or random_erasing > 0),
        random_erasing=random_erasing,
    )
    val_dataset = _ImageDataset(val_samples, label_to_idx=label_to_idx, image_size=image_size)
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=num_workers)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False, num_workers=num_workers)

    try:
        model = timm.create_model(backbone, pretrained=True, num_classes=num_classes, drop_rate=dropout).to(device)
    except TypeError:
        model = timm.create_model(backbone, pretrained=True, num_classes=num_classes).to(device)
    criterion = nn.CrossEntropyLoss(label_smoothing=label_smoothing)
    optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)

    step = 0
    model.train()
    for _epoch in range(max(1, epochs)):
        for images, targets in train_loader:
            images = images.to(device)
            targets = targets.to(device)
            optimizer.zero_grad()
            train_images = images
            y_a = targets
            y_b = targets
            lam = 1.0
            if mixup_alpha > 0:
                train_images, y_a, y_b, lam = _mixup_batch(images, targets, mixup_alpha)
            elif cutmix_alpha > 0:
                train_images, y_a, y_b, lam = _cutmix_batch(images, targets, cutmix_alpha)

            logits = model(train_images)
            if lam < 1.0:
                loss = (lam * criterion(logits, y_a)) + ((1.0 - lam) * criterion(logits, y_b))
            else:
                loss = criterion(logits, targets)
            loss.backward()
            optimizer.step()
            step += 1
            if step >= max_steps:
                break
        if step >= max_steps:
            break

    metrics = _evaluate(model=model, loader=val_loader, device=device, num_classes=num_classes)
    n_total = len(train_samples) + len(val_samples)
    return {
        "backbone": backbone,
        "status": "ok",
        "accuracy": metrics["accuracy"],
        "macro_f1": metrics["macro_f1"],
        "classes": classes,
        "confusion_matrix": metrics.get("confusion_matrix", []),
        "per_class": {
            classes[int(class_idx)] if str(class_idx).isdigit() and int(class_idx) < len(classes) else str(class_idx): class_metrics
            for class_idx, class_metrics in metrics.get("per_class", {}).items()
        },
        "wilson_score_lower": _wilson_score_lower(metrics["accuracy"], n_total),
        "train_samples": len(train_samples),
        "val_samples": len(val_samples),
        "num_classes": num_classes,
        "steps": step,
    }


def run_benchmark(
    *,
    data_dir: Optional[Path],
    labels_jsonl: Optional[Path],
    backbones: Sequence[str],
    device: str,
    image_size: int,
    batch_size: int,
    epochs: int,
    lr: float,
    weight_decay: float,
    label_smoothing: float,
    dropout: float,
    mixup_alpha: float,
    cutmix_alpha: float,
    random_erasing: float,
    max_steps: int,
    num_workers: int,
    val_ratio: float,
    seed: int,
) -> Dict[str, Any]:
    if labels_jsonl is not None:
        all_samples = _samples_from_jsonl(labels_jsonl)
        train_samples, val_samples = _stratified_split(all_samples, val_ratio=val_ratio, seed=seed)
        source = {"mode": "jsonl", "labels_jsonl": str(labels_jsonl)}
    elif data_dir is not None:
        train_samples, val_samples = _samples_from_data_dir(data_dir)
        source = {"mode": "data_dir", "data_dir": str(data_dir)}
    else:
        raise ValueError("Either data_dir or labels_jsonl is required")

    labels = sorted({sample.label for sample in train_samples + val_samples})
    label_to_idx = {label: idx for idx, label in enumerate(labels)}
    results: List[Dict[str, Any]] = []

    for backbone in backbones:
        try:
            result = _benchmark_backbone(
                backbone=backbone,
                train_samples=train_samples,
                val_samples=val_samples,
                label_to_idx=label_to_idx,
                device=device,
                image_size=image_size,
                batch_size=batch_size,
                epochs=epochs,
                lr=lr,
                weight_decay=weight_decay,
                label_smoothing=label_smoothing,
                dropout=dropout,
                mixup_alpha=mixup_alpha,
                cutmix_alpha=cutmix_alpha,
                random_erasing=random_erasing,
                max_steps=max_steps,
                num_workers=num_workers,
                seed=seed,
            )
            logger.info(
                "benchmark backbone={} macro_f1={:.4f} accuracy={:.4f}",
                backbone,
                result["macro_f1"],
                result["accuracy"],
            )
        except Exception as exc:
            result = {
                "backbone": backbone,
                "status": "failed",
                "error": str(exc),
                "accuracy": 0.0,
                "macro_f1": 0.0,
            }
            logger.warning("benchmark failed backbone={} error={}", backbone, exc)
        results.append(result)

    viable = [item for item in results if item.get("status") == "ok"]
    if not viable:
        return {
            "status": "failed",
            "reason": "no_viable_backbone",
            "selected_backbone": None,
            "source": source,
            "results": results,
        }

    winner = sorted(
        viable,
        key=lambda row: (float(row.get("macro_f1", 0.0)), float(row.get("accuracy", 0.0))),
        reverse=True,
    )[0]
    return {
        "status": "ok",
        "selected_backbone": winner["backbone"],
        "selected_metrics": {
            "macro_f1": float(winner.get("macro_f1", 0.0)),
            "accuracy": float(winner.get("accuracy", 0.0)),
            "wilson_score_lower": float(winner.get("wilson_score_lower", 0.0)),
            "classes": winner.get("classes", []),
            "confusion_matrix": winner.get("confusion_matrix", []),
            "per_class": winner.get("per_class", {}),
        },
        "source": source,
        "results": results,
    }


@app.command("benchmark")
def cmd_benchmark(
    data_dir: Optional[Path] = typer.Option(
        None, exists=True, file_okay=False, dir_okay=True, help="Dataset directory"
    ),
    labels_jsonl: Optional[Path] = typer.Option(
        None, exists=True, file_okay=True, dir_okay=False, help="JSONL labels file"
    ),
    backbones: str = typer.Option(..., help="Comma-separated backbones"),
    output_json: Optional[Path] = typer.Option(None, help="Optional report JSON path"),
    output_dir: Optional[Path] = typer.Option(
        None, help="Save winning tabular model to this directory (tabular modality only)"
    ),
    device: str = typer.Option(
        "cuda" if torch.cuda.is_available() else "cpu", help="Training device"
    ),
    modality: str = typer.Option(
        "vision", help="Modality: vision, text, or tabular"
    ),
    image_size: int = typer.Option(224, min=64, max=2048),
    batch_size: int = typer.Option(16, min=1),
    epochs: int = typer.Option(1, min=1),
    lr: float = typer.Option(1e-3, min=1e-8, help="Learning rate"),
    weight_decay: float = typer.Option(0.01, min=0.0, help="AdamW weight decay"),
    dropout: float = typer.Option(0.1, min=0.0, max=0.9, help="Dropout/drop-rate"),
    label_smoothing: float = typer.Option(0.0, min=0.0, max=0.5, help="Cross-entropy label smoothing"),
    mixup_alpha: float = typer.Option(0.0, min=0.0, help="Mixup alpha (paired modality)"),
    cutmix_alpha: float = typer.Option(0.0, min=0.0, help="CutMix alpha (paired modality)"),
    random_erasing: float = typer.Option(0.0, min=0.0, max=1.0, help="Random erasing probability"),
    max_steps: int = typer.Option(250, min=1),
    max_length: int = typer.Option(256, min=16, help="Max token length for text modality"),
    num_workers: int = typer.Option(2, min=0),
    val_ratio: float = typer.Option(0.15, min=0.05, max=0.5),
    seed: int = typer.Option(42),
    train_jsonl: Optional[Path] = typer.Option(
        None, exists=True, file_okay=True, dir_okay=False,
        help="Separate train JSONL (text/tabular). If provided with --val-jsonl, skips split.",
    ),
    val_jsonl: Optional[Path] = typer.Option(
        None, exists=True, file_okay=True, dir_okay=False,
        help="Separate val JSONL (text/tabular). Requires --train-jsonl.",
    ),
    taxonomy_collection: str = typer.Option(
        "operational", help="Federated taxonomy collection for benchmark tagging"
    ),
    store_memory: bool = typer.Option(
        True, help="Store benchmark event in memory with taxonomy metadata"
    ),
    require_memory_store: bool = typer.Option(
        True, help="Fail closed when memory storage is unsuccessful"
    ),
    memory_scope: str = typer.Option(
        "datalake_classifier", help="Memory scope for classifier benchmark artifacts"
    ),
    memory_events: Path = typer.Option(
        DEFAULT_MEMORY_EVENTS, help="JSONL sink for local memory benchmark events"
    ),
) -> None:
    """Benchmark one or more backbones and emit JSON contract."""
    modality = modality.lower().strip()
    if modality not in ("vision", "text", "tabular", "paired"):
        raise typer.BadParameter(f"Invalid modality: {modality}. Must be vision, text, tabular, or paired.")

    if modality in ("vision", "paired") and data_dir is None and labels_jsonl is None:
        raise typer.BadParameter("Provide at least one of --data-dir or --labels-jsonl")
    if modality in ("text", "tabular") and labels_jsonl is None and train_jsonl is None:
        raise typer.BadParameter(
            f"--labels-jsonl (or --train-jsonl + --val-jsonl) is required for {modality} modality"
        )

    candidates = [item.strip() for item in backbones.split(",") if item.strip()]
    if not candidates:
        raise typer.BadParameter("At least one backbone is required")

    if modality == "text":
        # Auto-detect multi-label format and route to appropriate engine
        source_jsonl = labels_jsonl or train_jsonl
        from multilabel_benchmark import detect_multilabel
        is_multilabel = source_jsonl is not None and detect_multilabel(source_jsonl)

        if is_multilabel:
            from multilabel_benchmark import run_multilabel_benchmark
            logger.info("Detected multi-label format — using BCEWithLogitsLoss engine")
            report = run_multilabel_benchmark(
                labels_jsonl=source_jsonl,  # type: ignore[arg-type]
                backbones=candidates,
                device=device,
                batch_size=batch_size,
                epochs=max(epochs, 10),
                max_steps=max(max_steps, 10000),
                max_length=max_length,
                val_ratio=val_ratio,
                seed=seed,
                train_jsonl=train_jsonl,
                val_jsonl=val_jsonl,
            )
        else:
            from text_benchmark import run_text_benchmark
            report = run_text_benchmark(
                labels_jsonl=source_jsonl,  # type: ignore[arg-type]
                backbones=candidates,
                device=device,
                batch_size=batch_size,
                epochs=epochs,
                max_steps=max_steps,
                max_length=max_length,
                val_ratio=val_ratio,
                seed=seed,
                lr=lr,
                weight_decay=weight_decay,
                label_smoothing=label_smoothing,
                dropout=dropout,
                train_jsonl=train_jsonl,
                val_jsonl=val_jsonl,
                output_dir=output_dir,
            )
    elif modality == "paired":
        from paired_benchmark import run_paired_benchmark

        report = run_paired_benchmark(
            data_dir=data_dir,  # type: ignore[arg-type]
            backbones=candidates,
            device=device,
            image_size=image_size,
            batch_size=batch_size,
            epochs=max(epochs, 20),
            lr=lr,
            weight_decay=weight_decay,
            label_smoothing=label_smoothing,
            dropout=dropout,
            mixup_alpha=mixup_alpha,
            cutmix_alpha=cutmix_alpha,
            random_erasing=random_erasing,
            num_workers=num_workers,
            seed=seed,
        )
    elif modality == "tabular":
        from text_benchmark import run_tabular_benchmark

        report = run_tabular_benchmark(
            labels_jsonl=labels_jsonl or train_jsonl,  # type: ignore[arg-type]
            backbones=candidates,
            val_ratio=val_ratio,
            seed=seed,
            train_jsonl=train_jsonl,
            val_jsonl=val_jsonl,
            output_dir=output_dir,
        )
    else:
        report = run_benchmark(
            data_dir=data_dir,
            labels_jsonl=labels_jsonl,
            backbones=candidates,
            device=device,
            image_size=image_size,
            batch_size=batch_size,
            epochs=epochs,
            lr=lr,
            weight_decay=weight_decay,
            label_smoothing=label_smoothing,
            dropout=dropout,
            mixup_alpha=mixup_alpha,
            cutmix_alpha=cutmix_alpha,
            random_erasing=random_erasing,
            max_steps=max_steps,
            num_workers=num_workers,
            val_ratio=val_ratio,
            seed=seed,
        )

    summary_text = (
        f"classifier benchmark status={report.get('status')}; "
        f"selected_backbone={report.get('selected_backbone')}; "
        f"selected_metrics={report.get('selected_metrics')}; "
        f"source={report.get('source')}"
    )
    taxonomy = _taxonomy_extract(summary_text=summary_text, taxonomy_collection=taxonomy_collection)
    report["taxonomy"] = taxonomy

    if store_memory:
        memory_result = _memory_store_event(
            report=report,
            taxonomy=taxonomy,
            memory_scope=memory_scope,
            memory_events_path=memory_events,
            taxonomy_collection=taxonomy_collection,
        )
        report["memory_store"] = memory_result
        if require_memory_store and memory_result.get("status") != "ok":
            report["status"] = "failed"
            report["reason"] = "memory_store_failed"
    else:
        report["memory_store"] = {"status": "skipped"}

    text = json.dumps(report, indent=2)
    print(text)
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(text, encoding="utf-8")
    if report.get("status") != "ok":
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
