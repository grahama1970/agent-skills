#!/usr/bin/env python3
"""Convert validated review-question JSON files into /assistant JSONL training data.

Reads question JSON files (from generate command), assigns composite labels
based on persona + query_type heuristic, and writes JSONL for train_classifiers.py.

Usage:
    python label_intent.py results/questions_brandon_f36.json [...]
    python label_intent.py --all  # label all results/questions_*.json files
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"
OUTPUT_DIR = Path.home() / ".pi" / "assistant" / "training_data" / "5ft-intent"

# Scope mapping: persona short name -> memory-daemon scope
SCOPE_MAP = {
    "brandon": "brandon_bailey",
    "jennifer": "jennifer_cheung",
    "noah": "noah_evans",
    "margaret": "margaret_chen",
    "paul": "paul_nakamura",
    "embry": "embry",
}

# Keywords that signal analytical queries (want charts/visualizations)
_ANALYTICAL_RE = re.compile(
    r"\b(show me|chart|graph|distribution|compare|trend|breakdown|break down|"
    r"how many|coverage|plot|visuali[sz]e|count|histogram|pie|bar chart|"
    r"top \d+|by family|by category|percentage|ratio|summary stats|"
    r"impact analysis|correlation|across|between .+ and|overlap)\b",
    re.IGNORECASE,
)

# Keywords that signal status queries
_STATUS_RE = re.compile(
    r"\b(status|health|daemon|service|uptime|running|connectivity)\b",
    re.IGNORECASE,
)


def classify_query_type(question: str) -> str:
    """Heuristic query_type from question text."""
    if _STATUS_RE.search(question):
        return "status"
    if _ANALYTICAL_RE.search(question):
        return "analytical"
    return "knowledge"


def label_file(path: Path) -> list[dict]:
    """Convert a questions JSON file to labeled training entries.

    Handles two formats:
    - Generator format: {persona: "brandon", ...} — scope derived from SCOPE_MAP
    - Pre-labeled format: {expected_scope: "brandon_bailey", expected_type: "knowledge", ...}
    """
    data = json.loads(path.read_text())
    entries = []
    for item in data:
        question = item.get("question", "")
        if not question:
            continue

        # Pre-labeled format (expected_scope/expected_type already present)
        if "expected_scope" in item:
            scope = item["expected_scope"]
            query_type = item.get("expected_type", classify_query_type(question))
        elif "persona" in item:
            persona = item["persona"]
            scope = SCOPE_MAP.get(persona, persona)
            query_type = classify_query_type(question)
        else:
            # Try to infer persona from filename
            continue

        composite_label = f"{scope}:{query_type}"

        entries.append({
            "input": {"text": question},
            "output": {"prediction": composite_label},
            "teacher_grade": composite_label,
            "source": "review-question-f36",
        })
    return entries


def main():
    args = sys.argv[1:]
    if not args or "--all" in args:
        files = sorted(RESULTS_DIR.glob("questions_*.json"))
        if not files:
            print(f"No question files found in {RESULTS_DIR}")
            sys.exit(1)
    else:
        files = [Path(a) for a in args if Path(a).exists()]

    all_entries = []
    for f in files:
        entries = label_file(f)
        print(f"  {f.name}: {len(entries)} entries")
        all_entries.extend(entries)

    if not all_entries:
        print("No entries generated — check question files")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "labels_f36.jsonl"
    with open(out_path, "w") as fh:
        for entry in all_entries:
            fh.write(json.dumps(entry) + "\n")

    # Summary
    from collections import Counter
    label_counts = Counter(e["teacher_grade"] for e in all_entries)
    print(f"\nWrote {len(all_entries)} labeled entries to {out_path}")
    print("Label distribution:")
    for label, count in sorted(label_counts.items()):
        print(f"  {label}: {count}")


if __name__ == "__main__":
    main()
