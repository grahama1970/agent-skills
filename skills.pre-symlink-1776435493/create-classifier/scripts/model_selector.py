#!/usr/bin/env python3
"""
Benchmark-first model selection for create-classifier.

Purpose:
- try classifier-lab benchmark first when available.
- fall back to internal quick benchmark across candidate backbones.
- return a deterministic selected model + benchmark report.

Inputs:
- labels JSONL, candidate backbones, and quick-benchmark parameters.

Outputs:
- selection report JSON and selected backbone name.

Failure modes:
- individual model benchmark failures are captured and excluded from selection.
"""

from __future__ import annotations
import os

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger
import torch
import typer


app = typer.Typer(no_args_is_help=True, add_completion=False)

CLASSIFIER_LAB_DIR = Path(__file__).resolve().parent.parent.parent / "classifier-lab"
DEFAULT_CANDIDATES = [
    "efficientnet_b0",
    "convnextv2_nano.fcmae_ft_in22k_in1k",
    "mobilenetv3_large_100",
    "resnet50",
]

# specific to running from create-classifier dir
sys.path.append(str(Path(__file__).parent.parent))


def _split_indices(
    labels: List[str], seed: int, val_ratio: float = 0.15
) -> Dict[str, List[int]]:
    import random
    from collections import defaultdict

    rng = random.Random(seed)
    by_label: Dict[str, List[int]] = defaultdict(list)
    for idx, label in enumerate(labels):
        by_label[label].append(idx)

    train: List[int] = []
    val: List[int] = []
    for _, indices in sorted(by_label.items()):
        rng.shuffle(indices)
        n_val = max(1, int(round(len(indices) * val_ratio))) if len(indices) > 1 else 0
        n_val = min(n_val, max(0, len(indices) - 1))
        val.extend(indices[:n_val])
        train.extend(indices[n_val:])
    if not val and len(train) > 1:
        val.append(train.pop())
    rng.shuffle(train)
    rng.shuffle(val)
    return {"train": train, "val": val}


def _evaluate_loader(
    model: torch.nn.Module, loader: torch.utils.data.DataLoader, device: str
) -> Dict[str, float]:
    from sklearn.metrics import f1_score

    model.eval()
    preds: List[int] = []
    labels: List[int] = []
    with torch.no_grad():
        for images, text_feats, batch_labels, _ in loader:
            images = images.to(device)
            text_feats = text_feats.to(device)
            batch_labels = batch_labels.to(device)
            logits, _ = model(images, text_feats)
            _, predicted = logits.max(1)
            preds.extend(predicted.cpu().numpy().tolist())
            labels.extend(batch_labels.cpu().numpy().tolist())
    if not labels:
        return {"accuracy": 0.0, "f1": 0.0}
    correct = sum(1 for p, l in zip(preds, labels) if p == l)
    accuracy = correct / len(labels)
    f1 = f1_score(labels, preds, average="macro")
    return {"accuracy": float(accuracy), "f1": float(f1)}


def _quick_benchmark(
    *,
    labels_path: Path,
    candidates: List[str],
    device: str,
    epochs: int,
    max_steps: int,
    split_seed: int,
) -> Dict[str, Any]:
    from torch.utils.data import DataLoader, Subset
    from torchvision import transforms
    import torch.nn as nn
    import torch.optim as optim
    from templates.vision_classifier import DocumentDataset, HybridClassifier

    transform = transforms.Compose(
        [
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ]
    )
    dataset = DocumentDataset(labels_path, transform=transform)
    labels = [str(sample.get("label", "")) for sample in dataset.samples]
    split = _split_indices(labels, seed=split_seed, val_ratio=0.15)
    train_loader = DataLoader(
        Subset(dataset, split["train"]), batch_size=16, shuffle=True, num_workers=2
    )
    val_loader = DataLoader(
        Subset(dataset, split["val"]), batch_size=16, shuffle=False, num_workers=2
    )

    results: List[Dict[str, Any]] = []
    for backbone in candidates:
        row: Dict[str, Any] = {"backbone": backbone, "status": "ok"}
        try:
            model = HybridClassifier(
                num_classes=len(dataset.label_to_idx),
                backbone=backbone,
                text_feature_dim=5,
            ).to(device)
            optimizer = optim.AdamW(model.parameters(), lr=1e-3, weight_decay=0.01)
            criterion = nn.CrossEntropyLoss()

            step = 0
            for _ in range(max(1, epochs)):
                model.train()
                for images, text_feats, batch_labels, _ in train_loader:
                    images = images.to(device)
                    text_feats = text_feats.to(device)
                    batch_labels = batch_labels.to(device)
                    optimizer.zero_grad()
                    logits, _ = model(images, text_feats)
                    loss = criterion(logits, batch_labels)
                    loss.backward()
                    optimizer.step()
                    step += 1
                    if step >= max_steps:
                        break
                if step >= max_steps:
                    break

            metrics = _evaluate_loader(model, val_loader, device)
            row.update(metrics)
            logger.info(
                "benchmark backbone={} accuracy={:.3f} f1={:.3f}",
                backbone,
                row["accuracy"],
                row["f1"],
            )
        except Exception as exc:
            row["status"] = "failed"
            row["error"] = str(exc)
            row["accuracy"] = 0.0
            row["f1"] = 0.0
            logger.warning("benchmark failed backbone={} err={}", backbone, exc)
        results.append(row)

    viable = [row for row in results if row.get("status") == "ok"]
    if not viable:
        return {"status": "failed", "results": results, "selected_model": None}
    selected = sorted(
        viable, key=lambda row: (float(row["f1"]), float(row["accuracy"])), reverse=True
    )[0]["backbone"]
    return {"status": "ok", "results": results, "selected_model": selected}


def _try_classifier_lab(
    *,
    labels_path: Path,
    candidates: List[str],
    data_dir: Optional[Path],
    timeout_sec: int,
    quick_epochs: int,
    quick_max_steps: int,
    split_seed: int,
    device: str,
) -> Dict[str, Any]:
    if not CLASSIFIER_LAB_DIR.exists():
        return {"status": "missing_skill"}
    benchmark_script = CLASSIFIER_LAB_DIR / "scripts" / "benchmark.py"
    if not benchmark_script.exists():
        return {
            "status": "missing_benchmark_entrypoint",
            "expected_path": str(benchmark_script),
        }

    with tempfile.NamedTemporaryFile(prefix="classifier_lab_benchmark_", suffix=".json", delete=False) as handle:
        output_path = Path(handle.name)
    labels_abs = labels_path.resolve()

    data_arg = ""
    if data_dir is not None:
        if not data_dir.exists():
            return {"status": "missing_data_dir_path", "data_dir": str(data_dir)}
        data_arg = f'--data-dir "{data_dir}"'

    command = (
        f"cd {CLASSIFIER_LAB_DIR} && ./run.sh benchmark "
        f'--labels-jsonl "{labels_abs}" '
        f"{data_arg} "
        f'--backbones "{",".join(candidates)}" '
        f"--epochs {max(1, quick_epochs)} "
        f"--max-steps {max(1, quick_max_steps)} "
        f'--device "{device}" '
        f"--seed {split_seed} "
        f'--output-json "{output_path}" '
        "> /dev/null"
    )
    proc = subprocess.run(
        ["bash", "-lc", command],
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        check=False,
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )
    if not output_path.exists():
        return {
            "status": "failed",
            "returncode": proc.returncode,
            "error": "benchmark_output_missing",
            "stdout_tail": "\n".join(proc.stdout.splitlines()[-30:]),
            "stderr_tail": "\n".join(proc.stderr.splitlines()[-30:]),
        }
    try:
        benchmark_json = json.loads(output_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "status": "failed",
            "returncode": proc.returncode,
            "error": f"invalid_benchmark_json: {exc}",
            "stdout_tail": "\n".join(proc.stdout.splitlines()[-30:]),
            "stderr_tail": "\n".join(proc.stderr.splitlines()[-30:]),
        }

    if proc.returncode != 0 or benchmark_json.get("status") != "ok":
        return {
            "status": "failed",
            "returncode": proc.returncode,
            "benchmark_report": benchmark_json,
            "stdout_tail": "\n".join(proc.stdout.splitlines()[-30:]),
            "stderr_tail": "\n".join(proc.stderr.splitlines()[-30:]),
        }

    selected = benchmark_json.get("selected_backbone")
    selected_metrics = benchmark_json.get("selected_metrics", {})
    return {
        "status": "ok",
        "selected_model": selected,
        "selected_metrics": {
            "f1": float(selected_metrics.get("macro_f1", 0.0)),
            "accuracy": float(selected_metrics.get("accuracy", 0.0)),
        },
        "benchmark_report": benchmark_json,
        "stderr_tail": "\n".join(proc.stderr.splitlines()[-30:]),
    }


def select_model(
    *,
    labels_path: Path,
    base_model: str,
    candidate_backbones: Optional[List[str]] = None,
    benchmark_first: bool = True,
    classifier_lab_first: bool = True,
    classifier_lab_data_dir: Optional[Path] = None,
    classifier_lab_timeout_sec: int = 300,
    require_classifier_lab: bool = True,
    require_selection_pass: bool = True,
    device: str = "cuda",
    quick_epochs: int = 1,
    quick_max_steps: int = 250,
    split_seed: int = 42,
) -> Dict[str, Any]:
    candidates = list(dict.fromkeys(([base_model] + (candidate_backbones or DEFAULT_CANDIDATES))))
    report: Dict[str, Any] = {
        "benchmark_first": benchmark_first,
        "classifier_lab_first": classifier_lab_first,
        "base_model": base_model,
        "candidate_backbones": candidates,
        "require_classifier_lab": require_classifier_lab,
        "require_selection_pass": require_selection_pass,
        "selected_model": base_model,
        "status": "ok",
        "path": "base_model",
    }
    if not benchmark_first:
        return report

    if classifier_lab_first:
        lab_report = _try_classifier_lab(
            labels_path=labels_path,
            candidates=candidates,
            data_dir=classifier_lab_data_dir,
            timeout_sec=classifier_lab_timeout_sec,
            quick_epochs=quick_epochs,
            quick_max_steps=quick_max_steps,
            split_seed=split_seed,
            device=device,
        )
        report["classifier_lab"] = lab_report
        if lab_report.get("status") == "ok":
            selected = lab_report.get("selected_model")
            if isinstance(selected, str) and selected:
                report["selected_model"] = selected
                report["path"] = "classifier_lab"
        elif require_classifier_lab:
            report["status"] = "failed"
            report["selected_model"] = None
            report["path"] = "classifier_lab_required_failed"
            return report

    internal = _quick_benchmark(
        labels_path=labels_path,
        candidates=candidates,
        device=device,
        epochs=quick_epochs,
        max_steps=quick_max_steps,
        split_seed=split_seed,
    )
    report["internal_benchmark"] = internal
    if report.get("path") == "classifier_lab":
        return report

    if internal.get("status") == "ok" and internal.get("selected_model"):
        report["selected_model"] = str(internal["selected_model"])
        report["path"] = "internal_benchmark"
        return report

    if require_selection_pass:
        report["status"] = "failed"
        report["selected_model"] = None
        report["path"] = "selection_failed"
    return report


def main(
    labels: Path = typer.Option(..., exists=True, file_okay=True, dir_okay=False),
    model: str = typer.Option(..., help="Base model"),
    candidate_backbones: str = typer.Option(
        "", help="Comma-separated candidate backbones"
    ),
    benchmark_first: bool = typer.Option(True),
    classifier_lab_first: bool = typer.Option(True),
    classifier_lab_data_dir: Optional[Path] = typer.Option(
        None, help="Optional data dir for classifier-lab benchmark"
    ),
    classifier_lab_timeout_sec: int = typer.Option(300, min=30),
    require_classifier_lab: bool = typer.Option(
        True, help="Require classifier-lab benchmark success"
    ),
    require_selection_pass: bool = typer.Option(
        True, help="Fail when no viable model can be selected"
    ),
    device: str = typer.Option(
        "cuda" if torch.cuda.is_available() else "cpu", help="Device"
    ),
    quick_epochs: int = typer.Option(1, min=1),
    quick_max_steps: int = typer.Option(250, min=20),
    split_seed: int = typer.Option(42),
    output: Optional[Path] = typer.Option(None, help="Optional output JSON"),
) -> None:
    """Run benchmark-first selection and print report."""
    candidates = [
        item.strip() for item in candidate_backbones.split(",") if item.strip()
    ]
    report = select_model(
        labels_path=labels,
        base_model=model,
        candidate_backbones=candidates if candidates else None,
        benchmark_first=benchmark_first,
        classifier_lab_first=classifier_lab_first,
        classifier_lab_data_dir=classifier_lab_data_dir,
        classifier_lab_timeout_sec=classifier_lab_timeout_sec,
        require_classifier_lab=require_classifier_lab,
        require_selection_pass=require_selection_pass,
        device=device,
        quick_epochs=quick_epochs,
        quick_max_steps=quick_max_steps,
        split_seed=split_seed,
    )
    print(json.dumps(report, indent=2))
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if report.get("status") != "ok":
        raise typer.Exit(code=1)


if __name__ == "__main__":
    typer.run(main)
