"""Data loading and feature preparation for create-regressor.

Purpose:
- Load JSONL or CSV tabular data.
- Separate features from target column.
- Handle missing values, boolean conversion, categorical encoding hints.

Inputs:
- File path (JSONL or CSV).
- Target column name.

Outputs:
- List of feature dicts + list of target values.

Failure modes:
- File not found: FileNotFoundError raised.
- Target column missing: ValueError raised.
- Empty file: ValueError raised.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from loguru import logger


def load_data(
    path: Path,
    target: str,
) -> tuple[list[dict], list[float]]:
    """Load tabular data from JSONL or CSV, returning (feature_dicts, targets).

    The target column is removed from feature dicts.
    Boolean values are converted to 0/1.
    Missing numeric values become 0, missing strings become "unknown".
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        rows = _load_jsonl(path)
    elif suffix in (".csv", ".tsv"):
        rows = _load_csv(path, delimiter="\t" if suffix == ".tsv" else ",")
    elif suffix == ".json":
        rows = _load_json(path)
    else:
        raise ValueError(f"Unsupported file format: {suffix}. Use .jsonl, .json, or .csv")

    if not rows:
        raise ValueError(f"No data rows loaded from {path}")

    # Validate target column exists
    if target not in rows[0]:
        available = list(rows[0].keys())
        raise ValueError(
            f"Target column '{target}' not found. Available: {available}"
        )

    feature_dicts: list[dict] = []
    targets: list[float] = []
    skipped = 0

    for row in rows:
        target_val = row.get(target)
        if target_val is None or target_val == "":
            skipped += 1
            continue

        try:
            t = float(target_val)
        except (ValueError, TypeError):
            skipped += 1
            continue

        targets.append(t)

        # Build feature dict without target
        fd: dict[str, Any] = {}
        for k, v in row.items():
            if k == target:
                continue
            fd[k] = _coerce_value(v)
        feature_dicts.append(fd)

    if skipped:
        logger.warning(f"Skipped {skipped} rows with invalid/missing target '{target}'")

    logger.info(f"Loaded {len(feature_dicts)} samples from {path} (target='{target}')")
    return feature_dicts, targets


def describe_data(path: Path) -> dict:
    """Describe schema and statistics of a data file."""
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix == ".jsonl":
        rows = _load_jsonl(path)
    elif suffix in (".csv", ".tsv"):
        rows = _load_csv(path, delimiter="\t" if suffix == ".tsv" else ",")
    elif suffix == ".json":
        rows = _load_json(path)
    else:
        raise ValueError(f"Unsupported: {suffix}")

    if not rows:
        return {"rows": 0, "columns": []}

    # Analyze columns
    columns = []
    all_keys = set()
    for row in rows:
        all_keys.update(row.keys())

    for key in sorted(all_keys):
        values = [row.get(key) for row in rows if row.get(key) is not None]
        col_info: dict[str, Any] = {"name": key, "non_null": len(values)}

        # Detect type
        numeric_count = 0
        for v in values[:100]:
            try:
                float(v)
                numeric_count += 1
            except (ValueError, TypeError):
                pass

        if numeric_count > len(values[:100]) * 0.8:
            col_info["type"] = "numeric"
            nums = [float(v) for v in values if _is_numeric(v)]
            if nums:
                col_info["min"] = min(nums)
                col_info["max"] = max(nums)
                col_info["mean"] = sum(nums) / len(nums)
        else:
            unique = set(str(v) for v in values[:1000])
            col_info["type"] = "categorical"
            col_info["unique"] = len(unique)
            if len(unique) <= 20:
                col_info["values"] = sorted(unique)[:20]

        columns.append(col_info)

    return {"rows": len(rows), "columns": columns}


def split_data(
    feature_dicts: list[dict],
    targets: list[float],
    test_ratio: float = 0.2,
    seed: int = 42,
) -> tuple[list[dict], list[float], list[dict], list[float]]:
    """Split data into train/test sets."""
    import random

    indices = list(range(len(feature_dicts)))
    rng = random.Random(seed)
    rng.shuffle(indices)

    split_idx = int(len(indices) * (1 - test_ratio))
    train_idx = indices[:split_idx]
    test_idx = indices[split_idx:]

    train_fd = [feature_dicts[i] for i in train_idx]
    train_t = [targets[i] for i in train_idx]
    test_fd = [feature_dicts[i] for i in test_idx]
    test_t = [targets[i] for i in test_idx]

    return train_fd, train_t, test_fd, test_t


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _coerce_value(v: Any) -> Any:
    """Coerce a raw value to a model-friendly type."""
    if isinstance(v, bool):
        return int(v)
    if v is None:
        return 0
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        v_stripped = v.strip()
        if not v_stripped:
            return "unknown"
        # Try numeric
        try:
            return float(v_stripped)
        except ValueError:
            # Categorical string — DictVectorizer handles one-hot
            return v_stripped
    return v


def _is_numeric(v: Any) -> bool:
    try:
        float(v)
        return True
    except (ValueError, TypeError):
        return False


def _load_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _load_json(path: Path) -> list[dict]:
    data = json.loads(path.read_text())
    if isinstance(data, list):
        return data
    raise ValueError(f"JSON file must contain a list of objects, got {type(data).__name__}")


def _load_csv(path: Path, delimiter: str = ",") -> list[dict]:
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        for row in reader:
            rows.append(dict(row))
    return rows
