#!/usr/bin/env python3
"""Quick benchmark: extract tables from fixture PDFs and report accuracy."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.python.extract_tables import read_pdf

FIXTURES_SKILL = Path(__file__).resolve().parent / "fixtures"
FIXTURES_CAMELOT = Path("/home/graham/workspace/experiments/camelot/tests/files")

PDFS = [
    ("foo", FIXTURES_SKILL / "foo.pdf", "lattice"),
    ("multiple_tables", FIXTURES_SKILL / "multiple_tables.pdf", "lattice"),
    ("column_span_2", FIXTURES_SKILL / "column_span_2.pdf", "lattice"),
    ("row_span_2", FIXTURES_SKILL / "row_span_2.pdf", "lattice"),
    ("column_span_1", FIXTURES_CAMELOT / "column_span_1.pdf", "lattice"),
    ("row_span_1", FIXTURES_SKILL / "row_span_1.pdf", "lattice"),
    ("twotables_1", FIXTURES_SKILL / "twotables_1.pdf", "lattice"),
    ("health", FIXTURES_SKILL / "health.pdf", "stream"),
]

for name, path, flavor in PDFS:
    if not path.exists():
        print(f"{name:20s}  MISSING {path}")
        continue
    t0 = time.time()
    try:
        result = read_pdf(str(path), flavor=flavor)
        elapsed = time.time() - t0
        tables = result.tables
        n = len(tables)
        accs = []
        for t in tables:
            if hasattr(t, 'accuracy') and t.accuracy is not None:
                accs.append(t.accuracy)
        avg_acc = sum(accs) / len(accs) if accs else 0.0
        shapes = [f"{t.rows}x{t.cols}" for t in tables]
        print(f"{name:20s}  tables={n}  acc={avg_acc:5.1f}%  time={elapsed:.1f}s  shapes={shapes}")
        # Print first few cells of first table for debugging
        if tables and tables[0].cells:
            for cell in tables[0].cells[:8]:
                txt = repr(cell.text)[:30]
                print(f"  cell({cell.x1:.0f},{cell.y1:.0f})-({cell.x2:.0f},{cell.y2:.0f}): {txt}")
    except Exception as e:
        import traceback
        elapsed = time.time() - t0
        print(f"{name:20s}  ERROR: {e}  time={elapsed:.1f}s")
        traceback.print_exc()
