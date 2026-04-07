#!/usr/bin/env python3
"""Profile a classifier dataset — multi-modality: text, vision, tabular.

Usage:
    python profile_dataset.py /path/to/samples.jsonl [--modality text]
    python profile_dataset.py /path/to/dataset.parquet [--modality vision]
    python profile_dataset.py /path/to/data-dir [--modality vision]

Outputs JSON to stdout. Modality auto-detected from data if not specified.
"""
import json
import os
import sys
from collections import Counter
from pathlib import Path


def _stats(values: list[float | int]) -> dict:
    """Min/max/mean/median for a list of numbers."""
    if not values:
        return {"min": 0, "max": 0, "mean": 0, "median": 0}
    s = sorted(values)
    n = len(s)
    return {
        "min": s[0],
        "max": s[-1],
        "mean": round(sum(s) / n, 1),
        "median": s[n // 2],
    }


def _common_quality(classes: list[str], splits: list[str]) -> dict:
    """Quality metrics shared across all modalities."""
    return {
        "splits": dict(Counter(splits)),
        "classCounts": dict(Counter(classes)),
    }


# ── Text profiling ──────────────────────────────────────────────────

def profile_text(rows: list[dict]) -> dict:
    texts = [r.get("text", "") or "" for r in rows]
    classes = [r.get("class", r.get("className", "")) or "" for r in rows]
    splits = [r.get("split", "train") or "train" for r in rows]

    word_counts = [len(t.split()) for t in texts]
    char_counts = [len(t) for t in texts]

    per_class_wc: dict[str, list[int]] = {}
    for cls, text in zip(classes, texts):
        per_class_wc.setdefault(cls, []).append(len(text.split()))

    per_class = {}
    for cls, wc_list in per_class_wc.items():
        st = _stats(wc_list)
        per_class[cls] = {
            "count": len(wc_list),
            "min_words": st["min"], "max_words": st["max"],
            "mean_words": st["mean"], "median_words": st["median"],
        }

    all_words = " ".join(texts).lower().split()
    vocab_size = len(set(all_words))
    top_words = [{"word": w, "count": c} for w, c in Counter(all_words).most_common(20)]

    empty_texts = sum(1 for t in texts if not t.strip())
    short_texts = sum(1 for wc in word_counts if wc < 5)
    duplicate_texts = len(texts) - len(set(texts))

    text_label_map: dict[str, set] = {}
    for text, cls in zip(texts, classes):
        text_label_map.setdefault(text.strip().lower(), set()).add(cls)
    conflicting_labels = sum(1 for labels in text_label_map.values() if len(labels) > 1)

    return {
        "modality": "text",
        "total": len(rows),
        "textStats": {
            "charMin": _stats(char_counts)["min"], "charMax": _stats(char_counts)["max"],
            "charMean": _stats(char_counts)["mean"], "charMedian": _stats(char_counts)["median"],
            "wordMin": _stats(word_counts)["min"], "wordMax": _stats(word_counts)["max"],
            "wordMean": _stats(word_counts)["mean"], "wordMedian": _stats(word_counts)["median"],
        },
        "vocabSize": vocab_size,
        "topWords": top_words,
        "perClass": per_class,
        **_common_quality(classes, splits),
        "quality": {
            "emptyTexts": empty_texts,
            "shortTexts": short_texts,
            "duplicateTexts": duplicate_texts,
            "conflictingLabels": conflicting_labels,
        },
    }


# ── Vision profiling ────────────────────────────────────────────────

def profile_vision_dir(data_dir: str) -> dict:
    """Profile an image directory tree: data_dir/{class_name}/*.{jpg,png,...}"""
    from PIL import Image

    data_path = Path(data_dir)
    IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
    classes_list: list[str] = []
    widths: list[int] = []
    heights: list[int] = []
    file_sizes: list[int] = []
    channels: list[int] = []
    corrupt_count = 0
    total = 0

    per_class_counts: dict[str, int] = {}

    for class_dir in sorted(data_path.iterdir()):
        if not class_dir.is_dir():
            continue
        cls_name = class_dir.name
        count = 0
        for img_file in class_dir.iterdir():
            if img_file.suffix.lower() not in IMAGE_EXTS:
                continue
            total += 1
            count += 1
            classes_list.append(cls_name)
            file_sizes.append(img_file.stat().st_size)
            try:
                with Image.open(img_file) as img:
                    w, h = img.size
                    widths.append(w)
                    heights.append(h)
                    mode_channels = {"L": 1, "RGB": 3, "RGBA": 4, "P": 1, "CMYK": 4}
                    channels.append(mode_channels.get(img.mode, 3))
            except Exception:
                corrupt_count += 1
        per_class_counts[cls_name] = count

    aspect_ratios = [w / h if h > 0 else 0 for w, h in zip(widths, heights)]

    return {
        "modality": "vision",
        "total": total,
        "imageStats": {
            "width": _stats(widths),
            "height": _stats(heights),
            "fileSize": _stats(file_sizes),
            "aspectRatio": _stats(aspect_ratios),
            "channels": dict(Counter(channels)),
        },
        "perClass": {cls: {"count": c} for cls, c in per_class_counts.items()},
        **_common_quality(classes_list, ["train"] * total),
        "quality": {
            "corruptImages": corrupt_count,
            "totalImages": total,
            "uniqueDimensions": len(set(zip(widths, heights))),
            "needsResize": len(set(zip(widths, heights))) > 1,
        },
    }


def profile_vision_jsonl(rows: list[dict]) -> dict:
    """Profile vision dataset from JSONL metadata (no image reading)."""
    classes = [r.get("class", r.get("className", "")) or "" for r in rows]
    splits = [r.get("split", "train") or "train" for r in rows]
    paths = [r.get("path", "") or "" for r in rows]

    per_class: dict[str, int] = {}
    for cls in classes:
        per_class[cls] = per_class.get(cls, 0) + 1

    duplicate_paths = len(paths) - len(set(paths))

    return {
        "modality": "vision",
        "total": len(rows),
        "imageStats": None,
        "perClass": {cls: {"count": c} for cls, c in per_class.items()},
        **_common_quality(classes, splits),
        "quality": {
            "duplicatePaths": duplicate_paths,
            "totalImages": len(rows),
            "note": "Image stats require scanning image files directly",
        },
    }


# ── Tabular profiling ───────────────────────────────────────────────

def profile_tabular(rows: list[dict]) -> dict:
    """Profile tabular dataset — column types, nulls, cardinality."""
    classes = [r.get("class", r.get("className", r.get("label", ""))) or "" for r in rows]
    splits = [r.get("split", "train") or "train" for r in rows]

    # Detect feature columns (exclude metadata)
    skip_keys = {"class", "className", "label", "split", "filename", "path", "id"}
    all_keys = set()
    for r in rows:
        all_keys.update(r.keys())
    feature_cols = sorted(all_keys - skip_keys)

    columns: list[dict] = []
    for col in feature_cols:
        values = [r.get(col) for r in rows]
        non_null = [v for v in values if v is not None and v != ""]
        nulls = len(values) - len(non_null)

        # Type detection
        numeric_count = sum(1 for v in non_null if isinstance(v, (int, float)))
        is_numeric = numeric_count > len(non_null) * 0.8

        col_info: dict = {
            "name": col,
            "dtype": "numeric" if is_numeric else "categorical",
            "nulls": nulls,
            "nullPct": round(nulls / len(values) * 100, 1) if values else 0,
            "unique": len(set(str(v) for v in non_null)),
        }

        if is_numeric:
            nums = [float(v) for v in non_null if isinstance(v, (int, float))]
            col_info["stats"] = _stats(nums)
        else:
            str_vals = [str(v) for v in non_null]
            top = Counter(str_vals).most_common(5)
            col_info["topValues"] = [{"value": v, "count": c} for v, c in top]

        columns.append(col_info)

    return {
        "modality": "tabular",
        "total": len(rows),
        "featureCount": len(feature_cols),
        "columns": columns,
        "perClass": dict(Counter(classes)),
        **_common_quality(classes, splits),
        "quality": {
            "totalNulls": sum(c["nulls"] for c in columns),
            "columnsWithNulls": sum(1 for c in columns if c["nulls"] > 0),
            "highCardinality": [c["name"] for c in columns if c["unique"] > len(rows) * 0.9],
            "constantColumns": [c["name"] for c in columns if c["unique"] <= 1],
        },
    }


# ── Entry point ─────────────────────────────────────────────────────

def load_rows(path: str) -> list[dict]:
    if path.endswith(".parquet"):
        try:
            import polars as pl
            return pl.read_parquet(path).to_dicts()
        except ImportError:
            return []
    elif path.endswith(".jsonl"):
        rows = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return rows
    return []


def detect_modality(rows: list[dict], path: str) -> str:
    """Auto-detect modality from data structure."""
    if not rows:
        # Check if path is a directory with image subdirs
        p = Path(path)
        if p.is_dir() and any(f.suffix.lower() in {".jpg", ".png", ".jpeg"} for f in p.rglob("*") if f.is_file()):
            return "vision"
        return "text"

    sample = rows[0]
    if "text" in sample:
        return "text"
    if "image" in sample or "path" in sample:
        # Check if paths look like images
        path_val = sample.get("path", "") or sample.get("image", "") or ""
        if any(path_val.lower().endswith(ext) for ext in (".jpg", ".png", ".jpeg", ".bmp")):
            return "vision"

    # If many numeric columns, likely tabular
    skip = {"class", "className", "label", "split", "filename", "path", "id"}
    feature_vals = [v for k, v in sample.items() if k not in skip]
    numeric = sum(1 for v in feature_vals if isinstance(v, (int, float)))
    if numeric > len(feature_vals) * 0.5:
        return "tabular"

    return "text"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "usage: profile_dataset.py <path> [--modality text|vision|tabular]"}))
        sys.exit(1)

    path = sys.argv[1]
    modality = None
    if "--modality" in sys.argv:
        idx = sys.argv.index("--modality")
        if idx + 1 < len(sys.argv):
            modality = sys.argv[idx + 1]

    p = Path(path)
    if not p.exists():
        print(json.dumps({"error": f"file not found: {path}"}))
        sys.exit(1)

    # Vision directory mode
    if p.is_dir():
        modality = modality or "vision"
        if modality == "vision":
            try:
                result = profile_vision_dir(path)
            except ImportError:
                result = {"error": "Pillow not installed — needed for image profiling", "modality": "vision"}
        else:
            result = {"error": f"directory mode only supports vision, got {modality}"}
        print(json.dumps(result))
        sys.exit(0)

    # File mode
    rows = load_rows(path)
    if not rows:
        print(json.dumps({"error": "no rows loaded", "total": 0}))
        sys.exit(0)

    modality = modality or detect_modality(rows, path)

    if modality == "text":
        result = profile_text(rows)
    elif modality == "vision":
        result = profile_vision_jsonl(rows)
    elif modality == "tabular":
        result = profile_tabular(rows)
    else:
        result = profile_text(rows)  # fallback

    print(json.dumps(result))
