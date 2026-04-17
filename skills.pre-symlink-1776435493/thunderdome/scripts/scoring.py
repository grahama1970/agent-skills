"""Metric extraction and convergence detection for tournament scoring."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from loguru import logger


@dataclass
class StrategyScore:
    name: str
    score: float = 0.0
    raw_json: dict = field(default_factory=dict)
    error: str = ""


@dataclass
class RoundResult:
    round_num: int
    strategy_scores: list[StrategyScore] = field(default_factory=list)
    winner_name: str = ""
    winner_score: float = 0.0
    gate_passed: bool = False
    plateau_detected: bool = False
    regression_detected: bool = False
    diagnosis: str = ""


def extract_f1_from_file(path: str) -> tuple[float, dict]:
    """Read benchmark output JSON from disk, extract F1."""
    try:
        data = json.loads(open(path).read())
        f1 = data.get("selected_metrics", {}).get("macro_f1", 0.0)
        return f1, data
    except (json.JSONDecodeError, FileNotFoundError, OSError) as e:
        logger.warning(f"Cannot read {path}: {e}")
        return 0.0, {}


def score_round(
    results: list[tuple[str, float, dict]],
    gate_threshold: float,
    round_num: int,
) -> RoundResult:
    """Score a round from (name, f1, raw_json) tuples."""
    rr = RoundResult(round_num=round_num)
    for name, f1, raw in results:
        rr.strategy_scores.append(StrategyScore(name=name, score=f1, raw_json=raw))
        logger.info(f"  {name}: F1={f1:.4f}")

    if rr.strategy_scores:
        best = max(rr.strategy_scores, key=lambda s: s.score)
        rr.winner_name = best.name
        rr.winner_score = best.score
        rr.gate_passed = best.score >= gate_threshold

    return rr


def detect_plateau(rounds: list[RoundResult], window: int = 3, epsilon: float = 0.02) -> bool:
    if len(rounds) < window:
        return False
    recent = [r.winner_score for r in rounds[-window:]]
    return (max(recent) - min(recent)) < epsilon


def detect_regression(rounds: list[RoundResult], window: int = 2) -> bool:
    if len(rounds) < window + 1:
        return False
    recent = [r.winner_score for r in rounds[-(window + 1):]]
    return all(recent[i] > recent[i + 1] for i in range(len(recent) - 1))
