"""benchmark - classifier-lab.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

import torch
from torch.utils.data import DataLoader
from torchvision import transforms

from .paired_benchmark import run_paired_benchmark
from .single_benchmark import run_single_benchmark
from .utils import (
    get_backbone_candidates,
    get_device,
    get_optimizer,
    get_scheduler,
    get_transforms,
    load_data,
    load_model,
    save_report,
)

def cmd_benchmark(args: argparse.Namespace) -> None:
    """Run benchmark for given modality."""
    data_dir = args.data_dir
    modality = args.modality
    backbones = args.backbones
    epochs = args.epochs
    lr = args.lr
    batch_size = args.batch_size
    mixup_alpha = args.mixup_alpha
    cutmix_alpha = args.cutmix_alpha
    random_erasing = args.random_erasing
    dropout = args.dropout
    weight_decay = args.weight_decay
    label_smoothing = args.label_smoothing
    output_json = args.output_json
    store_memory = args.store_memory

    device = get_device()

    candidates = get_backbone_candidates(backbones)

    if modality == "single":
        from .single_benchmark import run_single_benchmark

        report = run_single_benchmark(
            data_dir=data_dir,  # type: ignore[arg-type]
            backbones=candidates,
            device=device,
            epochs=epochs,
            lr=lr,
            batch_size=batch_size,
            mixup_alpha=mixup_alpha,
            cutmix_alpha=cutmix_alpha,
            random_erasing=random_erasing,
            dropout=dropout,
            weight_decay=weight_decay,
            label_smoothing=label_smoothing,
            store_memory=store_memory,
        )
    elif modality == "paired":
        from .paired_benchmark import run_paired_benchmark

        report = run_paired_benchmark(
            data_dir=data_dir,  # type: ignore[arg-type]
            backbones=candidates,
            device=device,
            epochs=epochs,
            lr=lr,
            batch_size=batch_size,
            mixup_alpha=mixup_alpha,
            cutmix_alpha=cutmix_alpha,
            random_erasing=random_erasing,
            dropout=dropout,
            weight_decay=weight_decay,
            label_smoothing=label_smoothing,
            store_memory=store_memory,
        )
    else:
        raise ValueError(f"Unknown modality: {modality}")

    save_report(report, output_json)

def main() -> None:
    parser = argparse.ArgumentParser(description="Run classifier benchmark")
    parser.add_argument(
        "--data-dir",
        type=str,
        required=True,
        help="Path to data directory",
    )
    parser.add_argument(
        "--modality",
        type=str,
        choices=["single", "paired"],
        required=True,
        help="Modality of the data",
    )
    parser.add_argument(
        "--backbones",
        type=str,
        nargs="+",
        required=True,
        help="Backbones to benchmark",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=20,
        help="Number of epochs",
    )
    parser.add_argument(
        "--lr",
        type=float,
        default=0.0002,
        help="Learning rate",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Batch size",
    )
    parser.add_argument(
        "--mixup-alpha",
        type=float,
        default=0.0,
        help="Mixup alpha",
    )
    parser.add_argument(
        "--cutmix-alpha",
        type=float,
        default=0.0,
        help="Cutmix alpha",
    )
    parser.add_argument(
        "--random-erasing",
        type=float,
        default=0.0,
        help="Random erasing probability",
    )
    parser.add_argument(
        "--dropout",
        type=float,
        default=0.1,
        help="Dropout rate",
    )
    parser.add_argument(
        "--weight-decay",
        type=float,
        default=0.0001,
        help="Weight decay",
    )
    parser.add_argument(
        "--label-smoothing",
        type=float,
        default=0.0,
        help="Label smoothing",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        required=True,
        help="Path to output JSON file",
    )
    parser.add_argument(
        "--store-memory",
        action="store_true",
        help="Store memory usage",
    )
    args = parser.parse_args()

    cmd_benchmark(args)

if __name__ == "__main__":
    main()