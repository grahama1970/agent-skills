#!/usr/bin/env python3
"""Sanity: polars DataFrame round-trip."""
import sys
try:
    import polars as pl
except ImportError:
    print("FAIL: polars not installed")
    sys.exit(1)

df = pl.DataFrame({"col1": [1, 2, 3], "col2": ["a", "b", "c"]})
assert df.shape == (3, 2)

# to_pandas compat
pdf = df.to_pandas()
assert len(pdf) == 3

# CSV round-trip
csv = df.write_csv()
assert "col1" in csv

print("PASS: polars -- DataFrame, to_pandas(), write_csv() all work")
sys.exit(0)
