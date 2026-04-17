"""
Camelot extraction reward function.

Executes Camelot with predicted strategy and scores the result.
This is the primary reward signal for GRPO training.
"""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import camelot
except ImportError:
    camelot = None

from loguru import logger


@dataclass
class ExtractionResult:
    """Result of a Camelot extraction attempt."""
    success: bool
    table_count: int
    accuracy: float
    extraction_time: float
    error: Optional[str] = None


@dataclass
class StrategyPrediction:
    """Predicted extraction strategy."""
    strategy: str  # "lattice", "stream", "lattice_sensitive"
    line_scale: int
    edge_tol: int
    confidence: float

    @property
    def flavor(self) -> str:
        """Get Camelot flavor parameter."""
        if self.strategy in ("lattice", "lattice_sensitive"):
            return "lattice"
        return "stream"

    def to_camelot_params(self) -> dict:
        """Convert to Camelot read_pdf kwargs."""
        params = {"flavor": self.flavor}
        if self.flavor == "lattice":
            params["line_scale"] = self.line_scale
        else:
            params["edge_tol"] = self.edge_tol
        return params


def bbox_to_camelot_area(bbox: tuple[float, float, float, float]) -> str:
    """Convert (x1, y1, x2, y2) bbox to Camelot table_areas format."""
    x1, y1, x2, y2 = bbox
    # Camelot uses (x1, y1, x2, y2) comma-separated string
    return f"{x1},{y1},{x2},{y2}"


def run_camelot_extraction(
    pdf_path: Path,
    page: int,
    prediction: StrategyPrediction,
    bbox: Optional[tuple[float, float, float, float]] = None,
    timeout: float = 30.0,
) -> ExtractionResult:
    """
    Execute Camelot with predicted strategy.

    Args:
        pdf_path: Path to PDF file
        page: Page number (0-indexed)
        prediction: Strategy prediction
        bbox: Optional table bounding box
        timeout: Maximum extraction time in seconds

    Returns:
        ExtractionResult with success, accuracy, timing
    """
    if camelot is None:
        return ExtractionResult(
            success=False,
            table_count=0,
            accuracy=0.0,
            extraction_time=0.0,
            error="camelot not installed"
        )

    start_time = time.time()

    try:
        kwargs = prediction.to_camelot_params()
        kwargs["pages"] = str(page + 1)  # Camelot uses 1-indexed pages

        if bbox:
            kwargs["table_areas"] = [bbox_to_camelot_area(bbox)]

        tables = camelot.read_pdf(str(pdf_path), **kwargs)

        extraction_time = time.time() - start_time

        if not tables:
            return ExtractionResult(
                success=False,
                table_count=0,
                accuracy=0.0,
                extraction_time=extraction_time,
                error="no tables found"
            )

        # Compute mean accuracy across tables
        accuracies = [t.accuracy for t in tables]
        mean_accuracy = sum(accuracies) / len(accuracies)

        return ExtractionResult(
            success=True,
            table_count=len(tables),
            accuracy=mean_accuracy,
            extraction_time=extraction_time,
        )

    except Exception as e:
        extraction_time = time.time() - start_time
        return ExtractionResult(
            success=False,
            table_count=0,
            accuracy=0.0,
            extraction_time=extraction_time,
            error=str(e)
        )


# Baseline extraction times for speed reward calculation
# Based on empirical measurements from 1000 PDFs
BASELINE_TIMES = {
    "lattice": 2.5,  # seconds
    "stream": 1.8,
    "lattice_sensitive": 3.0,
}


def compute_extraction_reward(
    pdf_path: Path,
    page: int,
    prediction: StrategyPrediction,
    bbox: Optional[tuple[float, float, float, float]] = None,
    ground_truth_strategy: Optional[str] = None,
) -> tuple[float, dict]:
    """
    Execute Camelot and compute reward for GRPO.

    Reward components:
    - Quality (50%): Camelot accuracy score
    - Speed (30%): Faster than baseline = bonus
    - Strategy match (20%): Matches ground truth if available

    Args:
        pdf_path: Path to PDF file
        page: Page number (0-indexed)
        prediction: Strategy prediction
        bbox: Optional table bounding box
        ground_truth_strategy: Optional known correct strategy

    Returns:
        Tuple of (reward, metadata_dict)
    """
    result = run_camelot_extraction(pdf_path, page, prediction, bbox)

    # Failed extraction = negative reward
    if not result.success:
        return -1.0, {
            "success": False,
            "error": result.error,
            "reward_components": {
                "quality": 0.0,
                "speed": 0.0,
                "strategy_match": 0.0,
            }
        }

    # Quality reward (50%): accuracy score
    quality_reward = result.accuracy / 100.0  # Camelot returns 0-100

    # Speed reward (30%): ratio vs baseline
    baseline = BASELINE_TIMES.get(prediction.strategy, 2.5)
    speed_ratio = baseline / max(result.extraction_time, 0.1)
    speed_reward = min(1.0, speed_ratio)  # Cap at 1.0

    # Strategy match reward (20%): matches ground truth
    if ground_truth_strategy:
        strategy_match_reward = 1.0 if prediction.strategy == ground_truth_strategy else 0.0
    else:
        strategy_match_reward = 0.5  # Neutral when no ground truth

    # Combined reward
    reward = (
        0.5 * quality_reward +
        0.3 * speed_reward +
        0.2 * strategy_match_reward
    )

    metadata = {
        "success": True,
        "table_count": result.table_count,
        "accuracy": result.accuracy,
        "extraction_time": result.extraction_time,
        "reward_components": {
            "quality": quality_reward,
            "speed": speed_reward,
            "strategy_match": strategy_match_reward,
        }
    }

    return reward, metadata


def compute_batch_extraction_rewards(
    examples: list[dict],
    predictions: list[StrategyPrediction],
    corpus_dir: Path,
) -> list[tuple[float, dict]]:
    """
    Compute extraction rewards for a batch of examples.

    Args:
        examples: List of training examples with pdf_path, page, bbox
        predictions: List of strategy predictions
        corpus_dir: Base directory for finding PDFs

    Returns:
        List of (reward, metadata) tuples
    """
    results = []

    for example, pred in zip(examples, predictions):
        pdf_name = example.get("source_pdf", "")
        pdf_path = corpus_dir / pdf_name

        if not pdf_path.exists():
            results.append((-1.0, {"error": "pdf not found"}))
            continue

        page = example.get("page", 0)
        bbox = example.get("bbox")
        if bbox:
            bbox = tuple(bbox)

        ground_truth = example.get("strategy")

        reward, meta = compute_extraction_reward(
            pdf_path, page, pred, bbox, ground_truth
        )
        results.append((reward, meta))

    return results
