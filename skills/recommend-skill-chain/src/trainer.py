"""Retrain coordinator: chain_miner refresh + classifier retrain."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from loguru import logger

SKILLS_ROOT = Path(__file__).resolve().parents[2]
SKILL_LAB_SCRIPTS = SKILLS_ROOT / "skill-lab" / "scripts"
ASSISTANT_DIR = SKILLS_ROOT / "assistant"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def retrain() -> dict:
    """Run full retrain pipeline: mine chains → prepare data → retrain classifier."""
    steps: dict[str, dict] = {}
    success = True

    # Step 1: Mine new chains via chain_miner
    chain_miner = SKILL_LAB_SCRIPTS / "chain_miner.py"
    if chain_miner.exists():
        try:
            result = subprocess.run(
                [sys.executable, str(chain_miner), "prepare", "--output-dir", str(DATA_DIR)],
                capture_output=True, text=True, timeout=120,
                cwd=str(SKILL_LAB_SCRIPTS),
            )
            steps["chain_miner_prepare"] = {
                "success": result.returncode == 0,
                "stdout": result.stdout[-500:] if result.stdout else "",
                "error": result.stderr[-500:] if result.returncode != 0 else "",
            }
            if result.returncode != 0:
                success = False
        except Exception as e:
            steps["chain_miner_prepare"] = {"success": False, "error": str(e)}
            success = False
    else:
        steps["chain_miner_prepare"] = {"success": False, "error": "chain_miner.py not found"}
        success = False

    # Step 2: Retrain skill-chain-router classifier
    train_classifiers = ASSISTANT_DIR / "train_classifiers.py"
    if train_classifiers.exists():
        try:
            result = subprocess.run(
                [sys.executable, str(train_classifiers), "--task", "skill-chain-router"],
                capture_output=True, text=True, timeout=300,
                cwd=str(ASSISTANT_DIR),
            )
            steps["train_classifier"] = {
                "success": result.returncode == 0,
                "stdout": result.stdout[-500:] if result.stdout else "",
                "error": result.stderr[-500:] if result.returncode != 0 else "",
            }
            if result.returncode != 0:
                success = False
        except Exception as e:
            steps["train_classifier"] = {"success": False, "error": str(e)}
            success = False
    else:
        steps["train_classifier"] = {"success": False, "error": "train_classifiers.py not found"}
        success = False

    return {"success": success, "steps": steps}
