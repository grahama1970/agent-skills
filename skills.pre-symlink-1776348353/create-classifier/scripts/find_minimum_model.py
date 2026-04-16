#!/usr/bin/env python3
"""
Find Minimum Model - Test models from smallest to largest

Based on prompt-lab's find-minimum pattern. Stops at first model meeting accuracy threshold.
"""

import typer
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import torch
from loguru import logger
from rich.console import Console
from rich.table import Table
import sys

# Add parent directory to path to allow importing templates
sys.path.append(str(Path(__file__).parent.parent))

console = Console()


# Model registry (smallest to largest)
MODEL_REGISTRY = [
    {
        "name": "mobilenetv3_small_100",
        "params": "2M",
        "inference_ms": 15,
        "priority": 1,
        "description": "Ultra-fast, good for simple tasks"
    },
    {
        "name": "efficientnet_b0",
        "params": "5M",
        "inference_ms": 45,
        "priority": 2,
        "description": "Proven success for table classifier"
    },
    {
        "name": "efficientnet_b1",
        "params": "7M",
        "inference_ms": 60,
        "priority": 3,
        "description": "Slightly more capacity than B0"
    },
    {
        "name": "resnet50",
        "params": "25M",
        "inference_ms": 80,
        "priority": 4,
        "description": "Standard CNN baseline"
    },
    {
        "name": "microsoft/dit-base",
        "params": "85M",
        "inference_ms": 150,
        "priority": 5,
        "description": "Document-specific pretrained (RVL-CDIP)"
    },
]


class ModelFinder:
    """Find smallest model meeting accuracy threshold."""
    
    def __init__(
        self,
        task_config_path: Path,
        labels_path: Path,
        threshold: float = 0.90,
        max_models: int = 10,
        quick_train_epochs: int = 5
    ):
        self.task_config = self._load_config(task_config_path)
        self.labels_path = labels_path
        self.threshold = threshold
        self.max_models = max_models
        self.quick_train_epochs = quick_train_epochs
        
        self.results: List[Dict[str, Any]] = []
    
    def _load_config(self, config_path: Path) -> Dict[str, Any]:
        """Load task configuration."""
        import yaml
        with open(config_path) as f:
            return yaml.safe_load(f)
    
    def quick_train_and_eval(self, model_config: Dict[str, Any]) -> Dict[str, Any]:
        """Quick training run to evaluate model accuracy.
        
        Returns:
            Dict with accuracy, f1, training_time_s
        """
        from templates.vision_classifier import VisionClassifier, DocumentDataset
        from torch.utils.data import DataLoader, random_split
        from torchvision import transforms
        import torch.nn as nn
        import torch.optim as optim
        from tqdm import tqdm
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Testing: {model_config['name']} ({model_config['params']})")
        logger.info(f"{'='*60}")
        
        # Prepare dataset
        transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])
        
        dataset = DocumentDataset(self.labels_path, transform=transform)
        
        # Quick train/val split
        train_size = int(0.85 * len(dataset))
        val_size = len(dataset) - train_size
        train_dataset, val_dataset = random_split(dataset, [train_size, val_size])
        
        train_loader = DataLoader(train_dataset, batch_size=16, shuffle=True, num_workers=2)
        val_loader = DataLoader(val_dataset, batch_size=16, shuffle=False, num_workers=2)
        
        # Model
        device = "cuda" if torch.cuda.is_available() else "cpu"
        num_classes = len(dataset.label_to_idx)
        model = VisionClassifier(
            num_classes=num_classes,
            backbone=model_config["name"]
        ).to(device)
        
        criterion = nn.CrossEntropyLoss()
        optimizer = optim.Adam(model.parameters(), lr=1e-3)
        
        # Quick training
        start_time = time.time()
        
        for epoch in range(self.quick_train_epochs):
            model.train()
            for images, labels, _ in tqdm(train_loader, desc=f"Epoch {epoch+1}/{self.quick_train_epochs}", leave=False):
                images, labels = images.to(device), labels.to(device)
                optimizer.zero_grad()
                logits, _ = model(images)
                loss = criterion(logits, labels)
                loss.backward()
                optimizer.step()
        
        training_time = time.time() - start_time
        
        # Evaluate
        model.eval()
        correct = 0
        total = 0
        all_preds = []
        all_labels = []
        
        with torch.no_grad():
            for images, labels, _ in val_loader:
                images, labels = images.to(device), labels.to(device)
                logits, _ = model(images)
                _, predicted = logits.max(1)
                
                correct += predicted.eq(labels).sum().item()
                total += labels.size(0)
                
                all_preds.extend(predicted.cpu().numpy())
                all_labels.extend(labels.cpu().numpy())
        
        accuracy = correct / total if total > 0 else 0
        
        # Calculate F1
        from sklearn.metrics import f1_score
        f1 = f1_score(all_labels, all_preds, average='macro')
        
        return {
            "accuracy": accuracy,
            "f1": f1,
            "training_time_s": training_time
        }
    
    def find_minimum(self) -> Optional[Dict[str, Any]]:
        """Find smallest model meeting threshold.
        
        Returns:
            Best model config or None if no model met threshold
        """
        console.print(f"\n[bold]Finding Minimum Model[/bold]")
        console.print(f"Threshold: {self.threshold:.1%}")
        console.print(f"Max models to test: {self.max_models}")
        console.print()
        
        # Sort by priority (smallest first)
        models = sorted(MODEL_REGISTRY[:self.max_models], key=lambda m: m["priority"])
        
        for model_config in models:
            try:
                metrics = self.quick_train_and_eval(model_config)
                
                result = {
                    **model_config,
                    **metrics,
                    "passed": metrics["accuracy"] >= self.threshold
                }
                self.results.append(result)
                
                # Display result
                status = "[green]✓ PASS[/green]" if result["passed"] else "[red]✗ FAIL[/red]"
                console.print(
                    f"{model_config['name']:25s} | "
                    f"Acc: {metrics['accuracy']:.1%} | "
                    f"F1: {metrics['f1']:.1%} | "
                    f"Time: {metrics['training_time_s']:.0f}s | "
                    f"{status}"
                )
                
                # Stop at first passing model
                if result["passed"]:
                    console.print(f"\n[bold green]✓ Found minimum model: {model_config['name']}[/bold green]")
                    return result
            
            except Exception as e:
                logger.error(f"Failed to test {model_config['name']}: {e}")
                self.results.append({
                    **model_config,
                    "accuracy": 0,
                    "f1": 0,
                    "training_time_s": 0,
                    "passed": False,
                    "error": str(e)
                })
        
        console.print("\n[bold red]No model met threshold[/bold red]")
        return None
    
    def print_summary(self):
        """Print summary table of all tested models."""
        console.print("\n[bold]Model Comparison[/bold]\n")
        
        table = Table()
        table.add_column("Model", style="cyan")
        table.add_column("Params", style="dim")
        table.add_column("Accuracy", style="green")
        table.add_column("F1", style="green")
        table.add_column("Train Time", style="yellow")
        table.add_column("Status")
        
        for result in self.results:
            status = "✓ PASS" if result.get("passed") else "✗ FAIL"
            status_color = "green" if result.get("passed") else "red"
            
            table.add_row(
                result["name"],
                result["params"],
                f"{result.get('accuracy', 0):.1%}",
                f"{result.get('f1', 0):.1%}",
                f"{result.get('training_time_s', 0):.0f}s",
                f"[{status_color}]{status}[/{status_color}]"
            )
        
        console.print(table)


app = typer.Typer(help="Find minimum model meeting accuracy threshold")


@app.command()
def main(
    task: str = typer.Option(..., help=""),
    labels: str = typer.Option(..., help="Path to labels JSONL"),
    threshold: float = typer.Option(0.90, help=""),
    max_models: int = typer.Option(5, help=""),
    quick_epochs: int = typer.Option(5, help=""),
    output: str = typer.Option(None, help="Output results to JSON file"),
):
    # Load config
    skill_dir = Path(__file__).parent.parent
    config_path = skill_dir / "configs" / f"{task}.yaml"
    
    if not config_path.exists():
        logger.error(f"Config not found: {config_path}")
        return 1
    
    # Run finder
    finder = ModelFinder(
        task_config_path=config_path,
        labels_path=labels,
        threshold=threshold,
        max_models=max_models,
        quick_train_epochs=quick_epochs
    )
    
    best_model = finder.find_minimum()
    finder.print_summary()
    
    # Save results
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w") as f:
            json.dump({
                "threshold": threshold,
                "tested_models": finder.results,
                "recommended_model": best_model
            }, f, indent=2)
        console.print(f"\n[dim]Results saved to: {output}[/dim]")
    
    return 0 if best_model else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
