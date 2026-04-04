#!/usr/bin/env python3
"""Lean4 Compilation Service — HTTP daemon wrapping ParallelCompiler.

LeanServerPool (20 workers) initializes ONCE at startup and persists.
All consumers call POST /compile, /compile-batch, or /step-verify.

Port: 8604 (configurable via LEAN4_SERVICE_PORT)
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import List, Optional

import httpx
from fastapi import FastAPI, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

from compiler import CompileResult, ParallelCompiler, StepResult

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
N_WORKERS = int(os.getenv("LEAN4_WORKERS", "20"))
TIMEOUT = float(os.getenv("LEAN4_TIMEOUT", "60"))
MEMORY_LIMIT_MB = os.getenv("LEAN4_MEMORY_LIMIT_MB")  # None = no limit
REQUIRE = os.getenv("LEAN4_REQUIRE", "mathlib")

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class CompileRequest(BaseModel):
    code: str = Field(..., description="Lean4 source code to compile")
    timeout: Optional[float] = Field(None, description="Override default timeout (seconds)")


class CompileResponse(BaseModel):
    success: bool
    error: Optional[str] = None
    stdout: str = ""
    elapsed_ms: float = 0.0


class BatchCompileRequest(BaseModel):
    proofs: List[str] = Field(..., description="List of Lean4 code strings")
    timeout: Optional[float] = None


class BatchCompileResponse(BaseModel):
    results: List[CompileResponse]
    total_ms: float = 0.0


class StepVerifyRequest(BaseModel):
    theorem_header: str = Field(..., description="Theorem statement (e.g. 'theorem foo : 1+1=2 := by')")
    tactics: List[str] = Field(..., description="Tactic strings to verify incrementally")
    timeout: Optional[float] = None


class StepResultModel(BaseModel):
    tactic: str
    success: bool
    goals: List[str] = []
    state_id: int = 0
    error: Optional[str] = None


class StepVerifyResponse(BaseModel):
    results: List[StepResultModel]


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Lean4 Prove Service",
    description="Shared compilation daemon — 20-worker LeanServerPool",
    version="1.0.0",
)

_compiler: Optional[ParallelCompiler] = None


@app.on_event("startup")
async def startup():
    global _compiler
    mem_limit = int(MEMORY_LIMIT_MB) if MEMORY_LIMIT_MB else None
    _compiler = ParallelCompiler(
        n_workers=N_WORKERS,
        timeout=TIMEOUT,
        memory_limit_mb=mem_limit,
        require=REQUIRE,
    )
    # Trigger lazy pool init so Mathlib builds at startup, not on first request
    _ = _compiler.pool


@app.on_event("shutdown")
async def shutdown():
    global _compiler
    if _compiler:
        _compiler.close()
        _compiler = None


def _get_compiler() -> ParallelCompiler:
    if _compiler is None:
        raise HTTPException(503, "Compiler not initialized")
    return _compiler


_stats = {"proofs_attempted": 0, "proofs_succeeded": 0, "compiles_total": 0,
          "compiles_succeeded": 0, "last_proof_at": None, "total_compile_ms": 0.0}


@app.get("/health")
async def health():
    c = _get_compiler()

    # Check scillm reachability (pass auth since /v1/models requires it)
    scillm_ok = False
    try:
        r = httpx.get(f"{SCILLM_BASE}/v1/models", timeout=3,
                      headers={"Authorization": f"Bearer {SCILLM_KEY}"})
        scillm_ok = r.status_code == 200
    except Exception:
        pass

    avg_compile_ms = (_stats["total_compile_ms"] / _stats["compiles_total"]
                      if _stats["compiles_total"] > 0 else 0)

    return {
        "ok": True,
        "workers": c.n_workers,
        "timeout": c.timeout,
        "scillm_reachable": scillm_ok,
        "scillm_url": SCILLM_BASE,
        "prove_available": scillm_ok,
        "stats": {
            "proofs_attempted": _stats["proofs_attempted"],
            "proofs_succeeded": _stats["proofs_succeeded"],
            "success_rate": (_stats["proofs_succeeded"] / _stats["proofs_attempted"]
                            if _stats["proofs_attempted"] > 0 else 0),
            "compiles_total": _stats["compiles_total"],
            "avg_compile_ms": round(avg_compile_ms, 1),
            "last_proof_at": _stats["last_proof_at"],
        },
    }


@app.post("/compile", response_model=CompileResponse)
async def compile_one(req: CompileRequest):
    """Compile a single Lean4 proof."""
    c = _get_compiler()
    timeout = req.timeout or c.timeout
    if req.timeout and req.timeout != c.timeout:
        result = ParallelCompiler(n_workers=1, timeout=timeout).compile_one(req.code)
    else:
        result = c.compile_one(req.code)
    _stats["compiles_total"] += 1
    _stats["total_compile_ms"] += result.elapsed_ms
    if result.success:
        _stats["compiles_succeeded"] += 1
    return CompileResponse(
        success=result.success,
        error=result.error,
        stdout=result.stdout,
        elapsed_ms=result.elapsed_ms,
    )


@app.post("/compile-batch", response_model=BatchCompileResponse)
async def compile_batch(req: BatchCompileRequest):
    """Compile multiple proofs in parallel via LeanServerPool."""
    c = _get_compiler()
    t0 = time.monotonic()
    results = c.compile_batch(req.proofs)
    total_ms = (time.monotonic() - t0) * 1000
    return BatchCompileResponse(
        results=[
            CompileResponse(
                success=r.success,
                error=r.error,
                stdout=r.stdout,
                elapsed_ms=r.elapsed_ms,
            )
            for r in results
        ],
        total_ms=total_ms,
    )


@app.post("/step-verify", response_model=StepVerifyResponse)
async def step_verify(req: StepVerifyRequest):
    """Per-tactic incremental elaboration for GRPO step rewards."""
    c = _get_compiler()
    results = c.step_verify(req.theorem_header, req.tactics)
    return StepVerifyResponse(
        results=[
            StepResultModel(
                tactic=r.tactic,
                success=r.success,
                goals=r.goals,
                state_id=r.state_id,
                error=r.error,
            )
            for r in results
        ],
    )


# ---------------------------------------------------------------------------
# /prove — full pipeline: generate via scillm → compile → retry
# ---------------------------------------------------------------------------

SCILLM_BASE = os.getenv("SCILLM_API_BASE", "http://host.docker.internal:4001")
SCILLM_KEY = os.getenv("SCILLM_PROXY_KEY", "sk-dev-proxy-123")


# ---------------------------------------------------------------------------
# Lean4 proof modes — each is a fundamentally different approach to proof
# ---------------------------------------------------------------------------

PROOF_MODES: dict[str, str] = {
    "tactic": (
        "Write the proof in TACTIC MODE using `by` blocks.\n"
        "Use goal-transforming tactics: simp, ring, omega, linarith, norm_num, field_simp, push_neg.\n"
        "Chain tactics with semicolons or newlines. Use `<;>` for focusing.\n"
        "Example: theorem foo : 1 + 1 = 2 := by norm_num"
    ),
    "term": (
        "Write the proof in TERM MODE — construct the proof term directly.\n"
        "Use lambda, angle brackets, function application, pattern matching.\n"
        "No `by` keyword. The proof IS the term.\n"
        "Example: theorem foo : 1 + 1 = 2 := rfl\n"
        "Example: theorem foo (h : P) : P ∨ Q := Or.inl h"
    ),
    "structured": (
        "Write a STRUCTURED PROOF using `calc`, `have`, `show`, `suffices`.\n"
        "Break the proof into named intermediate steps for readability.\n"
        "Use `calc` for chains of equalities/inequalities.\n"
        "Example:\n"
        "theorem foo (n : Nat) : n + 0 = n := by\n"
        "  have h : n + 0 = n := Nat.add_zero n\n"
        "  exact h"
    ),
    "automation": (
        "Use AUTOMATED PROOF SEARCH tactics: aesop, exact?, apply?, omega, decide.\n"
        "Let Lean's automation find the proof. Prefer single-tactic proofs.\n"
        "Try aesop first (general-purpose), then omega (arithmetic), then decide (decidable).\n"
        "Example: theorem foo : 1 + 1 = 2 := by decide"
    ),
    "induction": (
        "Use INDUCTION or CASE ANALYSIS as the primary proof strategy.\n"
        "Use `induction` for recursive structures (Nat, List, etc.).\n"
        "Use `cases` for sum types (Or, Option, etc.).\n"
        "Handle all cases explicitly. Use `simp` or `omega` in each case.\n"
        "Example:\n"
        "theorem foo (n : Nat) : 0 + n = n := by\n"
        "  induction n with\n"
        "  | zero => rfl\n"
        "  | succ n ih => simp [Nat.succ_add, ih]"
    ),
    "decision": (
        "Use DECISION PROCEDURES for fully automated proofs.\n"
        "These work for decidable propositions, arithmetic, and computation.\n"
        "Try in order: native_decide, decide, norm_num, omega.\n"
        "If the statement is about concrete numbers or finite structures, this will work.\n"
        "Example: theorem foo : 1 + 1 = 2 := by native_decide"
    ),
    "requirements": (
        "Formalize an ENGINEERING REQUIREMENT as a Lean4 theorem.\n"
        "The requirement describes a property of a system, control, or specification.\n"
        "Model the domain as structures/inductive types, then prove the requirement holds.\n"
        "Common patterns:\n"
        "- Control mitigates threat: structure Control, structure Threat, def mitigates\n"
        "- Subsumption: Control A subsumes Control B if A covers all of B's properties\n"
        "- Table-derived: Properties from a spreadsheet row become structure fields\n"
        "- Coverage: A set of controls covers a threat if at least one mitigates it\n"
        "Use Prop for assertions, Bool for decidable checks, Decidable instances for both.\n"
        "Prefer `deriving DecidableEq, Repr` on structures for automation.\n"
        "Example:\n"
        "structure Control where\n"
        "  id : String\n"
        "  mitigates : List String\n"
        "  deriving DecidableEq, Repr\n\n"
        "def covers (controls : List Control) (threat : String) : Prop :=\n"
        "  ∃ c ∈ controls, threat ∈ c.mitigates\n\n"
        "theorem ac2_covers_ia0003 : covers [⟨\"AC-2\", [\"IA-0003\"]⟩] \"IA-0003\" :=\n"
        "  ⟨⟨\"AC-2\", [\"IA-0003\"]⟩, List.Mem.head _, List.Mem.head _⟩"
    ),
}

# Default race: try all modes concurrently
DEFAULT_MODES = ["tactic", "term", "automation", "decision", "requirements"]


class ProveRequest(BaseModel):
    requirement: str = Field(..., description="Theorem or requirement to prove")
    model: str = Field("text", description="scillm model for generation")
    max_retries: int = Field(3, description="Max compile→fix rounds per proof mode")
    timeout: Optional[float] = Field(None, description="Compile timeout override")
    proof_modes: Optional[List[str]] = Field(
        None,
        description=(
            "Proof modes to race concurrently. If omitted, races all 6 modes. "
            "Options: tactic, term, structured, automation, induction, decision"
        ),
    )


class ProveResponse(BaseModel):
    success: bool
    code: Optional[str] = None
    attempts: int = 0
    errors: Optional[List[str]] = None
    proof_mode: Optional[str] = Field(None, description="Which proof mode won")
    strategy_index: int = Field(0, description="Index of winning mode (-1 if all failed)")
    all_results: Optional[List[Optional[dict]]] = Field(
        None, description="Per-mode results (only when multiple modes raced)"
    )


def _call_scillm(messages: list[dict], model: str = "text") -> str:
    """Call scillm for proof generation."""
    resp = httpx.post(
        f"{SCILLM_BASE}/v1/chat/completions",
        json={"model": model, "messages": messages, "max_tokens": 4096, "temperature": 0.2},
        headers={"Authorization": f"Bearer {SCILLM_KEY}"},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _extract_lean_code(text: str) -> str:
    """Extract Lean4 code from LLM response."""
    fence = re.search(r'```(?:lean4?|)\n(.*?)```', text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    lines = [l for l in text.split('\n') if not l.startswith('#') and l.strip()]
    return '\n'.join(lines).strip()


def _run_proof_mode(
    c: ParallelCompiler,
    requirement: str,
    mode_name: str,
    mode_prompt: str,
    model: str,
    strategy_idx: int,
    max_retries: int,
) -> dict:
    """Run one proof mode: generate via scillm, compile, retry with error feedback."""
    system_prompt = (
        "You are a Lean4 theorem proving expert. Write complete, compilable Lean4 code.\n"
        "Return ONLY the Lean4 code, no explanations.\n\n"
        f"PROOF STRATEGY — {mode_name.upper()}:\n{mode_prompt}"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Prove the following in Lean4:\n\n{requirement}"},
    ]

    errors: list[str] = []
    for attempt in range(max_retries):
        try:
            resp = httpx.post(
                f"{SCILLM_BASE}/v1/chat/completions",
                json={"model": model, "messages": messages,
                      "max_tokens": 4096, "temperature": 0.2 + (attempt * 0.1)},
                headers={"Authorization": f"Bearer {SCILLM_KEY}"},
                timeout=120,
            )
            resp.raise_for_status()
            code = _extract_lean_code(resp.json()["choices"][0]["message"]["content"])
        except Exception as e:
            errors.append(f"{mode_name} attempt {attempt + 1}: generation error: {e}")
            continue

        if not code:
            errors.append(f"{mode_name} attempt {attempt + 1}: empty code")
            continue

        result = c.compile_one(code)
        if result.success:
            return {"success": True, "code": code, "attempts": attempt + 1,
                    "strategy_index": strategy_idx, "proof_mode": mode_name,
                    "errors": errors or None}

        error_msg = result.error or ""
        errors.append(f"{mode_name} attempt {attempt + 1}: {error_msg[:300]}")
        messages.append({"role": "assistant", "content": f"```lean\n{code}\n```"})
        messages.append({"role": "user", "content": f"Compile error:\n{error_msg}\nFix the code. Return ONLY corrected Lean4 code."})

    return {"success": False, "code": None, "attempts": max_retries,
            "strategy_index": strategy_idx, "proof_mode": mode_name, "errors": errors}


@app.post("/prove", response_model=ProveResponse)
async def prove_endpoint(req: ProveRequest):
    """Prove a theorem by racing proof modes concurrently.

    - No `proof_modes`: races all default modes (tactic, term, automation, decision, requirements)
    - With `proof_modes`: races only the specified modes
    - Single mode: no concurrency overhead

    Each mode is a fundamentally different approach to proof construction.
    Most will fail for any given theorem — the value is in trying all concurrently.
    First compiled proof wins, others are cancelled.
    """
    import asyncio

    c = _get_compiler()
    _stats["proofs_attempted"] += 1
    _stats["last_proof_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Resolve proof modes
    mode_names = req.proof_modes or DEFAULT_MODES
    modes = []
    for name in mode_names:
        if name in PROOF_MODES:
            modes.append((name, PROOF_MODES[name]))
        else:
            logger.warning("Unknown proof mode '{}', skipping", name)

    if not modes:
        return ProveResponse(success=False, errors=["No valid proof modes specified"])

    if len(modes) == 1:
        name, prompt = modes[0]
        result = _run_proof_mode(c, req.requirement, name, prompt, req.model, 0, req.max_retries)
        if result["success"]:
            _stats["proofs_succeeded"] += 1
        return ProveResponse(**result)

    # Race all modes concurrently
    tasks = [
        asyncio.create_task(asyncio.to_thread(
            _run_proof_mode, c, req.requirement, name, prompt, req.model, idx, req.max_retries
        ))
        for idx, (name, prompt) in enumerate(modes)
    ]

    all_results: list[dict | None] = [None] * len(modes)
    winner = None

    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    while done:
        for task in done:
            result = await task
            all_results[result["strategy_index"]] = result
            if result["success"] and winner is None:
                winner = result
        if winner:
            for t in pending:
                t.cancel()
            break
        if not pending:
            break
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)

    if winner:
        _stats["proofs_succeeded"] += 1
        return ProveResponse(
            success=True, code=winner["code"], attempts=winner["attempts"],
            proof_mode=winner.get("proof_mode"), strategy_index=winner["strategy_index"],
            all_results=all_results,
        )

    total_attempts = sum(r["attempts"] for r in all_results if r)
    return ProveResponse(
        success=False, strategy_index=-1, attempts=total_attempts, all_results=all_results,
        errors=[e for r in all_results if r for e in (r.get("errors") or [])],
    )


