#!/usr/bin/env python3
"""
Evaluation Script - Compare classifier vs heuristics/baseline

Provides comprehensive metrics, confusion matrix, per-class scores.
"""

import typer
import json
from pathlib import Path
from typing import Any, Dict, List

import torch
from loguru import logger
from rich.console import Console
from rich.table import Table
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support
)

console = Console()


def evaluate_classifier(
    model_path: Path,
    labels_path: Path,
    device: str = "cuda"
) -> Dict[str, Any]:
    """Evaluate trained classifier on validation set.
    
    Returns:
        Dict with metrics: accuracy, f1, per_class_metrics, confusion_matrix
    """
    from templates.vision_classifier import VisionClassifier, DocumentDataset
    from torch.utils.data import DataLoader
    from torchvision import transforms
    import time
    
    # Load model
    checkpoint = torch.load(model_path / "best_model.pt", map_location=device)
    num_classes = len(checkpoint["label_to_idx"])
    
    model = VisionClassifier(
        num_classes=num_classes,
        backbone=checkpoint["config"]["model"]["architecture"]
    ).to(device)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    
    # Load dataset
    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])
    
    dataset = DocumentDataset(labels_path, transform=transform)
    dataloader = DataLoader(dataset, batch_size=16, shuffle=False, num_workers=4)
    
    # Predict
    all_preds = []
    all_labels = []
    all_confidences = []
    inference_times = []
    
    with torch.no_grad():
        for images, labels, _ in dataloader:
            images, labels = images.to(device), labels.to(device)
            
            t0 = time.time()
            logits, confidence = model(images)
            inference_time = (time.time() - t0) * 1000 / images.size(0)  # ms per sample
            
            _, predicted = logits.max(1)
            
            all_preds.extend(predicted.cpu().numpy())
            all_labels.extend(labels.cpu().numpy())
            all_confidences.extend(confidence.cpu().numpy())
            inference_times.append(inference_time)
    
    # Calculate metrics
    accuracy = accuracy_score(all_labels, all_preds)
    f1 = f1_score(all_labels, all_preds, average='macro')
    precision, recall, _, _ = precision_recall_fscore_support(
        all_labels, all_preds, average='macro'
    )
    
    # Per-class metrics
    per_class_precision, per_class_recall, per_class_f1, support = precision_recall_fscore_support(
        all_labels, all_preds, average=None
    )
    
    idx_to_label = checkpoint["idx_to_label"]
    per_class_metrics = {}
    for idx, label in idx_to_label.items():
        idx = int(idx)
        per_class_metrics[label] = {
            "precision": float(per_class_precision[idx]),
            "recall": float(per_class_recall[idx]),
            "f1": float(per_class_f1[idx]),
            "support": int(support[idx])
        }
    
    # Confusion matrix
    cm = confusion_matrix(all_labels, all_preds)
    
    # Inference stats
    avg_inference_time = sum(inference_times) / len(inference_times)
    p50_inference = sorted(inference_times)[len(inference_times) // 2]
    p95_inference = sorted(inference_times)[int(len(inference_times) * 0.95)]
    
    return {
        "accuracy": float(accuracy),
        "f1": float(f1),
        "precision": float(precision),
        "recall": float(recall),
        "per_class_metrics": per_class_metrics,
        "confusion_matrix": cm.tolist(),
        "inference_time_ms": {
            "mean": float(avg_inference_time),
            "p50": float(p50_inference),
            "p95": float(p95_inference)
        },
        "avg_confidence": float(sum(all_confidences) / len(all_confidences))
    }


def print_results(metrics: Dict[str, Any], class_names: List[str]):
    """Print evaluation results in rich format."""
    
    console.print("\n[bold]Overall Metrics[/bold]\n")
    table = Table()
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Accuracy", f"{metrics['accuracy']:.1%}")
    table.add_row("Macro F1", f"{metrics['f1']:.1%}")
    table.add_row("Precision", f"{metrics['precision']:.1%}")
    table.add_row("Recall", f"{metrics['recall']:.1%}")
    table.add_row("Avg Confidence", f"{metrics['avg_confidence']:.2f}")
    table.add_row("-" * 20, "-" * 10)
    table.add_row("Inference (mean)", f"{metrics['inference_time_ms']['mean']:.1f}ms")
    table.add_row("Inference (p50)", f"{metrics['inference_time_ms']['p50']:.1f}ms")
    table.add_row("Inference (p95)", f"{metrics['inference_time_ms']['p95']:.1f}ms")
    
    console.print(table)
    
    # Per-class metrics
    console.print("\n[bold]Per-Class Metrics[/bold]\n")
    class_table = Table()
    class_table.add_column("Class", style="cyan")
    class_table.add_column("Precision", style="green")
    class_table.add_column("Recall", style="green")
    class_table.add_column("F1", style="green")
    class_table.add_column("Support", style="yellow")
    
    for class_name, class_metrics in metrics["per_class_metrics"].items():
        class_table.add_row(
            class_name,
            f"{class_metrics['precision']:.1%}",
            f"{class_metrics['recall']:.1%}",
            f"{class_metrics['f1']:.1%}",
            str(class_metrics['support'])
        )
    
    console.print(class_table)
    
    # Confusion matrix
    console.print("\n[bold]Confusion Matrix[/bold]\n")
    cm = metrics["confusion_matrix"]
    
    # Print header
    header = "        " + " ".join(f"{name[:8]:8s}" for name in class_names)
    console.print(header)
    console.print("-" * len(header))
    
    for i, row in enumerate(cm):
        row_str = f"{class_names[i][:8]:8s}" + " ".join(f"{val:8d}" for val in row)
        console.print(row_str)


app = typer.Typer(help="Evaluate trained classifier")

_default_device = "cuda" if torch.cuda.is_available() else "cpu"


@app.command()
def main(
    model: Path = typer.Option(..., help="Path to model directory"),
    labels: Path = typer.Option(..., help="Path to validation labels JSONL"),
    output: Path = typer.Option(None, help="Output results to JSON file"),
    device: str = typer.Option(_default_device, help="Device to use"),
):
    if not model.exists():
        logger.error(f"Model not found: {model}")
        raise typer.Exit(code=1)

    if not labels.exists():
        logger.error(f"Labels not found: {labels}")
        raise typer.Exit(code=1)

    logger.info(f"Evaluating model: {model}")
    logger.info(f"Labels: {labels}")

    # Load checkpoint to get class names
    checkpoint = torch.load(model / "best_model.pt", map_location="cpu")
    class_names = [checkpoint["idx_to_label"][str(i)] for i in range(len(checkpoint["idx_to_label"]))]

    # Evaluate
    metrics = evaluate_classifier(model, labels, device)

    # Print results
    print_results(metrics, class_names)

    # Save to file
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w") as f:
            json.dump({
                "model_path": str(model),
                "labels_path": str(labels),
                "class_names": class_names,
                "metrics": metrics
            }, f, indent=2)
        console.print(f"\n[dim]Results saved to: {output}[/dim]")

    # Check success criteria
    success = (
        metrics["accuracy"] >= 0.90 and
        all(m["precision"] >= 0.80 for m in metrics["per_class_metrics"].values()) and
        metrics["inference_time_ms"]["p95"] < 100
    )

    if success:
        console.print("\n[bold green]SUCCESS CRITERIA MET[/bold green]")
    else:
        console.print("\n[bold red]SUCCESS CRITERIA NOT MET[/bold red]")
        if metrics["accuracy"] < 0.90:
            console.print(f"  - Accuracy {metrics['accuracy']:.1%} < 90%")
        if any(m["precision"] < 0.80 for m in metrics["per_class_metrics"].values()):
            console.print("  - Some classes have precision < 80%")
        if metrics["inference_time_ms"]["p95"] >= 100:
            console.print(f"  - p95 inference time {metrics['inference_time_ms']['p95']:.1f}ms >= 100ms")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
