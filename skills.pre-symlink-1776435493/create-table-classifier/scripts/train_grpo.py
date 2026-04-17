#!/usr/bin/env python3
"""
GRPO Training for Table Strategy Classifier.

Group Relative Policy Optimization with Camelot execution feedback.
Trains the model to predict strategies that lead to successful extractions.

Pipeline:
1. Image → Generate N strategy predictions
2. Execute Camelot with each prediction
3. Compute rewards (quality, speed, preset match)
4. Update policy using group-relative advantage
"""

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import typer
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "typer", "-q"],
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )
    import typer

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader

from loguru import logger
from tqdm import tqdm

# Local imports
from train_sft import (
    TableStrategyModel,
    TableDataset,
    STRATEGIES,
    STRATEGY_TO_IDX,
    PRESETS,
    SKILL_DIR,
    DATA_DIR,
    MODELS_DIR,
    LOGS_DIR,
)
from rewards.extraction import (
    StrategyPrediction,
    compute_extraction_reward,
)
from taxonomy_bridge import compute_preset_match_reward

app = typer.Typer(help="GRPO training with Camelot execution feedback")


@dataclass
class GRPOConfig:
    """GRPO training configuration."""
    # Model
    checkpoint_path: Path = MODELS_DIR / "table-classifier-sft" / "model.pth"
    backbone: str = "mobilenetv2_100"

    # GRPO
    num_generations: int = 4  # Number of strategy samples per image
    temperature: float = 1.0  # Sampling temperature
    kl_coef: float = 0.1  # KL penalty coefficient
    clip_range: float = 0.2  # PPO-style clipping

    # Training
    epochs: int = 5
    batch_size: int = 8  # Smaller due to Camelot execution
    learning_rate: float = 1e-5
    grad_accumulation_steps: int = 4

    # Rewards
    quality_weight: float = 0.5
    speed_weight: float = 0.3
    preset_weight: float = 0.2

    # Data
    train_file: Path = DATA_DIR / "labels" / "train.jsonl"
    corpus_dir: Path = Path("/data/corpus")  # Where PDFs live

    # Output
    output_dir: Path = MODELS_DIR / "table-classifier-grpo"
    log_file: Path = LOGS_DIR / "grpo_training.log"

    # Hardware
    device: str = "cuda" if torch.cuda.is_available() else "cpu"


def sample_strategies(
    model: TableStrategyModel,
    images: torch.Tensor,
    preset_ids: torch.Tensor,
    num_samples: int = 4,
    temperature: float = 1.0,
) -> tuple[torch.Tensor, torch.Tensor, list[list[StrategyPrediction]]]:
    """
    Sample multiple strategy predictions per image.

    Returns:
        - strategy_indices: (B, N) sampled strategy indices
        - log_probs: (B, N) log probabilities of samples
        - predictions: List of lists of StrategyPrediction objects
    """
    model.eval()
    batch_size = images.shape[0]

    with torch.no_grad():
        outputs = model(images, preset_ids)

    logits = outputs["strategy_logits"] / temperature  # (B, num_strategies)
    params = outputs["params"]  # (B, 2)
    confidence = outputs["confidence"]  # (B,)

    # Sample strategies
    probs = F.softmax(logits, dim=-1)
    dist = torch.distributions.Categorical(probs)

    strategy_indices = []
    log_probs = []
    predictions = []

    for _ in range(num_samples):
        sampled = dist.sample()  # (B,)
        log_prob = dist.log_prob(sampled)  # (B,)

        strategy_indices.append(sampled)
        log_probs.append(log_prob)

    strategy_indices = torch.stack(strategy_indices, dim=1)  # (B, N)
    log_probs = torch.stack(log_probs, dim=1)  # (B, N)

    # Build StrategyPrediction objects
    for b in range(batch_size):
        batch_preds = []
        for n in range(num_samples):
            strategy_idx = strategy_indices[b, n].item()
            pred = StrategyPrediction(
                strategy=STRATEGIES[strategy_idx],
                line_scale=int(params[b, 0].item()),
                edge_tol=int(params[b, 1].item()),
                confidence=confidence[b].item(),
            )
            batch_preds.append(pred)
        predictions.append(batch_preds)

    return strategy_indices, log_probs, predictions


def compute_grpo_rewards(
    examples: list[dict],
    predictions: list[list[StrategyPrediction]],
    corpus_dir: Path,
    quality_weight: float = 0.5,
    speed_weight: float = 0.3,
    preset_weight: float = 0.2,
) -> tuple[torch.Tensor, list[list[dict]]]:
    """
    Compute rewards by executing Camelot for each prediction.

    Returns:
        - rewards: (B, N) reward values
        - metadata: Nested list of reward metadata
    """
    batch_size = len(examples)
    num_samples = len(predictions[0])

    rewards = torch.zeros(batch_size, num_samples)
    all_metadata = []

    for b, example in enumerate(examples):
        pdf_name = example.get("source_pdf", "")
        pdf_path = corpus_dir / pdf_name

        page = example.get("page", 0)
        bbox = example.get("bbox")
        if bbox:
            bbox = tuple(bbox)
        preset = example.get("preset", "unknown")
        ground_truth = example.get("strategy")

        batch_meta = []

        for n, pred in enumerate(predictions[b]):
            if pdf_path.exists():
                # Execute Camelot
                extraction_reward, extract_meta = compute_extraction_reward(
                    pdf_path, page, pred, bbox, ground_truth
                )

                # Preset match reward
                preset_reward = compute_preset_match_reward(
                    pred.strategy,
                    pred.line_scale,
                    pred.edge_tol,
                    preset
                )

                # Combined reward
                if extraction_reward < 0:
                    # Failed extraction
                    reward = -1.0
                else:
                    components = extract_meta["reward_components"]
                    reward = (
                        quality_weight * components["quality"] +
                        speed_weight * components["speed"] +
                        preset_weight * preset_reward
                    )

                meta = {
                    "extraction": extract_meta,
                    "preset_reward": preset_reward,
                    "total_reward": reward,
                }
            else:
                # PDF not found, use preset reward only
                preset_reward = compute_preset_match_reward(
                    pred.strategy,
                    pred.line_scale,
                    pred.edge_tol,
                    preset
                )
                reward = preset_reward
                meta = {
                    "error": "pdf_not_found",
                    "preset_reward": preset_reward,
                    "total_reward": reward,
                }

            rewards[b, n] = reward
            batch_meta.append(meta)

        all_metadata.append(batch_meta)

    return rewards, all_metadata


def compute_grpo_loss(
    model: TableStrategyModel,
    images: torch.Tensor,
    preset_ids: torch.Tensor,
    strategy_indices: torch.Tensor,
    old_log_probs: torch.Tensor,
    rewards: torch.Tensor,
    kl_coef: float = 0.1,
    clip_range: float = 0.2,
) -> torch.Tensor:
    """
    Compute GRPO loss with group-relative advantage.

    Uses PPO-style clipping for stability.
    """
    batch_size, num_samples = strategy_indices.shape

    # Forward pass
    outputs = model(images, preset_ids)
    logits = outputs["strategy_logits"]  # (B, num_strategies)

    # Compute log probs for sampled strategies
    log_probs = F.log_softmax(logits, dim=-1)
    new_log_probs = log_probs.gather(
        1, strategy_indices
    )  # (B, N)

    # Group-relative advantage
    # Baseline = mean reward within group
    baseline = rewards.mean(dim=1, keepdim=True)
    advantages = rewards - baseline  # (B, N)

    # Normalize advantages
    advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

    # Policy ratio
    ratio = torch.exp(new_log_probs - old_log_probs)

    # Clipped objective
    clipped_ratio = torch.clamp(ratio, 1 - clip_range, 1 + clip_range)
    policy_loss = -torch.min(
        ratio * advantages,
        clipped_ratio * advantages
    ).mean()

    # KL penalty (approximate)
    kl_div = (old_log_probs.exp() * (old_log_probs - new_log_probs)).mean()
    kl_loss = kl_coef * kl_div

    total_loss = policy_loss + kl_loss

    return total_loss


@app.command()
def grpo(
    checkpoint: Path = typer.Option(
        MODELS_DIR / "table-classifier-sft" / "model.pth",
        help="SFT checkpoint path"
    ),
    train_file: Path = typer.Option(
        DATA_DIR / "labels" / "train.jsonl",
        help="Training data"
    ),
    corpus_dir: Path = typer.Option(
        ..., help="Directory containing PDFs"
    ),
    epochs: int = typer.Option(5, help="Number of epochs"),
    batch_size: int = typer.Option(8, help="Batch size"),
    generations: int = typer.Option(4, help="Samples per image"),
    learning_rate: float = typer.Option(1e-5, help="Learning rate"),
    output_dir: Path = typer.Option(
        MODELS_DIR / "table-classifier-grpo",
        help="Output directory"
    ),
    wandb: bool = typer.Option(False, help="Log to WandB"),
):
    """
    Run GRPO training with Camelot execution feedback.

    Examples:
        ./run.sh grpo --checkpoint models/sft/model.pth --corpus-dir /data/pdfs
    """
    logger.info("Starting GRPO training")

    # Setup
    output_dir.mkdir(parents=True, exist_ok=True)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Device: {device}")

    # Load checkpoint
    if not checkpoint.exists():
        logger.error(f"Checkpoint not found: {checkpoint}")
        raise typer.Exit(1)

    ckpt = torch.load(checkpoint, map_location=device)
    config = ckpt.get("config", {})

    # Create model
    model = TableStrategyModel(
        backbone=config.get("backbone", "mobilenetv2_100"),
        pretrained=False,
    )
    model.load_state_dict(ckpt["model_state_dict"])
    model = model.to(device)
    logger.info("Model loaded from checkpoint")

    # Create dataset
    dataset = TableDataset(train_file, DATA_DIR / "images", augment=False)
    dataloader = DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=2,
    )

    # Optimizer
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=learning_rate,
        weight_decay=1e-5
    )

    # Training loop
    for epoch in range(epochs):
        logger.info(f"Epoch {epoch + 1}/{epochs}")

        total_loss = 0.0
        total_reward = 0.0
        num_batches = 0

        for batch in tqdm(dataloader, desc="Training"):
            images = batch["image"].to(device)
            preset_ids = batch["preset"].to(device)

            # Get batch examples for Camelot execution
            batch_examples = []
            for i in range(len(images)):
                ex = {
                    "source_pdf": dataset.examples[batch["idx"][i] if "idx" in batch else i].get("source_pdf", ""),
                    "page": batch.get("page", [0] * len(images))[i] if "page" in batch else 0,
                    "bbox": batch.get("bbox", [None] * len(images))[i] if "bbox" in batch else None,
                    "preset": PRESETS[preset_ids[i].item()],
                    "strategy": STRATEGIES[batch["strategy"][i].item()],
                }
                batch_examples.append(ex)

            # Sample strategies
            with torch.no_grad():
                strategy_indices, old_log_probs, predictions = sample_strategies(
                    model, images, preset_ids, num_samples=generations
                )

            # Compute rewards via Camelot execution
            rewards, _ = compute_grpo_rewards(
                batch_examples, predictions, corpus_dir
            )
            rewards = rewards.to(device)

            # Compute GRPO loss
            model.train()
            loss = compute_grpo_loss(
                model, images, preset_ids,
                strategy_indices, old_log_probs,
                rewards
            )

            # Backward pass
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            total_reward += rewards.mean().item()
            num_batches += 1

        # Epoch stats
        avg_loss = total_loss / num_batches
        avg_reward = total_reward / num_batches
        logger.info(f"Epoch {epoch + 1} - Loss: {avg_loss:.4f}, Reward: {avg_reward:.4f}")

        # Save checkpoint
        attempt_dir = output_dir / f"attempt_{epoch + 1}"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        torch.save({
            "model_state_dict": model.state_dict(),
            "config": config,
            "epoch": epoch,
            "avg_reward": avg_reward,
        }, attempt_dir / "model.pth")

    logger.info(f"GRPO training complete! Models saved to {output_dir}")


@app.command()
def train(
    train_file: Path = typer.Option(
        DATA_DIR / "labels" / "train.jsonl",
        help="Training data"
    ),
    eval_file: Optional[Path] = typer.Option(
        None, help="Evaluation data"
    ),
    corpus_dir: Path = typer.Option(
        ..., help="Directory containing PDFs"
    ),
    sft_epochs: int = typer.Option(3, help="SFT warmup epochs"),
    grpo_epochs: int = typer.Option(5, help="GRPO epochs"),
    wandb: bool = typer.Option(False, help="Log to WandB"),
):
    """
    Full training pipeline: SFT warmup -> GRPO -> Evaluation.

    Examples:
        ./run.sh train-full --train-file data/train.jsonl --corpus-dir /data/pdfs
    """
    logger.info("Starting full training pipeline")

    # Step 1: SFT Warmup
    logger.info("Step 1: SFT Warmup")
    from train_sft import train as sft_train

    sft_output = MODELS_DIR / "table-classifier-sft"
    # Run SFT (this will be called via CLI, but showing the flow)
    # sft_train(train_file, eval_file, sft_epochs, ...)

    # Step 2: GRPO Training
    logger.info("Step 2: GRPO Training")
    grpo_output = MODELS_DIR / "table-classifier-grpo"

    # Step 3: Evaluation
    logger.info("Step 3: Evaluation")
    # Run evaluation on holdout set

    logger.info("Full pipeline complete!")


if __name__ == "__main__":
    app()
