#!/usr/bin/env python3
"""
compiler: Parallel Lean4 compilation via lean-interact.

Replaces Docker-based compilation with lean-interact's LeanServerPool
for 20+ concurrent silos with crash recovery and OOM auto-restart.

Usage:
    from compiler import ParallelCompiler
    compiler = ParallelCompiler(n_workers=20)
    results = compiler.compile_batch(["theorem test : 1 + 1 = 2 := by norm_num"])
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional

from lean_interact import (
    AutoLeanServer,
    Command,
    LeanREPLConfig,
    LeanServerPool,
    ProofStep,
    TempRequireProject,
)
from lean_interact.interface import LeanError


@dataclass
class CompileResult:
    """Result of compiling a single Lean4 proof."""
    success: bool
    error: Optional[str] = None
    stdout: str = ""
    goals: List[str] = field(default_factory=list)
    elapsed_ms: float = 0.0

    def __bool__(self) -> bool:
        return self.success


@dataclass
class StepResult:
    """Result of a single tactic step (for GRPO step rewards)."""
    tactic: str
    success: bool
    goals: List[str] = field(default_factory=list)
    state_id: int = 0
    error: Optional[str] = None


def _make_config(
    lean_version: Optional[str] = None,
    memory_limit_mb: Optional[int] = None,
    require: str = "mathlib",
) -> LeanREPLConfig:
    """Create a LeanREPLConfig with optional dependency support.

    Args:
        lean_version: Lean version string (e.g., 'v4.16.0'). None = latest.
        memory_limit_mb: Per-worker memory limit. None = no limit (recommended).
        require: Lake dependency string. 'mathlib' for Mathlib, '' for bare Lean4.

    First-time: downloads Lean REPL binary + builds deps (~5-10 min for Mathlib).
    Subsequent: uses lake cache (near-instant).
    File locks prevent concurrent build races.
    """
    resolved_require = require if require else []
    # lean-interact >=0.11 requires explicit lean_version (None → TypeError).
    # Discover installed version from lean --version, fall back to stable.
    if lean_version is None:
        import shutil, subprocess as _sp
        if shutil.which("lean"):
            try:
                out = _sp.check_output(["lean", "--version"], text=True, timeout=10)
                # Output: "Lean (version 4.28.0, ...)"
                import re
                m = re.search(r"version (\d+\.\d+\.\d+)", out)
                if m:
                    lean_version = f"v{m.group(1)}"
            except Exception:
                pass
        if lean_version is None:
            lean_version = "v4.28.0"
    return LeanREPLConfig(
        project=TempRequireProject(lean_version=lean_version, require=resolved_require),
        memory_hard_limit_mb=memory_limit_mb,
        enable_incremental_optimization=True,
    )


class ParallelCompiler:
    """Parallel Lean4 compiler using lean-interact LeanServerPool.

    Manages N concurrent Lean4 REPL instances with:
    - Thread-based workers with shared ReplaySessionCache
    - AutoLeanServer crash recovery (max 5 restart attempts)
    - OOM auto-restart via memory_hard_limit_mb
    - Per-proof timeout enforcement

    Args:
        n_workers: Number of parallel compilation silos (default: 20)
        timeout: Per-proof timeout in seconds (default: 30.0)
        lean_version: Lean version (None = latest compatible)
        memory_limit_mb: Per-worker memory limit in MB. None = no limit (recommended).
        require: Lake dependency string. 'mathlib' for Mathlib, '' for bare Lean4.
    """

    def __init__(
        self,
        n_workers: int = 20,
        timeout: float = 30.0,
        lean_version: Optional[str] = None,
        memory_limit_mb: Optional[int] = None,
        require: str = "mathlib",
    ):
        self.n_workers = n_workers
        self.timeout = timeout
        self.config = _make_config(lean_version, memory_limit_mb, require=require)
        self._pool: Optional[LeanServerPool] = None

    @property
    def pool(self) -> LeanServerPool:
        """Lazy-init pool (Mathlib build happens on first access)."""
        if self._pool is None:
            self._pool = LeanServerPool(
                self.config, num_workers=self.n_workers,
                max_total_memory=0.95,    # host runs many containers
                max_process_memory=None,  # no per-process limit
            )
        return self._pool

    def compile_one(self, code: str) -> CompileResult:
        """Compile a single proof synchronously."""
        t0 = time.monotonic()
        try:
            server = AutoLeanServer(
                self.config, max_restart_attempts=5,
                max_total_memory=0.95,    # host runs many containers
                max_process_memory=None,  # no per-process limit
            )
            resp = server.run(Command(cmd=code), timeout=self.timeout)
            elapsed = (time.monotonic() - t0) * 1000

            if isinstance(resp, LeanError):
                return CompileResult(
                    success=False,
                    error=resp.error if hasattr(resp, "error") else str(resp),
                    elapsed_ms=elapsed,
                )

            # Check CommandResponse.messages for error-severity messages.
            # lean-interact returns CommandResponse (not LeanError) even when
            # compilation fails — errors are in the messages list.
            error_msgs = [
                m for m in getattr(resp, "messages", [])
                if getattr(m, "severity", "") == "error"
            ]
            has_sorries = bool(getattr(resp, "sorries", []))

            if error_msgs:
                error_text = "\n".join(
                    getattr(m, "data", str(m)) for m in error_msgs
                )
                return CompileResult(
                    success=False,
                    error=error_text,
                    stdout=getattr(resp, "stdout", "") or "",
                    elapsed_ms=elapsed,
                )

            if has_sorries:
                return CompileResult(
                    success=False,
                    error="Proof contains sorry (incomplete)",
                    stdout=getattr(resp, "stdout", "") or "",
                    elapsed_ms=elapsed,
                )

            return CompileResult(
                success=True,
                stdout=getattr(resp, "stdout", "") or "",
                elapsed_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            return CompileResult(success=False, error=str(e), elapsed_ms=elapsed)

    def compile_batch(self, proofs: List[str]) -> List[CompileResult]:
        """Compile multiple proofs in parallel using LeanServerPool.

        Args:
            proofs: List of Lean4 code strings

        Returns:
            List of CompileResult in same order as input
        """
        if not proofs:
            return []

        requests = [Command(cmd=code) for code in proofs]
        t0 = time.monotonic()

        try:
            raw_results = self.pool.run_batch(requests, timeout_per_cmd=self.timeout)
        except Exception as e:
            # Pool-level failure: return all as errors
            elapsed = (time.monotonic() - t0) * 1000
            return [
                CompileResult(success=False, error=f"Pool error: {e}", elapsed_ms=elapsed)
                for _ in proofs
            ]

        results = []
        for resp in raw_results:
            if isinstance(resp, LeanError):
                results.append(CompileResult(
                    success=False,
                    error=resp.error if hasattr(resp, "error") else str(resp),
                ))
            elif isinstance(resp, Exception):
                results.append(CompileResult(success=False, error=str(resp)))
            else:
                results.append(CompileResult(
                    success=True,
                    stdout=getattr(resp, "stdout", "") or "",
                ))

        return results

    def step_verify(
        self,
        theorem_header: str,
        tactics: List[str],
    ) -> List[StepResult]:
        """Per-tactic incremental elaboration for GRPO step rewards.

        Loads a theorem declaration, then checks each tactic individually.
        Returns results for each step — first failure propagates.

        Args:
            theorem_header: The theorem statement (e.g., "theorem foo : 1+1=2 := by")
            tactics: List of tactic strings to verify incrementally

        Returns:
            List of StepResult, one per tactic
        """
        server = AutoLeanServer(self.config, max_restart_attempts=5)

        # Load the theorem header
        header_resp = server.run(Command(cmd=theorem_header), timeout=self.timeout)
        if isinstance(header_resp, LeanError):
            return [StepResult(
                tactic=tactics[0] if tactics else "",
                success=False,
                error=f"Header failed: {header_resp.error if hasattr(header_resp, 'error') else str(header_resp)}",
            )]

        results = []
        state_id = 0
        for tactic in tactics:
            try:
                resp = server.run(
                    ProofStep(tactic=tactic, proof_state=state_id),
                    timeout=self.timeout,
                )

                if isinstance(resp, LeanError):
                    results.append(StepResult(
                        tactic=tactic,
                        success=False,
                        state_id=state_id,
                        error=resp.error if hasattr(resp, "error") else str(resp),
                    ))
                    # Propagate failure: remaining tactics get same error
                    for remaining in tactics[len(results):]:
                        results.append(StepResult(
                            tactic=remaining,
                            success=False,
                            state_id=state_id,
                            error="skipped (previous tactic failed)",
                        ))
                    break

                goals = getattr(resp, "goals", []) or []
                new_state = getattr(resp, "new_proof_state", state_id)
                results.append(StepResult(
                    tactic=tactic,
                    success=True,
                    goals=goals,
                    state_id=new_state,
                ))
                state_id = new_state

            except Exception as e:
                results.append(StepResult(
                    tactic=tactic,
                    success=False,
                    state_id=state_id,
                    error=str(e),
                ))
                break

        return results

    def close(self):
        """Shut down the pool."""
        if self._pool is not None:
            try:
                self._pool.close()
            except Exception:
                pass
            self._pool = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ---------------------------------------------------------------------------
# Docker compatibility shim (deprecation bridge)
# ---------------------------------------------------------------------------

def compile_lean_compat(
    code: str,
    container: str = "lean_runner",
    timeout: int = 120,
) -> dict:
    """Drop-in replacement for prove.py's compile_lean() using lean-interact.

    Returns dict matching the original Docker-based interface:
        {"success": bool, "exit_code": int, "stdout": str, "stderr": str}

    The `container` parameter is accepted but ignored (prints deprecation
    warning on first use).
    """
    import sys
    if not hasattr(compile_lean_compat, "_warned"):
        compile_lean_compat._warned = True
        if container != "_internal":
            print(
                "[lean4-prove] DEPRECATION: Docker container is no longer used. "
                "Compilation now uses lean-interact AutoLeanServer. "
                "The --container flag is a no-op.",
                file=sys.stderr,
            )

    compiler = ParallelCompiler(n_workers=1, timeout=float(timeout))
    result = compiler.compile_one(code)
    compiler.close()

    return {
        "success": result.success,
        "exit_code": 0 if result.success else 1,
        "stdout": result.stdout or "",
        "stderr": result.error or "",
    }
