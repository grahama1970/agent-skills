#!/usr/bin/env python3
"""
Generate synthetic training data for the viz-type-selector classifier.

For each implemented VizType in D3_VIZ_CATALOG, generates 50-100 synthetic
data profiles with realistic feature vectors and natural-language queries.
Also generates ~200 negative examples (random profiles that don't match
any type well).

Outputs JSONL splits to:
  .pi/skills/assistant/training_data/viz_type_selector/{train,val,test}.jsonl

Usage:
    python generate_viz_training_data.py
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

from loguru import logger

# ---------------------------------------------------------------------------
# Import d3_catalog from create-figure skill
# ---------------------------------------------------------------------------
CREATE_FIGURE_DIR = str(Path(__file__).resolve().parents[2] / "create-figure")
sys.path.insert(0, CREATE_FIGURE_DIR)

from d3_catalog import D3_VIZ_CATALOG, get_implemented_viz_types  # noqa: E402
from d3_catalog_types import DataShape, RenderBackend  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SEED = 42
OUTPUT_DIR = Path(__file__).resolve().parent / "viz_type_selector"
MIN_EXAMPLES_PER_TYPE = 50
MAX_EXAMPLES_PER_TYPE = 100
NUM_NEGATIVE_EXAMPLES = 200

QUERY_PREFIXES = [
    "show me",
    "visualize",
    "plot",
    "display",
    "create a",
    "make a",
    "generate a",
    "draw",
    "graph",
    "chart",
    "I want to see",
    "can you show",
    "help me visualize",
    "render",
    "build a",
]

QUERY_CONNECTORS = [
    "the",
    "a",
    "my",
    "our",
    "this",
    "the following",
]

QUERY_SUFFIXES = [
    "",
    "for the dataset",
    "from the data",
    "please",
    "for this data",
    "over time",
    "by category",
    "across groups",
    "for comparison",
]

# Mapping from DataShape to dominant column type
SHAPE_TO_COL_TYPE: dict[DataShape, str] = {
    DataShape.CATEGORICAL: "categorical",
    DataShape.TIME_SERIES: "datetime",
    DataShape.BIVARIATE: "numeric",
    DataShape.MULTIVARIATE: "numeric",
    DataShape.HIERARCHICAL: "categorical",
    DataShape.NETWORK: "categorical",
    DataShape.FLOW: "categorical",
    DataShape.MATRIX: "numeric",
    DataShape.DISTRIBUTION: "numeric",
    DataShape.GEOGRAPHIC: "numeric",
    DataShape.TABULAR: "mixed",
    DataShape.TEXT: "text",
}


def _has_flag(shapes: list[DataShape], target: DataShape) -> bool:
    return target in shapes


def _derive_col_types(
    shapes: list[DataShape], n_cols: int, rng: random.Random
) -> dict[str, str]:
    """Build a realistic col_types dict from data shapes."""
    col_types: dict[str, str] = {}

    # Determine primary type from the first shape
    primary_type = SHAPE_TO_COL_TYPE.get(shapes[0], "numeric")

    # Assign columns
    for i in range(n_cols):
        if primary_type == "mixed":
            col_types[f"col_{i}"] = rng.choice(
                ["numeric", "categorical", "datetime", "text"]
            )
        elif primary_type == "datetime" and i == 0:
            col_types[f"col_{i}"] = "datetime"
        elif primary_type == "categorical" and i == 0:
            col_types[f"col_{i}"] = "categorical"
        else:
            # Mix in secondary types based on other shapes
            secondary_types = [SHAPE_TO_COL_TYPE.get(s, "numeric") for s in shapes[1:]]
            if secondary_types and rng.random() < 0.4:
                col_types[f"col_{i}"] = rng.choice(secondary_types)
            else:
                col_types[f"col_{i}"] = primary_type

    return col_types


def _generate_query(keywords: list[str], rng: random.Random) -> str:
    """Generate a natural-language query from keywords."""
    prefix = rng.choice(QUERY_PREFIXES)
    connector = rng.choice(QUERY_CONNECTORS)
    suffix = rng.choice(QUERY_SUFFIXES)

    # Pick 2-4 keywords
    n_kw = min(len(keywords), rng.randint(2, 4))
    selected_kw = rng.sample(keywords, n_kw)

    # Sometimes use keywords directly, sometimes wrap them
    if rng.random() < 0.3:
        kw_phrase = " ".join(selected_kw)
    else:
        kw_phrase = " and ".join(
            [" ".join(selected_kw[:-1]), selected_kw[-1]]
            if len(selected_kw) > 1
            else selected_kw
        )

    parts = [prefix, connector, kw_phrase]
    if suffix:
        parts.append(suffix)

    return " ".join(parts)


def generate_positive_examples(rng: random.Random) -> list[dict]:
    """Generate positive examples for all implemented viz types."""
    examples = []
    implemented = get_implemented_viz_types()

    for viz in implemented:
        n_examples = rng.randint(MIN_EXAMPLES_PER_TYPE, MAX_EXAMPLES_PER_TYPE)
        logger.debug(
            "Generating {} examples for viz type '{}'", n_examples, viz.name
        )

        for _ in range(n_examples):
            # Sample n_rows within valid range
            min_rows = viz.min_data_points
            max_rows = viz.max_data_points or 10000
            n_rows = rng.randint(min_rows, max_rows)

            # Sample n_cols within valid range
            min_cols = max(viz.min_dimensions, 1)
            max_cols = viz.max_dimensions or 20
            n_cols = rng.randint(min_cols, max_cols)

            # Derive column types from data shapes
            col_types = _derive_col_types(viz.data_shapes, n_cols, rng)

            # Derive boolean flags from data shapes
            has_time = _has_flag(viz.data_shapes, DataShape.TIME_SERIES)
            has_hierarchy = _has_flag(viz.data_shapes, DataShape.HIERARCHICAL)
            has_geo = _has_flag(viz.data_shapes, DataShape.GEOGRAPHIC)
            has_network = _has_flag(viz.data_shapes, DataShape.NETWORK)

            # Add some noise: occasionally flip a flag
            if rng.random() < 0.05:
                has_time = not has_time
            if rng.random() < 0.05:
                has_hierarchy = not has_hierarchy

            # Generate query from keywords
            if viz.keywords:
                query = _generate_query(viz.keywords, rng)
            else:
                query = rng.choice(QUERY_PREFIXES) + " data"

            # Count numeric and categorical columns
            n_numeric = sum(1 for t in col_types.values() if t == "numeric")
            n_categorical = sum(
                1 for t in col_types.values() if t == "categorical"
            )

            features = {
                "n_rows": n_rows,
                "n_cols": n_cols,
                "n_numeric": n_numeric,
                "n_categorical": n_categorical,
                "has_time": has_time,
                "has_hierarchy": has_hierarchy,
                "has_geo": has_geo,
                "has_network": has_network,
                "query": query,
            }

            examples.append({"features": features, "label": viz.name})

    return examples


def generate_negative_examples(
    rng: random.Random, n: int = NUM_NEGATIVE_EXAMPLES
) -> list[dict]:
    """Generate negative examples -- random profiles that don't match well."""
    examples = []

    for _ in range(n):
        # Random, often mismatched features
        n_rows = rng.choice([0, 1, rng.randint(1, 50000)])
        n_cols = rng.randint(0, 30)
        n_numeric = rng.randint(0, n_cols)
        n_categorical = n_cols - n_numeric

        # Random flags, but bias toward unusual combos
        has_time = rng.random() < 0.2
        has_hierarchy = rng.random() < 0.2
        has_geo = rng.random() < 0.1
        has_network = rng.random() < 0.1

        # Nonsensical or vague queries
        vague_queries = [
            "show me something",
            "I have data",
            "what can I do with this",
            "help",
            "analyze this file",
            "the numbers",
            "just display it",
            "make it pretty",
            "any chart",
            "something useful",
            "idk what to do",
            "process the data",
            "run analysis",
            "give me insights",
            "what does this mean",
            "summarize",
            "overview",
            "report",
            "dashboard please",
            "make a visualization",
        ]
        query = rng.choice(vague_queries)

        features = {
            "n_rows": n_rows,
            "n_cols": n_cols,
            "n_numeric": n_numeric,
            "n_categorical": n_categorical,
            "has_time": has_time,
            "has_hierarchy": has_hierarchy,
            "has_geo": has_geo,
            "has_network": has_network,
            "query": query,
        }

        examples.append({"features": features, "label": "unknown"})

    return examples


def split_data(
    examples: list[dict], rng: random.Random
) -> tuple[list[dict], list[dict], list[dict]]:
    """Split examples into train (80%), val (10%), test (10%)."""
    rng.shuffle(examples)
    n = len(examples)
    train_end = int(n * 0.8)
    val_end = int(n * 0.9)

    return examples[:train_end], examples[train_end:val_end], examples[val_end:]


def write_jsonl(path: Path, examples: list[dict]) -> None:
    """Write examples to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex, separators=(",", ":")) + "\n")
    logger.info("Wrote {} examples to {}", len(examples), path)


def print_stats(
    train: list[dict], val: list[dict], test: list[dict]
) -> None:
    """Print type distribution statistics."""
    all_examples = train + val + test
    total = len(all_examples)

    # Count by label
    label_counts: dict[str, int] = {}
    for ex in all_examples:
        label = ex["label"]
        label_counts[label] = label_counts.get(label, 0) + 1

    print(f"\n{'='*60}")
    print(f"VIZ TYPE SELECTOR TRAINING DATA STATISTICS")
    print(f"{'='*60}")
    print(f"Total examples: {total}")
    print(f"  Train: {len(train)}")
    print(f"  Val:   {len(val)}")
    print(f"  Test:  {len(test)}")
    print(f"\nType distribution ({len(label_counts)} types):")
    print(f"{'Label':<25s} {'Count':>6s} {'Pct':>6s}")
    print(f"{'-'*37}")

    for label, count in sorted(label_counts.items(), key=lambda x: -x[1]):
        pct = count / total * 100
        print(f"  {label:<23s} {count:>6d} {pct:>5.1f}%")

    print(f"\nMinimum requirement check: {total} >= 3000? {'PASS' if total >= 3000 else 'FAIL'}")


def main() -> None:
    rng = random.Random(SEED)
    random.seed(SEED)

    logger.info("D3_VIZ_CATALOG has {} types total", len(D3_VIZ_CATALOG))
    implemented = get_implemented_viz_types()
    logger.info(
        "{} implemented types (backend != NOT_YET)", len(implemented)
    )

    # Generate examples
    logger.info("Generating positive examples...")
    positive = generate_positive_examples(rng)
    logger.info("Generated {} positive examples", len(positive))

    logger.info("Generating {} negative examples...", NUM_NEGATIVE_EXAMPLES)
    negative = generate_negative_examples(rng, NUM_NEGATIVE_EXAMPLES)
    logger.info("Generated {} negative examples", len(negative))

    all_examples = positive + negative
    logger.info("Total examples: {}", len(all_examples))

    # Split
    train, val, test = split_data(all_examples, rng)

    # Write
    write_jsonl(OUTPUT_DIR / "train.jsonl", train)
    write_jsonl(OUTPUT_DIR / "val.jsonl", val)
    write_jsonl(OUTPUT_DIR / "test.jsonl", test)

    # Stats
    print_stats(train, val, test)


if __name__ == "__main__":
    main()
