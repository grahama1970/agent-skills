#!/usr/bin/env python3
"""Tier 0 resolver eval harness — 50 hand-labeled examples.

Measures accuracy, precision, recall, F1 of the deterministic BM25+token resolver.

Usage:
    python eval_resolver.py
    python eval_resolver.py --verbose
"""

import json
import time
from pathlib import Path
from typing import Any

import typer
from loguru import logger

from resolver import resolve_action

app = typer.Typer()

# ── Ground truth: 50 (input, expected_action, should_resolve) triples ──

GROUND_TRUTH: list[tuple[str, str | None, bool]] = [
    # === Direct commands (30) — should resolve to correct action ===
    ("approve this entry", "APPROVE_ENTRY", True),
    ("reject the selected document", "REJECT_ENTRY", True),
    ("re-extract this PDF", "REEXTRACT_ENTRY", True),
    ("run convergence on this document", "CONVERGE_ENTRY", True),
    ("diagnose this entry", "DIAGNOSE_ENTRY", True),
    ("filter by low confidence", "FILTER_QUARANTINE", True),
    ("zoom in", "ZOOM_IN", True),
    ("zoom out", "ZOOM_OUT", True),
    ("select this node", "SELECT_NODE", True),
    ("expand the graph", "EXPAND", True),
    ("dismiss this node", "DISMISS_NODE", True),
    ("focus on this cluster", "FOCUS_CLUSTER", True),
    ("approve", "APPROVE_ENTRY", True),
    ("reject", "REJECT_ENTRY", True),
    ("converge", "CONVERGE_ENTRY", True),
    ("diagnose", "DIAGNOSE_ENTRY", True),
    ("re-extract", "REEXTRACT_ENTRY", True),
    ("accept this entry", "APPROVE_ENTRY", True),
    ("decline this document", "REJECT_ENTRY", True),
    ("run re-extraction", "REEXTRACT_ENTRY", True),
    ("please approve this", "APPROVE_ENTRY", True),
    ("can you reject this entry", "REJECT_ENTRY", True),
    ("this looks good, approve it", "APPROVE_ENTRY", True),
    ("zoom in on the graph", "ZOOM_IN", True),
    ("zoom out please", "ZOOM_OUT", True),
    ("filter quarantine entries", "FILTER_QUARANTINE", True),
    ("select the node", "SELECT_NODE", True),
    ("expand this", "EXPAND", True),
    ("focus cluster", "FOCUS_CLUSTER", True),
    ("dismiss node", "DISMISS_NODE", True),

    # === Ambiguous commands (5) — should NOT resolve ===
    ("click that button", None, False),
    ("do the thing", None, False),
    ("select it", None, False),
    ("make it work", None, False),
    ("fix this", None, False),

    # === Out of scope (5) — should NOT resolve ===
    ("what is the weather today", None, False),
    ("tell me a joke", None, False),
    ("how tall is the Eiffel tower", None, False),
    ("what time is it", None, False),
    ("translate hello to French", None, False),

    # === Compound commands (5) — should resolve primary action ===
    ("approve and go to next", "APPROVE_ENTRY", True),
    ("reject this and move on", "REJECT_ENTRY", True),
    ("zoom in and select the node", "ZOOM_IN", True),
    ("filter and approve all", "FILTER_QUARANTINE", True),
    ("diagnose then re-extract", "DIAGNOSE_ENTRY", True),

    # === Abbreviated (5) — should resolve ===
    ("ok approve", "APPROVE_ENTRY", True),
    ("nah reject", "REJECT_ENTRY", True),
    ("redo extract", "REEXTRACT_ENTRY", True),
    ("conv", "CONVERGE_ENTRY", True),
    ("diag", "DIAGNOSE_ENTRY", True),
]


def evaluate(verbose: bool = False) -> dict[str, Any]:
    """Run evaluation and return metrics."""
    tp = fp = fn = tn = 0
    correct_action = 0
    total_resolved_correctly = 0
    total_latency = 0.0
    results: list[dict] = []

    for text, expected_action, should_resolve in GROUND_TRUTH:
        start = time.time()
        result = resolve_action(text)
        latency = time.time() - start
        total_latency += latency

        resolved = result["resolved"]
        actual_action = result.get("action")

        if should_resolve:
            if resolved:
                tp += 1
                if actual_action == expected_action:
                    correct_action += 1
                    total_resolved_correctly += 1
                    status = "CORRECT"
                else:
                    status = f"WRONG_ACTION (got {actual_action}, expected {expected_action})"
            else:
                fn += 1
                status = f"MISSED (expected {expected_action})"
        else:
            if resolved:
                fp += 1
                status = f"FALSE_POS (resolved to {actual_action})"
            else:
                tn += 1
                status = "CORRECT_REJECT"

        entry = {
            "input": text,
            "expected": expected_action,
            "should_resolve": should_resolve,
            "resolved": resolved,
            "actual_action": actual_action,
            "confidence": result.get("confidence", 0),
            "method": result.get("method"),
            "status": status,
            "latency_ms": round(latency * 1000, 1),
        }
        results.append(entry)

        if verbose:
            marker = "✓" if "CORRECT" in status else "✗"
            print(f"  {marker} \"{text}\" → {status} ({latency*1000:.0f}ms)")

    total = len(GROUND_TRUTH)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    accuracy = (correct_action + tn) / total
    resolution_accuracy = correct_action / tp if tp > 0 else 0

    metrics = {
        "total": total,
        "true_positive": tp,
        "false_positive": fp,
        "true_negative": tn,
        "false_negative": fn,
        "correct_action": correct_action,
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "resolution_accuracy": round(resolution_accuracy, 4),
        "mean_latency_ms": round(total_latency / total * 1000, 1),
        "results": results,
    }
    return metrics


@app.command()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    output: str = typer.Option("", "--output", "-o", help="Write results JSON to file"),
) -> None:
    """Evaluate Tier 0 resolver on 50 hand-labeled examples."""
    print(f"Evaluating resolver on {len(GROUND_TRUTH)} examples...\n")

    metrics = evaluate(verbose=verbose)

    print(f"\n{'='*50}")
    print(f"  Accuracy:            {metrics['accuracy']:.1%}")
    print(f"  Precision:           {metrics['precision']:.1%}")
    print(f"  Recall:              {metrics['recall']:.1%}")
    print(f"  F1:                  {metrics['f1']:.1%}")
    print(f"  Resolution accuracy: {metrics['resolution_accuracy']:.1%}")
    print(f"  Mean latency:        {metrics['mean_latency_ms']:.0f}ms")
    print(f"{'='*50}")
    print(f"  TP={metrics['true_positive']} FP={metrics['false_positive']} "
          f"TN={metrics['true_negative']} FN={metrics['false_negative']}")
    print(f"  Correct action: {metrics['correct_action']}/{metrics['true_positive']}")

    out_path = output or str(Path(__file__).parent / "eval_results.json")
    with open(out_path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"\n  Results written to {out_path}")


if __name__ == "__main__":
    app()
