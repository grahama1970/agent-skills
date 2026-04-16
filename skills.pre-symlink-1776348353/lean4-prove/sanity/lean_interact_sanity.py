#!/usr/bin/env python3
"""Sanity check for lean-interact installation.

Verifies that:
1. lean_interact imports succeed (AutoLeanServer, Command, LeanREPLConfig)
2. The Lean REPL binary can be built/found
3. A simple theorem (1 + 1 = 2) compiles without error using omega

Exit code 0 = PASS, 1 = FAIL.

NOTE: First run downloads and builds the Lean REPL binary (~5-10 min).
"""

from __future__ import annotations

import sys
import time
import traceback


def main() -> int:
    # Step 1: Verify imports
    print("[1/3] Verifying lean_interact imports...")
    try:
        from lean_interact import AutoLeanServer, Command, LeanREPLConfig
        from lean_interact.interface import LeanError
    except ImportError as e:
        print(f"FAIL: Import error - {e}")
        return 1
    print("  OK: AutoLeanServer, Command, LeanREPLConfig, LeanError imported")

    # Step 2: Create config (no project = bare Lean, no mathlib needed for norm_num)
    print("[2/3] Creating LeanREPLConfig...")
    try:
        config = LeanREPLConfig(
            lean_version=None,
            # memory_hard_limit_mb limits virtual address space via setrlimit(RLIMIT_AS).
            # Setting it too low (e.g. 512) prevents Lean from spawning threads.
            # Use None to leave it unconstrained and let the OS manage memory.
            memory_hard_limit_mb=None,
            enable_parallel_elaboration=False,
            verbose=True,
        )
    except Exception as e:
        print(f"FAIL: Could not create config - {e}")
        traceback.print_exc()
        return 1
    print("  OK: Config created (no memory limit, parallel_elaboration=False)")

    # Step 3: Compile a simple theorem
    # norm_num requires Mathlib; use omega (built-in since Lean 4.8+) for bare Lean
    theorem = "theorem test : 1 + 1 = 2 := by omega"
    print(f"[3/3] Compiling: {theorem}")
    t0 = time.time()
    try:
        server = AutoLeanServer(config)
        cmd = Command(cmd=theorem)
        result = server.run(cmd, timeout=300)
        elapsed = time.time() - t0
    except Exception as e:
        elapsed = time.time() - t0
        print(f"FAIL: Server/compilation error after {elapsed:.1f}s - {e}")
        traceback.print_exc()
        return 1

    # Check result type
    if isinstance(result, LeanError):
        print(f"FAIL: LeanError after {elapsed:.1f}s - {result.model_dump_json(indent=2)}")
        return 1

    # Check for compilation errors
    if result.has_errors():
        errors = result.get_errors()
        print(f"FAIL: Compilation errors after {elapsed:.1f}s:")
        for err in errors:
            print(f"  - {err}")
        return 1

    # Check validity
    if not result.lean_code_is_valid():
        print(f"FAIL: Code not valid after {elapsed:.1f}s")
        print(f"  Response: {result.model_dump_json(indent=2)}")
        return 1

    warnings = result.get_warnings() if hasattr(result, "get_warnings") else []
    print(f"  OK: Compiled successfully in {elapsed:.1f}s")
    if warnings:
        print(f"  Warnings: {warnings}")

    print()
    print(f"PASS: lean-interact sanity check passed ({elapsed:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
