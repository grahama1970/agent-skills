"""Shadow-LEGO strategy routing for table extraction.

3-tier cascade:
  T0:   Heuristic (line density, text gaps)
  T0.5: /assistant classify(task="table-strategy-router")
  T2:   /scillm teacher (novel layouts, paid)

Escalation stops at first confident tier (confidence >= 0.7).

Self-correction: if accuracy < 80%, try alternative strategy.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

CONFIDENCE_THRESHOLD = float(os.environ.get("STRATEGY_CONFIDENCE_THRESHOLD", "0.7"))
SKILL_DIR = Path(__file__).resolve().parent.parent.parent
STRATEGY_MEMORY_PATH = SKILL_DIR / "strategy_memory.json"

STRATEGIES = {
    "lattice": "LatticeParser",
    "stream": "StreamParser",
    "network": "NetworkParser",
    "hybrid": "HybridParser",
}

FALLBACK_ORDER = {
    "lattice": ["hybrid", "stream", "network"],
    "stream": ["lattice", "hybrid", "network"],
    "network": ["lattice", "stream", "hybrid"],
    "hybrid": ["lattice", "stream", "network"],
}

# Mapping from extractor pipeline strategy names to flavors
STRATEGY_MAP = {
    "lattice_default": ("lattice", {"line_scale": 15}),
    "lattice_strong": ("lattice", {"line_scale": 40}),
    "lattice_sensitive": ("lattice", {"line_scale": 5}),
    "stream_default": ("stream", {"edge_tol": 50}),
    "stream_tight": ("stream", {"edge_tol": 30, "row_tol": 5}),
    "stream_wide": ("stream", {"edge_tol": 80, "row_tol": 15}),
    "stream_columns": ("stream", {"edge_tol": 50, "column_tol": 10}),
}


def _analyze_grid_regularity(pdf_path: str, page_num: int) -> dict[str, float]:
    """Analyze rendered page for grid structure regularity.

    Returns dict with:
    - 'has_lines': bool-like 0/1 indicating whether significant lines found
    - 'grid_regularity': 0.0-1.0 how regular/complete the grid is
      (1.0 = all lines span full table width/height, 0.0 = no grid)
    - 'v_full_ratio': fraction of vertical lines spanning full table height
    - 'h_full_ratio': fraction of horizontal lines spanning full table width
    """
    result = {"has_lines": 0.0, "grid_regularity": 0.0,
              "v_full_ratio": 0.0, "h_full_ratio": 0.0}
    try:
        import numpy as np
        from PIL import Image
        from .pdf_bridge import render_page_image
    except ImportError:
        return result

    try:
        img = render_page_image(pdf_path, page_num, dpi=72)
    except Exception:
        return result

    gray = img.convert("L")
    arr = np.array(gray)
    h, w = arr.shape
    if h == 0 or w == 0:
        return result

    try:
        import cv2
    except ImportError:
        return result

    # Global threshold to get dark pixels (lines and text)
    _, binary = cv2.threshold(arr, 200, 255, cv2.THRESH_BINARY_INV)

    # Detect vertical lines (must be at least 1/15 of page height)
    v_min_len = max(h // 15, 1)
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_min_len))
    v_mask = cv2.erode(binary, v_kernel)
    v_mask = cv2.dilate(v_mask, v_kernel)
    v_contours, _ = cv2.findContours(v_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Filter for thin vertical lines only (width < 10px)
    v_heights = []
    for c in v_contours:
        _, _, cw, ch = cv2.boundingRect(c)
        if cw < 10:
            v_heights.append(ch)

    # Detect horizontal lines (must be at least 1/15 of page width)
    h_min_len = max(w // 15, 1)
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_min_len, 1))
    h_mask = cv2.erode(binary, h_kernel)
    h_mask = cv2.dilate(h_mask, h_kernel)
    h_contours, _ = cv2.findContours(h_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    h_widths = []
    for c in h_contours:
        _, _, cw, ch = cv2.boundingRect(c)
        if ch < 10:
            h_widths.append(cw)

    # Need at least a few lines to consider it a grid
    if len(v_heights) < 2 or len(h_widths) < 2:
        return result

    result["has_lines"] = 1.0

    # Compute full-span ratio: fraction of lines that span ~full table dim
    max_vh = max(v_heights) if v_heights else 1
    v_full = sum(1 for vh in v_heights if vh > max_vh * 0.8)
    v_full_ratio = v_full / len(v_heights)

    max_hw = max(h_widths) if h_widths else 1
    h_full = sum(1 for hw in h_widths if hw > max_hw * 0.8)
    h_full_ratio = h_full / len(h_widths)

    grid_regularity = (v_full_ratio + h_full_ratio) / 2.0

    result["v_full_ratio"] = v_full_ratio
    result["h_full_ratio"] = h_full_ratio
    result["grid_regularity"] = grid_regularity

    return result


def _analyze_text_structure(pdf_path: str, page_num: int) -> dict[str, float]:
    """Analyze text layout for table structure indicators.

    Returns dict with:
    - 'regularity': how regular the text spacing is (0-1)
    - 'text_count': number of text elements
    """
    try:
        from .pdf_bridge import extract_text_elements
    except ImportError:
        return {"regularity": 0.0, "text_count": 0}

    try:
        elements = extract_text_elements(pdf_path, page_num)
    except Exception:
        return {"regularity": 0.0, "text_count": 0}

    if not elements:
        return {"regularity": 0.0, "text_count": 0}

    # Group by y position (rows)
    sorted_elems = sorted(elements, key=lambda e: (e.y0, e.x0))
    rows: list[list] = []
    current_row: list = [sorted_elems[0]]
    row_y = sorted_elems[0].y0

    for elem in sorted_elems[1:]:
        if abs(elem.y0 - row_y) < 5:
            current_row.append(elem)
        else:
            if current_row:
                rows.append(current_row)
            current_row = [elem]
            row_y = elem.y0
    if current_row:
        rows.append(current_row)

    if len(rows) < 2:
        return {"regularity": 0.0, "text_count": len(elements)}

    # Check regularity: consistent number of elements per row
    row_counts = [len(r) for r in rows]
    from collections import Counter
    counter = Counter(row_counts)
    most_common_count, most_common_freq = counter.most_common(1)[0]

    regularity = most_common_freq / len(rows) if len(rows) > 0 else 0.0

    return {
        "regularity": regularity,
        "text_count": len(elements),
    }


def select_strategy(
    filepath: str,
    page_num: int = 0,
    pages: str = "1",
    **kwargs,
) -> tuple[str, float]:
    """Select extraction strategy using Shadow-LEGO cascade.

    Returns (strategy_name, confidence) tuple.

    T0 Heuristic:
    - Render page, check for line structures
    - If strong lines detected -> "lattice"
    - If no lines but text with regular spacing -> "stream"
    - If mixed signals -> "hybrid"
    """
    # Check if caller provided a strategy hint
    strategy_hint = kwargs.get("strategy_hint")
    if strategy_hint and strategy_hint in STRATEGY_MAP:
        flavor, _ = STRATEGY_MAP[strategy_hint]
        return flavor, 0.8

    # Tier -1: Strategy memory (remembered best for this PDF domain)
    recalled = recall_strategy(filepath)
    if recalled is not None:
        return recalled[0], 0.85

    # Tier 0.5: Classifier (if available and confident)
    result = _classifier_strategy(filepath, **kwargs)
    if result is not None:
        return result

    # Tier 0: Heuristic
    return _heuristic_strategy(filepath, page_num, **kwargs)


def _heuristic_strategy(filepath: str, page_num: int = 0, **kwargs) -> tuple[str, float]:
    """Tier 0: Fast heuristic based on page analysis.

    Lines-first: check for grid structure before text regularity.
    If a PDF has visible borders, lattice should always be preferred.

    Decision tree:
    - Lines detected with any grid structure -> lattice
    - No lines but regular text spacing -> stream
    - No lines and irregular text -> stream (low confidence)
    """
    # Check for lines first (uses 72 DPI for speed)
    grid_info = _analyze_grid_regularity(filepath, page_num)
    has_lines = grid_info["has_lines"] > 0.5

    if has_lines:
        # Lines found — always prefer lattice. The lattice parser's
        # multi-config probe will find the right parameters.
        regularity = grid_info["grid_regularity"]
        return "lattice", min(0.7 + regularity * 0.2, 0.95)

    # No lines — analyze text structure for borderless tables
    text_info = _analyze_text_structure(filepath, page_num)

    if text_info["regularity"] > 0.3 and text_info["text_count"] > 10:
        return "stream", min(0.5 + text_info["regularity"] * 0.3, 0.85)
    else:
        return "stream", 0.5


def _classifier_strategy(filepath: str, **kwargs) -> tuple[str, float] | None:
    """Tier 0.5: /assistant classify for strategy routing.

    Returns None if classifier unavailable or not confident.
    """
    try:
        from assistant.assistant import classify
        result = classify(
            task="table-strategy-router",
            text=f"PDF: {filepath}",
        )
        if result and result.get("confidence", 0) >= CONFIDENCE_THRESHOLD:
            flavor = result.get("label", "lattice")
            return flavor, result["confidence"]
    except (ImportError, Exception):
        pass
    return None


def _local_classifier_strategy(**kwargs) -> tuple[str, float] | None:
    """Tier 1.5: Local trained classifier from shadow logs.

    Uses the HistGradientBoosting model trained by train_strategy_classifier.py.
    Returns None if model not available or not confident.
    """
    model_path = SKILL_DIR / "strategy_classifier.joblib"
    if not model_path.exists():
        return None
    try:
        from .train_strategy_classifier import predict_strategy
        strategy, confidence = predict_strategy(
            model_path,
            num_tables=kwargs.get("num_tables", 0),
            accuracy=kwargs.get("accuracy", 0),
            elapsed_seconds=kwargs.get("elapsed_seconds", 0),
            confidence=kwargs.get("confidence", 0),
        )
        if confidence >= CONFIDENCE_THRESHOLD:
            return strategy, confidence
    except Exception:
        pass
    return None


def get_fallback(strategy: str) -> list[str]:
    """Get ordered fallback strategies."""
    return FALLBACK_ORDER.get(strategy, ["stream", "lattice"])


class StrategyRouter:
    """Strategy router that selects the best parser for each page.

    Tracks strategy history per PDF.
    """

    def __init__(self):
        self._history: list[dict] = []

    def pick_strategy(self, pdf_path: str, page_num: int, **kwargs) -> str:
        """Select best parser strategy for a page.

        Returns the strategy name: 'lattice', 'stream', 'network', or 'hybrid'.
        """
        strategy, confidence = select_strategy(pdf_path, page_num, **kwargs)
        self._history.append({
            "pdf_path": pdf_path,
            "page_num": page_num,
            "strategy": strategy,
            "confidence": confidence,
        })
        return strategy

    def route_strategy(self, pdf_path: str, page_num: int, **kwargs) -> str:
        """Alias for pick_strategy."""
        return self.pick_strategy(pdf_path, page_num, **kwargs)

    @property
    def history(self) -> list[dict]:
        return list(self._history)


# ---------------------------------------------------------------------------
# Strategy Memory: remember best strategy per PDF domain/directory
# ---------------------------------------------------------------------------

def _pdf_domain(filepath: str) -> str:
    """Extract a domain key from a PDF path for strategy memory lookup.

    Groups PDFs by parent directory name, which tends to correlate with
    document source/type (e.g. "financial_reports", "medical_forms").
    """
    p = Path(filepath).resolve()
    return p.parent.name or "unknown"


def load_strategy_memory() -> dict:
    """Load strategy memory from disk."""
    if STRATEGY_MEMORY_PATH.exists():
        try:
            return json.loads(STRATEGY_MEMORY_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_strategy_memory(memory: dict) -> None:
    """Save strategy memory to disk."""
    try:
        STRATEGY_MEMORY_PATH.write_text(json.dumps(memory, indent=2))
    except OSError:
        pass


def remember_strategy(filepath: str, strategy: str, accuracy: float, params: dict | None = None) -> None:
    """Record that a strategy achieved a given accuracy for this PDF domain.

    Only updates if the new accuracy beats the stored best.
    """
    domain = _pdf_domain(filepath)
    memory = load_strategy_memory()
    entry = memory.get(domain, {})
    stored_accuracy = entry.get("accuracy", 0.0)

    if accuracy > stored_accuracy:
        memory[domain] = {
            "strategy": strategy,
            "accuracy": round(accuracy, 2),
            "params": params or {},
            "filepath_sample": os.path.basename(filepath),
        }
        save_strategy_memory(memory)


def recall_strategy(filepath: str) -> tuple[str, dict] | None:
    """Look up remembered best strategy for this PDF domain.

    Returns (strategy_name, params) or None if no memory exists.
    """
    domain = _pdf_domain(filepath)
    memory = load_strategy_memory()
    entry = memory.get(domain)
    if entry and entry.get("accuracy", 0) >= 70:
        return entry["strategy"], entry.get("params", {})
    return None
