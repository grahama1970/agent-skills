#!/usr/bin/env python3
"""Sanity test for ParallelCompiler with 5 workers and 10 theorems.

Validates that ParallelCompiler.compile_batch works correctly with
bare Lean4 (no Mathlib). Uses omega, rfl, simp, decide, and other
tactics that are available without external dependencies.
"""
from __future__ import annotations

import sys
import time

# Add parent directory to path so we can import compiler
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from compiler import ParallelCompiler

# 10 known-good theorems using bare Lean4 tactics (no Mathlib needed)
THEOREMS = [
    # 1. rfl - reflexivity
    "theorem t1 : 1 + 1 = 2 := by rfl",
    # 2. omega - linear arithmetic
    "theorem t2 : 2 + 3 = 5 := by omega",
    # 3. decide - decidable propositions
    "theorem t3 : True := by decide",
    # 4. omega - inequality
    "theorem t4 (n : Nat) : n + 0 = n := by omega",
    # 5. simp - simplification
    "theorem t5 : 0 + 1 = 1 := by simp",
    # 6. omega - more arithmetic
    "theorem t6 : 10 - 3 = 7 := by omega",
    # 7. rfl - definitional equality
    "theorem t7 : (fun x : Nat => x) 42 = 42 := by rfl",
    # 8. intro + rfl
    "theorem t8 (a : Nat) : a = a := by rfl",
    # 9. omega - chained inequality
    "theorem t9 (a b : Nat) : a + b = b + a := by omega",
    # 10. decide on Bool
    "theorem t10 : true && true = true := by decide",
]

N_WORKERS = 5


def main() -> int:
    print(f"ParallelCompiler sanity: {len(THEOREMS)} theorems, {N_WORKERS} workers")
    print("Initializing compiler (bare Lean4, no Mathlib)...")

    t0 = time.monotonic()
    compiler = ParallelCompiler(
        n_workers=N_WORKERS,
        timeout=60.0,
        lean_version="v4.16.0",
        require="",  # bare Lean4, no Mathlib
    )

    print("Compiling batch...")
    results = compiler.compile_batch(THEOREMS)
    elapsed = time.monotonic() - t0
    compiler.close()

    # Report results
    passed = 0
    failed = 0
    for i, (thm, res) in enumerate(zip(THEOREMS, results), 1):
        label = thm.split(":")[0].strip()
        if res.success:
            passed += 1
            print(f"  [{i:2d}] PASS  {label}")
        else:
            failed += 1
            print(f"  [{i:2d}] FAIL  {label}")
            print(f"         error: {res.error}")

    print(f"\nResults: {passed}/{len(THEOREMS)} passed, {failed} failed")
    print(f"Total time: {elapsed:.1f}s ({elapsed/len(THEOREMS)*1000:.0f}ms/theorem)")

    if failed > 0:
        print("\nFAIL - not all theorems compiled successfully")
        return 1

    print("\nPASS - all theorems compiled with 5 workers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
