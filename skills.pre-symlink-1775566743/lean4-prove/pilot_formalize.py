#!/usr/bin/env python3
"""
Pilot formalization: 100 SPARTA controls -> Lean4 -> compile check.

Uses /scillm (via subprocess to scillm venv) for LLM calls (NON-NEGOTIABLE).
Uses ParallelCompiler (lean-interact) for compilation.
Writes results to data/pilot_formalization.jsonl.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

# Load .env
try:
    from dotenv import load_dotenv
    for envpath in [
        os.path.expanduser("~/workspace/experiments/pi-mono/.env"),
        os.path.expanduser("~/workspace/experiments/memory/.env"),
    ]:
        if os.path.exists(envpath):
            load_dotenv(envpath, override=False)
except ImportError:
    pass

from arango import ArangoClient
from compiler import ParallelCompiler

# ── Config ────────────────────────────────────────────────────────────────
ARANGO_HOST = os.getenv("ARANGO_HOST", "localhost")
ARANGO_PORT = int(os.getenv("ARANGO_PORT", "8529"))
ARANGO_DB = "memory"  # NON-NEGOTIABLE
ARANGO_USER = os.getenv("ARANGO_USER", "root")
ARANGO_PASS = os.getenv("ARANGO_PASS", "openSesame")

SCILLM_DIR = Path(__file__).resolve().parent.parent / "scillm"

N_CONTROLS = 100
N_WORKERS = 5
COMPILE_TIMEOUT = 60.0
LEAN_VERSION = "v4.16.0"
OUTPUT_PATH = Path(__file__).resolve().parent / "data" / "pilot_formalization.jsonl"

SYSTEM_PROMPT = """You are an expert Lean4 formalizer for cybersecurity and space systems requirements.

Given a security control (name + description), produce a Lean4 formalization that:
1. Models the key property/invariant as a theorem or structure
2. Uses appropriate types (e.g., Bool for flags, Prop for properties, Nat for counts)
3. Compiles with standard Lean4 (NO Mathlib imports)

Return ONLY the Lean4 code in a ```lean4 block. Keep it simple and compilable.

Rules:
- Do NOT use `import Mathlib` or any external imports
- Prefer simple types: Bool, Nat, Prop, String, List
- Use `theorem`, `def`, or `structure` as appropriate
- For proofs use: `by simp`, `by decide`, `by omega`, `by intro; exact`, `by trivial`, `by rfl`
- Name identifiers using snake_case based on the control name
- Keep the formalization focused on the CORE invariant, not every detail
- The code MUST compile standalone with `lean`
- Always include necessary type annotations
- For boolean properties, model them as (config : SomeStructure) → config.field = true
- Wrap the entire code so it compiles as a single file"""


def fetch_controls(n: int = N_CONTROLS) -> list[dict]:
    """Fetch n controls with non-empty descriptions from ArangoDB."""
    client = ArangoClient(hosts=f"http://{ARANGO_HOST}:{ARANGO_PORT}")
    db = client.db(ARANGO_DB, username=ARANGO_USER, password=ARANGO_PASS)

    query = """
    FOR c IN sparta_controls
        FILTER c.description != null AND c.description != ""
        FILTER LENGTH(c.description) > 50
        SORT RAND()
        LIMIT @n
        RETURN {
            control_id: c.control_id,
            name: c.name,
            description: c.description
        }
    """
    cursor = db.aql.execute(query, bind_vars={"n": n})
    controls = list(cursor)
    print(f"Fetched {len(controls)} controls from ArangoDB")
    return controls


def scillm_complete(prompt: str, system: str = "") -> str:
    """Call /scillm via subprocess (anti-silo: uses scillm venv)."""
    # Build a small Python script that calls quick_completion
    script = f"""
import os, sys, json
os.environ.setdefault('LITELLM_DEFAULT_MODEL', 'gemini/gemini-2.5-flash')
sys.path.insert(0, {str(SCILLM_DIR)!r})
from batch import quick_completion
result = quick_completion(
    prompt={prompt!r},
    system={system!r},
    max_tokens=1024,
    temperature=0.3,
    timeout=60,
)
print(json.dumps({{"content": result}}))
"""
    try:
        result = subprocess.run(
            ["uv", "run", "--directory", str(SCILLM_DIR), "python", "-c", script],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if line.startswith("{"):
                    try:
                        data = json.loads(line)
                        return data.get("content", line)
                    except json.JSONDecodeError:
                        continue
            return result.stdout.strip()
        else:
            # Check stderr for useful info
            return f"ERROR: scillm exit {result.returncode}: {result.stderr[-500:]}"
    except subprocess.TimeoutExpired:
        return "ERROR: scillm timeout"
    except Exception as e:
        return f"ERROR: {e}"


def extract_lean_code(response: str) -> str:
    """Extract Lean4 code from LLM response."""
    patterns = [
        r'```lean4?\s*\n(.*?)```',
        r'```\s*\n(.*?)```',
    ]
    for pattern in patterns:
        matches = re.findall(pattern, response, re.DOTALL)
        if matches:
            return matches[0].strip()
    if any(kw in response for kw in ['theorem ', 'def ', 'structure ']):
        return response.strip()
    return response.strip()


def formalize_control(control: dict) -> dict:
    """Formalize a single control via /scillm."""
    control_id = control["control_id"]
    name = control.get("name", "unknown")
    desc = control.get("description", "")

    if len(desc) > 800:
        desc = desc[:800] + "..."

    prompt = f"""Formalize this security control into Lean4:

Control ID: {control_id}
Name: {name}
Description: {desc}

Produce a Lean4 formalization that captures the core security invariant."""

    response = scillm_complete(prompt, system=SYSTEM_PROMPT)

    if response.startswith("ERROR:"):
        return {
            "control_id": control_id,
            "name": name,
            "english_text": desc,
            "lean4_code": "",
            "llm_error": response,
        }

    lean4_code = extract_lean_code(response)
    return {
        "control_id": control_id,
        "name": name,
        "english_text": desc,
        "lean4_code": lean4_code,
        "llm_error": None,
    }


def classify_error(error: str) -> str:
    """Classify a compilation error into a category."""
    if not error:
        return "none"
    e = error.lower()
    if "unknown identifier" in e or "unknown constant" in e:
        return "unknown_identifier"
    if "type mismatch" in e:
        return "type_mismatch"
    if "expected token" in e or "unexpected token" in e:
        return "syntax_error"
    if "unknown tactic" in e:
        return "unknown_tactic"
    if "unsolved goals" in e:
        return "unsolved_goals"
    if "function expected" in e:
        return "function_expected"
    if "not a theorem" in e or "declaration" in e:
        return "declaration_error"
    if "import" in e:
        return "import_error"
    if "timeout" in e or "timed out" in e:
        return "timeout"
    if "failed to synthesize" in e:
        return "synthesis_failed"
    if "application type mismatch" in e:
        return "app_type_mismatch"
    return "other"


def main():
    print("=" * 70)
    print("PILOT FORMALIZATION: 100 SPARTA Controls -> Lean4")
    print("=" * 70)

    # Step 1: Fetch controls
    print("\n[1/4] Fetching controls from ArangoDB...")
    controls = fetch_controls(N_CONTROLS)
    if not controls:
        print("ERROR: No controls fetched!")
        sys.exit(1)

    # Step 2: Formalize via /scillm
    print(f"\n[2/4] Formalizing {len(controls)} controls via /scillm...")
    results = []
    for i, ctrl in enumerate(controls):
        t0 = time.monotonic()
        result = formalize_control(ctrl)
        elapsed = time.monotonic() - t0
        status = "OK" if result["lean4_code"] and not result["llm_error"] else "FAIL"
        print(f"  [{i+1:3d}/{len(controls)}] {ctrl['control_id']:20s} {status} ({elapsed:.1f}s)")
        results.append(result)

    # Filter out LLM failures
    formalized = [r for r in results if r["lean4_code"] and not r["llm_error"]]
    llm_fails = [r for r in results if r["llm_error"]]
    print(f"\n  LLM success: {len(formalized)}/{len(results)} ({len(llm_fails)} LLM failures)")

    # Step 3: Compile all via ParallelCompiler
    print(f"\n[3/4] Compiling {len(formalized)} formalizations (workers={N_WORKERS})...")
    if formalized:
        compiler = ParallelCompiler(
            n_workers=N_WORKERS,
            timeout=COMPILE_TIMEOUT,
            require="",  # No Mathlib -- bare Lean4 only
            lean_version=LEAN_VERSION,
        )
        codes = [r["lean4_code"] for r in formalized]

        BATCH_SIZE = 20
        all_compile_results = []
        for batch_start in range(0, len(codes), BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, len(codes))
            batch_codes = codes[batch_start:batch_end]
            print(f"  Compiling batch {batch_start+1}-{batch_end}...")
            batch_results = compiler.compile_batch(batch_codes)
            all_compile_results.extend(batch_results)

            batch_ok = sum(1 for r in batch_results if r.success)
            print(f"    -> {batch_ok}/{len(batch_results)} compiled OK")

        compiler.close()

        for result, compile_result in zip(formalized, all_compile_results):
            result["compiled"] = compile_result.success
            result["compiler_errors"] = compile_result.error if not compile_result.success else None
            result["compile_elapsed_ms"] = compile_result.elapsed_ms

    # Mark LLM failures
    for result in llm_fails:
        result["compiled"] = False
        result["compiler_errors"] = f"LLM error: {result['llm_error']}"
        result["compile_elapsed_ms"] = 0.0

    # Step 4: Write results
    print(f"\n[4/4] Writing results to {OUTPUT_PATH}...")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        for result in results:
            result.setdefault("compiled", False)
            result.setdefault("compiler_errors", None)
            result.setdefault("compile_elapsed_ms", 0.0)
            f.write(json.dumps(result) + "\n")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    total = len(results)
    compiled = sum(1 for r in results if r.get("compiled"))
    failed_llm = len(llm_fails)
    failed_compile = sum(1 for r in results if not r.get("compiled") and not r.get("llm_error"))

    print(f"  Total controls:      {total}")
    print(f"  LLM failures:        {failed_llm}")
    print(f"  Compiled OK:         {compiled}")
    print(f"  Compile failures:    {failed_compile}")
    print(f"  Compile rate:        {compiled/total*100:.1f}%")

    errors = [r.get("compiler_errors", "") or "" for r in results if not r.get("compiled")]
    if errors:
        categories = Counter(classify_error(e) for e in errors)
        print(f"\n  Top error categories:")
        for cat, count in categories.most_common(10):
            print(f"    {cat:25s} {count:4d} ({count/len(errors)*100:.1f}%)")

    print(f"\n  Output: {OUTPUT_PATH}")
    print("=" * 70)

    if compiled >= 10:
        print(f"\n  PASS: {compiled} >= 10 compiled pairs")
        return 0
    else:
        print(f"\n  BELOW TARGET: {compiled} < 10 compiled pairs")
        return 1


if __name__ == "__main__":
    sys.exit(main())
