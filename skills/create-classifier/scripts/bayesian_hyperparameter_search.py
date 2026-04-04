#!/usr/bin/env python3
"""
Bayesian Hyperparameter Search using Optuna

Based on tts-train's hyperparameter optimization pattern.
"""

import typer
import json
import time
from pathlib import Path
from typing import Any, Dict

import torch
import torch.nn as nn
import torch.optim as optim
from loguru import logger

try:
    import optuna
    from optuna.visualization import plot_optimization_history, plot_param_importances
except ImportError:
    logger.error("Optuna not installed. Install with: uv pip install optuna")
    raise


def smoke_run_training(
    model_name: str,
    labels_path: Path,
    hyperparams: Dict[str, Any],
    max_steps: int = 300,
    device: str = "cuda"
) -> float:
    """Run short training to evaluate hyperparameters.
    
    Returns:
        Validation accuracy (higher is better)
    """
    from templates.vision_classifier import VisionClassifier, DocumentDataset
    from torch.utils.data import DataLoader, random_split
    from torchvision import transforms
    
    # Dataset
    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])
    
    dataset = DocumentDataset(labels_path, transform=transform)
    train_size = int(0.85 * len(dataset))
    val_size = len(dataset) - train_size
    train_dataset, val_dataset = random_split(dataset, [train_size, val_size])
    
    train_loader = DataLoader(
        train_dataset,
        batch_size=hyperparams["batch_size"],
        shuffle=True,
        num_workers=2
    )
    val_loader = DataLoader(val_dataset, batch_size=16, shuffle=False, num_workers=2)
    
    # Model with custom dropout
    num_classes = len(dataset.label_to_idx)
    model = VisionClassifier(num_classes=num_classes, backbone=model_name).to(device)
    
    # Apply dropout to confidence head
    if hasattr(model.confidence_head, "1"):  # Assuming Sequential with Dropout at index 1
        model.confidence_head[2] = nn.Dropout(hyperparams["dropout"])
    
    # Optimizer
    if hyperparams["optimizer"] == "adam":
        optimizer = optim.Adam(
            model.parameters(),
            lr=hyperparams["lr"],
            weight_decay=hyperparams["weight_decay"]
        )
    elif hyperparams["optimizer"] == "adamw":
        optimizer = optim.AdamW(
            model.parameters(),
            lr=hyperparams["lr"],
            weight_decay=hyperparams["weight_decay"]
        )
    else:  # sgd
        optimizer = optim.SGD(
            model.parameters(),
            lr=hyperparams["lr"],
            weight_decay=hyperparams["weight_decay"],
            momentum=0.9
        )
    
    criterion = nn.CrossEntropyLoss()
    
    # Smoke run training
    model.train()
    step = 0
    
    while step < max_steps:
        for images, labels, _ in train_loader:
            if step >= max_steps:
                break
            
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            logits, _ = model(images)
            loss = criterion(logits, labels)
            loss.backward()
            optimizer.step()
            step += 1
    
    # Evaluate
    model.eval()
    correct = 0
    total = 0
    
    with torch.no_grad():
        for images, labels, _ in val_loader:
            images, labels = images.to(device), labels.to(device)
            logits, _ = model(images)
            _, predicted = logits.max(1)
            correct += predicted.eq(labels).sum().item()
            total += labels.size(0)
    
    accuracy = correct / total if total > 0 else 0
    return accuracy


def objective(
    trial: optuna.Trial,
    model_name: str,
    labels_path: Path,
    max_steps: int,
    device: str
) -> float:
    """Optuna objective function to minimize (we return negative accuracy)."""
    
    # Sample hyperparameters
    hyperparams = {
        "lr": trial.suggest_float("lr", 1e-5, 1e-2, log=True),
        "weight_decay": trial.suggest_float("weight_decay", 1e-4, 1e-1, log=True),
        "dropout": trial.suggest_float("dropout", 0.1, 0.5),
        "batch_size": trial.suggest_categorical("batch_size", [8, 16, 32]),
        "optimizer": trial.suggest_categorical("optimizer", ["adam", "adamw", "sgd"])
    }
    
    logger.info(
        f"\nTrial {trial.number}: lr={hyperparams['lr']:.2e}, "
        f"wd={hyperparams['weight_decay']:.2e}, dropout={hyperparams['dropout']:.2f}"
    )
    
    try:
        accuracy = smoke_run_training(
            model_name=model_name,
            labels_path=labels_path,
            hyperparams=hyperparams,
            max_steps=max_steps,
            device=device
        )
        
        logger.info(f"  → Accuracy: {accuracy:.1%}")
        return -accuracy  # Optuna minimizes, we want to maximize accuracy
    
    except Exception as e:
        logger.error(f"  → Trial failed: {e}")
        return float("inf")


app = typer.Typer(help="Bayesian hyperparameter search with Optuna")

_default_device = "cuda" if torch.cuda.is_available() else "cpu"


@app.command()
def main(
    task: str = typer.Option(..., help="Task config name"),
    model: str = typer.Option(..., help="Model architecture name"),
    labels: Path = typer.Option(..., help="Path to labels JSONL"),
    trials: int = typer.Option(15, help="Number of trials (default: 15)"),
    smoke_steps: int = typer.Option(300, help="Steps per smoke run (default: 300)"),
    output_dir: Path = typer.Option(..., help="Output directory for results"),
    device: str = typer.Option(_default_device, help="Device to use"),
):
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create Optuna study
    study_path = output_dir / "optuna_study.db"
    study = optuna.create_study(
        study_name=f"{task}_hp_search",
        storage=f"sqlite:///{study_path}",
        direction="minimize",  # Minimize negative accuracy
        load_if_exists=True
    )

    logger.info(f"\n{'='*60}")
    logger.info(f"Bayesian Hyperparameter Search")
    logger.info(f"{'='*60}")
    logger.info(f"Task: {task}")
    logger.info(f"Model: {model}")
    logger.info(f"Trials: {trials}")
    logger.info(f"Smoke steps: {smoke_steps}")
    logger.info(f"Study DB: {study_path}")
    logger.info(f"{'='*60}\n")

    # Run optimization
    study.optimize(
        lambda trial: objective(
            trial,
            model_name=model,
            labels_path=labels,
            max_steps=smoke_steps,
            device=device
        ),
        n_trials=trials,
        show_progress_bar=True
    )

    # Results
    best_params = study.best_params
    best_accuracy = -study.best_value  # Convert back to positive

    logger.info(f"\n{'='*60}")
    logger.info(f"Optimization Complete")
    logger.info(f"{'='*60}")
    logger.info(f"Best accuracy: {best_accuracy:.1%}")
    logger.info(f"Best trial: #{study.best_trial.number}")
    logger.info(f"Best hyperparameters:")
    for k, v in best_params.items():
        logger.info(f"  {k}: {v}")
    logger.info(f"{'='*60}\n")

    # Save best config
    best_config_path = output_dir / "best_config.json"
    with open(best_config_path, "w") as f:
        json.dump({
            "best_value": best_accuracy,
            "best_trial": study.best_trial.number,
            "hyperparameters": best_params,
            "model": model,
            "task": task
        }, f, indent=2)

    logger.info(f"Best config saved to: {best_config_path}")
    logger.info(f"\nView Optuna dashboard:")
    logger.info(f"  optuna-dashboard sqlite:///{study_path}")


if __name__ == "__main__":
    app()
