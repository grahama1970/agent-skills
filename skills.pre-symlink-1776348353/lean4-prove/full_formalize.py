#!/usr/bin/env python3
"""
Full formalization: 500 records from formalization_batch.jsonl -> Lean4 -> compile check.

Uses /scillm (via subprocess to scillm venv) for LLM calls (NON-NEGOTIABLE).
Uses ParallelCompiler (lean-interact) for compilation with 20 workers.
Processes in batches of 50 with progress logging.
Writes ALL results (pass and fail) to data/full_formalization.jsonl.
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

from compiler import ParallelCompiler

# ── Config ────────────────────────────────────────────────────────────────
SCILLM_DIR = Path(__file__).resolve().parent.parent / "scillm"

N_RECORDS = 500
N_WORKERS = 20
COMPILE_TIMEOUT = 60.0
LEAN_VERSION = "v4.16.0"
LLM_BATCH_SIZE = 50       # Progress logging batch size for LLM calls
COMPILE_BATCH_SIZE = 50   # Compilation batch size

INPUT_PATH = Path(__file__).resolve().parent / "data" / "formalization_batch.jsonl"
OUTPUT_PATH = Path(__file__).resolve().parent / "data" / "full_formalization.jsonl"

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


def load_records(n: int = N_RECORDS) -> list[dict]:
    """Load first n records from formalization_batch.jsonl."""
    records = []
    with open(INPUT_PATH) as f:
        for i, line in enumerate(f):
            if i >= n:
                break
            line = line.strip()
            if line:
                records.append(json.loads(line))
    print(f"Loaded {len(records)} records from {INPUT_PATH}")
    return records


def scillm_complete(prompt: str, system: str = "") -> str:
    """Call /scillm via subprocess (anti-silo: uses scillm venv)."""
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


def formalize_record(record: dict) -> dict:
    """Formalize a single record via /scillm."""
    key = record.get("_key", "unknown")
    name = record.get("name", "unknown")
    text = record.get("text", "")

    # Truncate long descriptions
    desc = text
    if len(desc) > 800:
        desc = desc[:800] + "..."

    prompt = f"""Formalize this security control into Lean4:

Control ID: {key}
Name: {name}
Description: {desc}

Produce a Lean4 formalization that captures the core security invariant."""

    response = scillm_complete(prompt, system=SYSTEM_PROMPT)

    if response.startswith("ERROR:"):
        return {
            "control_id": key,
            "name": name,
            "english_text": text,
            "lean4_code": "",
            "llm_error": response,
            "source_framework": record.get("source_framework", ""),
            "control_type": record.get("control_type", ""),
        }

    lean4_code = extract_lean_code(response)
    return {
        "control_id": key,
        "name": name,
        "english_text": text,
        "lean4_code": lean4_code,
        "llm_error": None,
        "source_framework": record.get("source_framework", ""),
        "control_type": record.get("control_type", ""),
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
    t_start = time.monotonic()

    print("=" * 70)
    print(f"FULL FORMALIZATION: {N_RECORDS} records -> Lean4")
    print(f"  Workers: {N_WORKERS}  |  LLM batch: {LLM_BATCH_SIZE}  |  Compile batch: {COMPILE_BATCH_SIZE}")
    print("=" * 70)

    # Step 1: Load records
    print("\n[1/4] Loading records from formalization_batch.jsonl...")
    records = load_records(N_RECORDS)
    if not records:
        print("ERROR: No records loaded!")
        sys.exit(1)

    # Step 2: Formalize via /scillm in batches of LLM_BATCH_SIZE
    print(f"\n[2/4] Formalizing {len(records)} records via /scillm...")
    results = []
    for batch_idx in range(0, len(records), LLM_BATCH_SIZE):
        batch_end = min(batch_idx + LLM_BATCH_SIZE, len(records))
        batch_records = records[batch_idx:batch_end]
        batch_num = batch_idx // LLM_BATCH_SIZE + 1
        total_batches = (len(records) + LLM_BATCH_SIZE - 1) // LLM_BATCH_SIZE

        print(f"\n  --- LLM Batch {batch_num}/{total_batches} (records {batch_idx+1}-{batch_end}) ---")
        batch_t0 = time.monotonic()
        batch_ok = 0

        for i, rec in enumerate(batch_records):
            t0 = time.monotonic()
            result = formalize_record(rec)
            elapsed = time.monotonic() - t0
            status = "OK" if result["lean4_code"] and not result["llm_error"] else "FAIL"
            if status == "OK":
                batch_ok += 1
            global_idx = batch_idx + i + 1
            print(f"  [{global_idx:4d}/{len(records)}] {result['control_id']:30s} {status} ({elapsed:.1f}s)")
            results.append(result)

        batch_elapsed = time.monotonic() - batch_t0
        print(f"  Batch {batch_num} done: {batch_ok}/{len(batch_records)} OK in {batch_elapsed:.1f}s")

        # Running totals
        total_ok = sum(1 for r in results if r["lean4_code"] and not r["llm_error"])
        total_fail = len(results) - total_ok
        print(f"  Running total: {total_ok} OK / {total_fail} LLM-fail / {len(results)} processed")

    # Filter out LLM failures
    formalized = [r for r in results if r["lean4_code"] and not r["llm_error"]]
    llm_fails = [r for r in results if r["llm_error"]]
    print(f"\n  LLM summary: {len(formalized)}/{len(results)} success ({len(llm_fails)} LLM failures)")

    # Step 3: Compile all via ParallelCompiler with 20 workers
    print(f"\n[3/4] Compiling {len(formalized)} formalizations (workers={N_WORKERS})...")
    if formalized:
        compiler = ParallelCompiler(
            n_workers=N_WORKERS,
            timeout=COMPILE_TIMEOUT,
            require="",  # No Mathlib -- bare Lean4 only
            lean_version=LEAN_VERSION,
        )
        codes = [r["lean4_code"] for r in formalized]

        all_compile_results = []
        for batch_start in range(0, len(codes), COMPILE_BATCH_SIZE):
            batch_end = min(batch_start + COMPILE_BATCH_SIZE, len(codes))
            batch_codes = codes[batch_start:batch_end]
            batch_num = batch_start // COMPILE_BATCH_SIZE + 1
            total_compile_batches = (len(codes) + COMPILE_BATCH_SIZE - 1) // COMPILE_BATCH_SIZE

            print(f"  Compile batch {batch_num}/{total_compile_batches} ({batch_start+1}-{batch_end})...", end=" ", flush=True)
            bt0 = time.monotonic()
            batch_results = compiler.compile_batch(batch_codes)
            bt_elapsed = time.monotonic() - bt0
            all_compile_results.extend(batch_results)

            batch_ok = sum(1 for r in batch_results if r.success)
            total_compiled = sum(1 for r in all_compile_results if r.success)
            print(f"{batch_ok}/{len(batch_results)} OK ({bt_elapsed:.1f}s) | Running: {total_compiled}/{len(all_compile_results)}")

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

    # Step 4: Write ALL results
    print(f"\n[4/4] Writing results to {OUTPUT_PATH}...")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        for result in results:
            result.setdefault("compiled", False)
            result.setdefault("compiler_errors", None)
            result.setdefault("compile_elapsed_ms", 0.0)
            f.write(json.dumps(result) + "\n")

    # Summary
    t_total = time.monotonic() - t_start
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    total = len(results)
    compiled = sum(1 for r in results if r.get("compiled"))
    failed_llm = len(llm_fails)
    failed_compile = sum(1 for r in results if not r.get("compiled") and not r.get("llm_error"))

    print(f"  Total records:       {total}")
    print(f"  LLM failures:        {failed_llm}")
    print(f"  Compiled OK:         {compiled}")
    print(f"  Compile failures:    {failed_compile}")
    print(f"  Compile rate:        {compiled/total*100:.1f}%")
    print(f"  Elapsed time:        {t_total:.1f}s ({t_total/60:.1f}min)")
    print(f"  Throughput:          {total/t_total*60:.1f} records/min")

    # Error breakdown
    errors = [r.get("compiler_errors", "") or "" for r in results if not r.get("compiled")]
    if errors:
        categories = Counter(classify_error(e) for e in errors)
        print(f"\n  Error categories ({len(errors)} total failures):")
        for cat, count in categories.most_common(10):
            print(f"    {cat:25s} {count:4d} ({count/len(errors)*100:.1f}%)")

    # Framework breakdown
    fw_stats = {}
    for r in results:
        fw = r.get("source_framework", "unknown")
        if fw not in fw_stats:
            fw_stats[fw] = {"total": 0, "compiled": 0}
        fw_stats[fw]["total"] += 1
        if r.get("compiled"):
            fw_stats[fw]["compiled"] += 1
    print(f"\n  By framework:")
    for fw, stats in sorted(fw_stats.items()):
        rate = stats["compiled"] / stats["total"] * 100 if stats["total"] > 0 else 0
        print(f"    {fw:20s} {stats['compiled']:4d}/{stats['total']:4d} ({rate:.1f}%)")

    print(f"\n  Output: {OUTPUT_PATH}")
    print("=" * 70)

    if compiled >= 450:
        print(f"\n  PASS: {compiled} >= 450 compiled (90% of 500)")
        return 0
    else:
        print(f"\n  BELOW TARGET: {compiled} < 450 compiled (need 90% of 500)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
