#!/usr/bin/env python3
"""
Stratified Quality Sampling for Ground Truth Validation

Samples a small subset from each collection and presents them for
manual verification, calculating overall quality estimate.
"""
import json
import random
from pathlib import Path
from typing import Dict, List, Any


def stratified_sample(
    ground_truth_file: Path,
    samples_per_collection: int = 3,
    seed: int = 42,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Sample cases stratified by collection.

    Args:
        ground_truth_file: Path to ground truth JSON
        samples_per_collection: Number of samples per collection
        seed: Random seed

    Returns:
        Dict mapping collection -> list of sampled cases
    """
    random.seed(seed)

    data = json.loads(ground_truth_file.read_text())
    cases = data.get("cases", [])

    # Group by collection
    by_collection = {}
    for case in cases:
        collection = case.get("metadata", {}).get("collection", "Unknown")
        if collection not in by_collection:
            by_collection[collection] = []
        by_collection[collection].append(case)

    # Sample from each collection
    sampled = {}
    for collection, collection_cases in by_collection.items():
        random.shuffle(collection_cases)
        sampled[collection] = collection_cases[:samples_per_collection]

    return sampled


def format_for_review(sampled: Dict[str, List[Dict[str, Any]]]) -> str:
    """Format sampled cases for human review."""
    lines = ["# Quality Sampling Review\n"]
    lines.append("Review each case and mark as CORRECT or INCORRECT.\n")

    total = 0
    for collection, cases in sampled.items():
        lines.append(f"\n## {collection} ({len(cases)} samples)\n")

        for case in cases:
            total += 1
            case_id = case.get("id", "?")
            name = case.get("input", {}).get("name", "?")
            desc = case.get("input", {}).get("description", "?")[:200]
            expected = case.get("expected", {})
            conceptual = expected.get("conceptual", [])
            tactical = expected.get("tactical", [])
            confidence = case.get("metadata", {}).get("llm_confidence", 0)

            lines.append(f"### {case_id}: {name}")
            lines.append(f"**Description:** {desc}...")
            lines.append(f"**Predicted:** C={conceptual} T={tactical} (conf={confidence:.2f})")
            lines.append(f"**Correct?** [ ] Yes  [ ] No")
            lines.append(f"**Notes:** _________________")
            lines.append("")

    lines.append(f"\n---\nTotal samples: {total}")
    lines.append("Quality Score = (Correct / Total) * 100%")

    return "\n".join(lines)


def calculate_quality_estimate(
    sampled: Dict[str, List[Dict[str, Any]]],
    correct_counts: Dict[str, int],
) -> Dict[str, Any]:
    """
    Calculate quality estimate from review results.

    Args:
        sampled: Sampled cases by collection
        correct_counts: Number correct per collection

    Returns:
        Quality metrics
    """
    total_sampled = sum(len(cases) for cases in sampled.values())
    total_correct = sum(correct_counts.values())

    overall_quality = total_correct / total_sampled if total_sampled > 0 else 0

    per_collection = {}
    for collection, cases in sampled.items():
        correct = correct_counts.get(collection, 0)
        quality = correct / len(cases) if cases else 0
        per_collection[collection] = {
            "sampled": len(cases),
            "correct": correct,
            "quality": quality,
        }

    return {
        "overall_quality": overall_quality,
        "total_sampled": total_sampled,
        "total_correct": total_correct,
        "per_collection": per_collection,
        "confidence_interval_95": f"{overall_quality:.1%} +/- {1.96 * (overall_quality * (1-overall_quality) / total_sampled) ** 0.5:.1%}",
    }


if __name__ == "__main__":
    import sys

    skill_dir = Path(__file__).parent
    gt_file = skill_dir / "ground_truth" / "taxonomy_llm.json"

    if not gt_file.exists():
        print(f"Ground truth not found: {gt_file}")
        sys.exit(1)

    # Sample 3 cases from each collection
    sampled = stratified_sample(gt_file, samples_per_collection=3)

    # Output review document
    review_doc = format_for_review(sampled)
    print(review_doc)

    # Also save to file
    review_file = skill_dir / "ground_truth" / "quality_review.md"
    review_file.write_text(review_doc)
    print(f"\nReview document saved to: {review_file}")
