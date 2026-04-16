#!/usr/bin/env python3
"""Enrich text training data with grader signal features for tabular classification.

Reads merged_evidence_training_v2.jsonl (text + label), calls the evidence grader's
signal collection functions (entity extraction + QRA recall — fast ArangoDB lookups),
and outputs tabular JSONL compatible with /classifier-lab's tabular-benchmark.

Output format:
  {"features": {"has_valid_control": 1.0, "fabricated_id_count": 0, ...}, "label": "Pass"}

The insight: TF-IDF on raw text can't distinguish "SV-SP-1" (valid) from "SV-ZZ-99"
(fabricated). But the evidence grader's entity extraction + ArangoDB validation can,
in ~200ms. Since the whole point of the classifier is fast validation, augmenting
with these cheap DB calls is the right approach.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add the sparta-stress-test package to path
SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from sparta_stress_test.evidence_grader import (
    _collect_entities,
    _collect_recall,
    _group_by_technique,
    MIN_QRA_COVERAGE,
)

INPUT = SKILL_DIR / "results" / "merged_evidence_training_v2.jsonl"
OUTPUT = SKILL_DIR / "results" / "tabular_evidence_training.jsonl"


def extract_features(question: str) -> dict[str, float]:
    """Extract grader signal features from a question via ArangoDB lookups."""
    # Entity extraction (~200ms)
    entities = _collect_entities(question)
    controls = []
    fabricated_ids = []
    grounding_ok = False
    if entities:
        grounding_ok = entities.get("grounding_ok", False)
        controls = [
            c.get("id", c) if isinstance(c, dict) else c
            for c in entities.get("controls", [])
        ]
        fabricated_ids = [
            w["term"] for w in entities.get("warnings", [])
            if w.get("category") == "fabricated_id"
        ]

    # QRA recall (~500ms)
    qra_items = _collect_recall(question, extracted_controls=controls)
    technique_groups = _group_by_technique(qra_items)

    # Compute BM25 top score
    bm25_scores = [item.get("score", 0.0) for item in qra_items if isinstance(item.get("score"), (int, float))]
    bm25_top = max(bm25_scores) if bm25_scores else 0.0
    bm25_mean = sum(bm25_scores) / len(bm25_scores) if bm25_scores else 0.0

    return {
        "has_valid_control": 1.0 if controls else 0.0,
        "n_valid_controls": float(len(controls)),
        "fabricated_id_count": float(len(fabricated_ids)),
        "grounding_ok": 1.0 if grounding_ok else 0.0,
        "qra_count": float(len(qra_items)),
        "qra_sufficient": 1.0 if len(qra_items) >= MIN_QRA_COVERAGE else 0.0,
        "technique_group_count": float(len(technique_groups)),
        "technique_bridge": 1.0 if len(technique_groups) >= 1 else 0.0,
        "bm25_top_score": float(bm25_top),
        "bm25_mean_score": float(bm25_mean),
    }


def main():
    samples = []
    with open(INPUT) as f:
        for line in f:
            item = json.loads(line)
            samples.append(item)

    print(f"Enriching {len(samples)} samples with grader signal features...")

    enriched = []
    for i, sample in enumerate(samples):
        text = sample["text"]
        label = sample["label"]
        # Merge Fail → Absurd (same as train_evidence_classifier.py)
        if label == "Fail":
            label = "Absurd"

        features = extract_features(text)

        enriched.append({"features": features, "label": label, "text": text})

        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{len(samples)} done")

    # Write tabular JSONL
    with open(OUTPUT, "w") as f:
        for item in enriched:
            f.write(json.dumps({"features": item["features"], "label": item["label"]}) + "\n")

    print(f"\nWrote {len(enriched)} samples to {OUTPUT}")

    # Print feature distribution summary
    from collections import Counter
    label_counts = Counter(item["label"] for item in enriched)
    print(f"Label distribution: {dict(label_counts)}")

    # Print feature stats
    import statistics
    for feat in enriched[0]["features"]:
        vals = [item["features"][feat] for item in enriched]
        print(f"  {feat}: min={min(vals):.1f} max={max(vals):.1f} mean={statistics.mean(vals):.2f}")

    # Also write a version with text for hybrid classifiers
    hybrid_out = SKILL_DIR / "results" / "hybrid_evidence_training.jsonl"
    with open(hybrid_out, "w") as f:
        for item in enriched:
            f.write(json.dumps(item) + "\n")
    print(f"Wrote hybrid (features+text) to {hybrid_out}")


if __name__ == "__main__":
    main()
