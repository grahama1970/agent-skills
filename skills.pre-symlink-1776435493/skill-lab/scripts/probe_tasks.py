"""Load probe tasks from mined chain data for gap detection.

Replaces hardcoded PROBE_TASKS with real user requests from
chains_classifier.jsonl and skill_chains.jsonl. Also generates
structural gap probes from skill naming patterns (create-X without
review-X, create-X + review-X without X-lab).
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from loguru import logger

STATE_DIR = Path(__file__).resolve().parent.parent / "state"
SKILLS_ROOT = Path(__file__).resolve().parent.parent.parent

# Fallback tasks if no chain data exists yet (bootstrap only)
_FALLBACK_TASKS = [
    "extract tables from PDF and validate quality",
    "research a topic and store findings",
    "scan for vulnerabilities and report",
    "train a classifier from labeled data",
    "monitor system health and alert",
]


def _load_chain_inputs(max_tasks: int = 30) -> list[str]:
    """Load unique user request strings from chain JSONL files."""
    inputs: set[str] = set()
    for filename in ["chains_classifier.jsonl", "skill_chains.jsonl"]:
        path = STATE_DIR / filename
        if not path.exists():
            continue
        try:
            with path.open() as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(record, dict):
                        continue
                    text = str(
                        record.get("input")
                        or record.get("request")
                        or record.get("text")
                        or ""
                    ).strip()
                    if text and len(text) > 20:
                        inputs.add(text[:200])
                        if len(inputs) >= max_tasks:
                            break
            if len(inputs) >= max_tasks:
                break
        except OSError as exc:
            logger.warning("Failed to read chain file {}: {}", filename, exc)
            continue
    return list(inputs)[:max_tasks]


def _detect_structural_gaps() -> list[str]:
    """Generate probe tasks from skill naming pattern gaps.

    Detects: create-X without review-X, create-X + review-X without X-lab.
    """
    probes: set[str] = set()
    if not SKILLS_ROOT.exists() or not SKILLS_ROOT.is_dir():
        logger.warning("Skills root not found: {}", SKILLS_ROOT)
        return []
    try:
        skills = {d.name for d in SKILLS_ROOT.iterdir() if d.is_dir() and not d.name.startswith(".")}
    except OSError as exc:
        logger.warning("Failed to scan skills root: {}", exc)
        return []

    for skill in skills:
        if skill.startswith("create-"):
            base = skill[7:]  # strip "create-"
            if f"review-{base}" not in skills:
                probes.add(f"create and then review a {base}")
            if f"review-{base}" in skills and f"{base}-lab" not in skills:
                probes.add(f"iteratively improve a {base} with convergence")
    return sorted(probes)


def load_probe_tasks(max_total: int = 20) -> list[str]:
    """Load probe tasks from mined chains + structural gap detection.

    Priority: mined chain inputs > structural gap probes > fallback.
    Samples up to max_total to keep runtime bounded.
    """
    tasks: list[str] = []

    # 1. Real user requests from chain data
    chain_tasks = _load_chain_inputs(max_tasks=50)
    if chain_tasks:
        tasks.extend(random.sample(chain_tasks, min(len(chain_tasks), max_total // 2)))

    # 2. Structural gap probes
    structural = _detect_structural_gaps()
    remaining = max_total - len(tasks)
    if structural and remaining > 0:
        tasks.extend(random.sample(structural, min(len(structural), remaining)))

    # 3. Fallback if nothing else
    if not tasks:
        logger.warning("No chain data found, using fallback probe tasks")
        tasks = _FALLBACK_TASKS

    logger.info(f"Loaded {len(tasks)} probe tasks ({len(chain_tasks)} from chains, {len(structural)} structural)")
    return tasks[:max_total]
