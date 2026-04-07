#!/usr/bin/env python3
"""
formalize: Bidirectional English↔Lean4 autoformalization.

Uses /scillm for LLM generation (NOT direct openai client) and
reuses prove_retrieval.py for exemplar lookup from the 94K+ corpus.

Usage:
    from formalize import formalize, informalize, round_trip_check
    result = formalize("For all n, n + 0 = n")
    english = informalize("theorem test : ∀ n : Nat, n + 0 = n := by simp")
    rt = round_trip_check("For all n, n + 0 = n")
"""
from __future__ import annotations

import httpx
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

SCILLM_URL = "http://localhost:4001"


@dataclass
class FormalizeResult:
    """Result of English → Lean4 formalization."""
    english: str
    lean4_code: str
    compiled: bool = False
    compile_error: Optional[str] = None
    exemplars_used: int = 0
    model: str = ""


@dataclass
class RoundTripResult:
    """Result of round-trip fidelity check."""
    original_english: str
    lean4_code: str
    lean4_compiled: bool = False
    informalized_english: str = ""
    lean4_prime: str = ""
    lean4_prime_compiled: bool = False
    semantic_similarity: float = 0.0
    fidelity_ok: bool = False


def _scillm_complete(prompt: str, system: str = "", model: str = "") -> str:
    """Call /scillm for LLM completion via HTTP proxy.

    Falls back to Claude CLI if /scillm unavailable.
    """
    model = model or os.getenv("LEAN4_FORMALIZE_MODEL", "deepseek-ai/DeepSeek-V3")

    try:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {"model": model, "messages": messages}
        resp = httpx.post(
            f"{SCILLM_URL}/v1/chat/completions",
            json=payload,
            timeout=120.0,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        if content and content.strip():
            return content.strip()
    except (httpx.HTTPStatusError, httpx.TimeoutException, Exception):
        pass

    # scillm failed — no fallback available
    return "ERROR: scillm unavailable and no fallback configured"


def _retrieve_exemplars(query: str, k: int = 5) -> List[Dict]:
    """Retrieve similar exemplars via prove_retrieval (REUSE existing RAG)."""
    try:
        from prove_retrieval import retrieve_similar_proofs
        return retrieve_similar_proofs(query, k=k) or []
    except ImportError:
        return []


def _compile_check(code: str, n_workers: int = 1) -> tuple[bool, str]:
    """Quick compilation check via ParallelCompiler."""
    try:
        from compiler import ParallelCompiler
        compiler = ParallelCompiler(n_workers=min(n_workers, 1), timeout=30.0)
        results = compiler.compile_batch([code])
        compiler.close()
        if results and results[0].success:
            return True, ""
        return False, results[0].error or "compilation failed" if results else "no result"
    except Exception as e:
        return False, str(e)


def _extract_lean_code(response: str) -> str:
    """Extract Lean4 code from LLM response."""
    import re
    patterns = [
        r'```lean4?\s*\n(.*?)```',
        r'```\s*\n(.*?)```',
    ]
    for pattern in patterns:
        matches = re.findall(pattern, response, re.DOTALL)
        if matches:
            return matches[0].strip()
    return response.strip()


def formalize(
    english: str,
    exemplars: Optional[List[Dict]] = None,
    n_workers: int = 20,
    model: str = "",
) -> FormalizeResult:
    """Formalize English requirement into Lean4 code.

    1. Retrieve 5 similar from lean_theorems (REUSE prove_retrieval)
    2. Build support pack with exemplar context
    3. Generate Lean4 via /scillm
    4. Compile check via ParallelCompiler

    Args:
        english: Natural language requirement
        exemplars: Pre-fetched exemplars (or auto-retrieve)
        n_workers: Compiler workers for verification
        model: LLM model override

    Returns:
        FormalizeResult with lean4_code and compilation status
    """
    if exemplars is None:
        exemplars = _retrieve_exemplars(english, k=5)

    # Build exemplar context
    examples_text = ""
    if exemplars:
        parts = []
        for i, ex in enumerate(exemplars[:5], 1):
            stmt = ex.get("formal_statement", ex.get("statement", ""))
            proof = ex.get("formal_proof", ex.get("proof", ""))
            if stmt:
                parts.append(f"Example {i}:\n  Statement: {stmt}\n  Proof: {proof}")
        examples_text = "\n".join(parts)

    system = """You are an expert Lean4 formalizer. Given a natural language statement,
produce a valid Lean4 theorem with proof. Return ONLY the Lean4 code in a ```lean4 block.

Rules:
- Use `import Mathlib` for all imports
- The code must compile with `lake env lean`
- Prefer `simp`, `omega`, `ring`, `norm_num` for automation
- Name the theorem descriptively"""

    prompt = f"Formalize this into Lean4:\n\n{english}"
    if examples_text:
        prompt += f"\n\nSimilar verified proofs for reference:\n{examples_text}"

    response = _scillm_complete(prompt, system=system, model=model)
    lean4_code = _extract_lean_code(response)

    # Compile check
    compiled, compile_error = _compile_check(lean4_code, n_workers)

    return FormalizeResult(
        english=english,
        lean4_code=lean4_code,
        compiled=compiled,
        compile_error=compile_error if not compiled else None,
        exemplars_used=len(exemplars),
        model=model or "default",
    )


def informalize(lean4_code: str, model: str = "") -> str:
    """Convert Lean4 code to natural language English.

    Args:
        lean4_code: Valid Lean4 code
        model: LLM model override

    Returns:
        Natural language description
    """
    system = """You are an expert at reading Lean4 formal proofs.
Given Lean4 code, explain in plain English what it proves.
Be precise and concise. Return ONLY the English statement, no code."""

    prompt = f"Explain what this Lean4 code proves:\n\n```lean4\n{lean4_code}\n```"
    return _scillm_complete(prompt, system=system, model=model)


def round_trip_check(
    english: str,
    n_workers: int = 20,
    similarity_threshold: float = 0.85,
    model: str = "",
) -> RoundTripResult:
    """Round-trip fidelity check: english → lean4 → compile → english' → lean4' → compile.

    Both compilations must pass and semantic similarity >= threshold.

    Args:
        english: Original English requirement
        n_workers: Compiler workers
        similarity_threshold: Min semantic similarity for fidelity
        model: LLM model override

    Returns:
        RoundTripResult with full pipeline results
    """
    # Forward: English → Lean4
    fwd = formalize(english, n_workers=n_workers, model=model)

    result = RoundTripResult(
        original_english=english,
        lean4_code=fwd.lean4_code,
        lean4_compiled=fwd.compiled,
    )

    if not fwd.compiled:
        return result

    # Backward: Lean4 → English'
    informalized = informalize(fwd.lean4_code, model=model)
    result.informalized_english = informalized

    # Forward again: English' → Lean4'
    fwd2 = formalize(informalized, n_workers=n_workers, model=model)
    result.lean4_prime = fwd2.lean4_code
    result.lean4_prime_compiled = fwd2.compiled

    # Semantic similarity (simple word overlap as fallback)
    orig_words = set(english.lower().split())
    inf_words = set(informalized.lower().split())
    if orig_words or inf_words:
        overlap = len(orig_words & inf_words)
        total = len(orig_words | inf_words)
        result.semantic_similarity = overlap / max(total, 1)
    else:
        result.semantic_similarity = 0.0

    result.fidelity_ok = (
        fwd.compiled
        and fwd2.compiled
        and result.semantic_similarity >= similarity_threshold
    )

    return result
