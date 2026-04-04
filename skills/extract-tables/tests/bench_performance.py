"""Performance benchmarks for native table extraction.

Measures wall time and peak RSS memory for extraction on representative PDFs.
Results are REPORTED, not asserted — this is measurement, not validation.
"""
import json
import os
import sys
import time
import resource

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.python import read_pdf

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

BENCHMARKS = [
    {"name": "simple_bordered", "file": "foo.pdf", "desc": "Simple bordered table (1 page)"},
    {"name": "borderless", "file": "column_span_2.pdf", "desc": "Borderless/stream parser"},
    {"name": "complex", "file": "health.pdf", "desc": "Complex layout"},
    {"name": "merged_cells", "file": "row_span_1.pdf", "desc": "Tables with merged cells"},
    {"name": "multi_table", "file": "multiple_tables.pdf", "desc": "Multiple tables on one page"},
]

def measure(pdf_path, strategy="auto"):
    """Measure extraction time and memory."""
    # Get baseline memory
    start_mem = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    start = time.perf_counter()
    result = read_pdf(pdf_path, pages="all", strategy=strategy)
    elapsed = time.perf_counter() - start

    end_mem = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    return {
        "tables": len(result),
        "elapsed_s": round(elapsed, 3),
        "peak_rss_kb": end_mem,
        "strategy_history": result.strategy_history,
    }


def run_benchmarks():
    results = {}
    for bench in BENCHMARKS:
        pdf_path = os.path.join(FIXTURES_DIR, bench["file"])
        if not os.path.exists(pdf_path):
            results[bench["name"]] = {"skipped": True, "reason": "fixture not found"}
            continue

        try:
            data = measure(pdf_path)
            results[bench["name"]] = {
                "file": bench["file"],
                "description": bench["desc"],
                "backend": "native_extract_tables",
                **data,
            }
        except Exception as e:
            results[bench["name"]] = {"error": str(e)}

    return results


def main():
    print("Running performance benchmarks...")
    results = run_benchmarks()

    # Save to benchmarks.json
    output_path = os.path.join(os.path.dirname(__file__), "..", "benchmarks.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    # Print summary
    print(f"\nResults saved to benchmarks.json")
    for name, data in results.items():
        if "skipped" in data or "error" in data:
            print(f"  {name}: SKIP/ERROR")
        else:
            print(f"  {name}: {data['tables']} tables in {data['elapsed_s']}s (RSS: {data['peak_rss_kb']}KB)")


if __name__ == "__main__":
    main()
