"""Pre-tournament research: /analytics + /dogpile, strategy pool."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from loguru import logger

from .manifest import Strategy

SKILLS_DIR = Path(__file__).resolve().parent.parent.parent

# Strategy pool — each round picks the next N
STRATEGY_POOL = [
    # Vision strategies — work with single 224x224 images
    Strategy(name="vision-effnet-baseline", modality="vision", backbones="efficientnet_b0",
             epochs=15, lr=2e-4, batch_size=32),
    Strategy(name="vision-effnet-augmented", modality="vision", backbones="efficientnet_b0",
             epochs=30, lr=1e-4, batch_size=16, mixup_alpha=0.3, cutmix_alpha=1.0,
             random_erasing=0.25, dropout=0.2, weight_decay=1e-3, label_smoothing=0.1),
    Strategy(name="vision-convnext-augmented", modality="vision",
             backbones="convnextv2_nano.fcmae_ft_in22k_in1k",
             epochs=30, lr=5e-5, batch_size=16, mixup_alpha=0.2, cutmix_alpha=0.5,
             random_erasing=0.1, dropout=0.15, weight_decay=5e-4, label_smoothing=0.05),
    Strategy(name="vision-effnet-regularized", modality="vision", backbones="efficientnet_b0",
             epochs=40, lr=5e-5, batch_size=16, mixup_alpha=0.4, cutmix_alpha=1.0,
             random_erasing=0.3, dropout=0.3, weight_decay=5e-3, label_smoothing=0.15),
    Strategy(name="vision-convnext-long", modality="vision",
             backbones="convnextv2_nano.fcmae_ft_in22k_in1k",
             epochs=50, lr=2e-5, batch_size=8, mixup_alpha=0.3, cutmix_alpha=1.0,
             random_erasing=0.2, dropout=0.25, weight_decay=1e-3, label_smoothing=0.1),
    Strategy(name="vision-effnet-cosine", modality="vision", backbones="efficientnet_b0",
             epochs=50, lr=3e-4, batch_size=16, mixup_alpha=0.2, cutmix_alpha=0.5,
             random_erasing=0.15, dropout=0.15, weight_decay=1e-3, label_smoothing=0.05),
]


def analyze_dataset(data_dir: str) -> dict[str, Any]:
    """Analyze dataset: class counts, image sizes, balance."""
    data_path = Path(data_dir)
    if not data_path.exists():
        return {"error": f"not found: {data_dir}", "total_samples": 0}

    train_dir = data_path / "train" if (data_path / "train").exists() else data_path
    class_counts: dict[str, int] = {}
    image_sizes: list[str] = []

    for cls_dir in sorted(train_dir.iterdir()):
        if cls_dir.is_dir() and not cls_dir.name.startswith("."):
            images = list(cls_dir.glob("*.png")) + list(cls_dir.glob("*.jpg"))
            if images:
                class_counts[cls_dir.name] = len(images)
                if not image_sizes:
                    try:
                        from PIL import Image
                        with Image.open(images[0]) as img:
                            image_sizes.append(f"{img.width}x{img.height}")
                    except Exception:
                        pass

    total = sum(class_counts.values())
    balanced = (max(class_counts.values()) / max(min(class_counts.values()), 1) < 2.0) if class_counts else False

    analytics = {
        "data_dir": data_dir, "total_samples": total, "n_classes": len(class_counts),
        "class_counts": class_counts, "balanced": balanced, "image_sizes": image_sizes,
        "has_val": (data_path / "val").exists(), "has_test": (data_path / "test").exists(),
    }
    logger.info(f"Dataset: {total} samples, {len(class_counts)} classes, balanced={balanced}")
    return analytics


def dogpile_research(query: str, scope: str) -> str:
    """Call /dogpile skill. Returns result text."""
    skill_dir = SKILLS_DIR / "dogpile"
    cmd = f'cd {skill_dir} && ./run.sh search "{query}"'
    try:
        proc = subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True,
                              timeout=180, env={**os.environ, "VIRTUAL_ENV": ""})
        return proc.stdout if proc.returncode == 0 else proc.stderr[:500]
    except Exception as e:
        logger.warning(f"/dogpile failed: {e}")
        return ""


def pick_strategies(n: int, round_num: int) -> list[Strategy]:
    """Pick next N strategies from the pool for this round."""
    start = ((round_num - 1) * n) % len(STRATEGY_POOL)
    selected = [STRATEGY_POOL[(start + i) % len(STRATEGY_POOL)] for i in range(n)]
    for s in selected:
        logger.info(f"Strategy '{s.name}': {s.modality} {s.backbones} lr={s.lr} epochs={s.epochs}")
    return selected
