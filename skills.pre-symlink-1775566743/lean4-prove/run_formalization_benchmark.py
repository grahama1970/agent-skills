#!/usr/bin/env python3
"""
Task 8: Benchmark the lean4_autoformalization collection.

Checks: dedup, framework coverage, tactic analysis, structure validation,
        and re-compilation of 10 random samples.

Run with: cd <skill-dir>/lean4-prove && uv run python run_formalization_benchmark.py
"""
from __future__ import annotations

import hashlib
import json
import random
import time
from collections import Counter
from pathlib import Path

from arango import ArangoClient

# ---------------------------------------------------------------------------
# 1. Load all documents
# ---------------------------------------------------------------------------
client = ArangoClient(hosts="http://localhost:8529")
db = client.db("memory", username="root", password="openSesame")
col = db.collection("lean4_autoformalization")

docs = list(col.all())
total_pairs = len(docs)
print(f"Loaded {total_pairs} documents from lean4_autoformalization")

# ---------------------------------------------------------------------------
# 2. Check 1 — Deduplication
# ---------------------------------------------------------------------------
hashes: dict[str, list[str]] = {}
for d in docs:
    h = hashlib.sha256(d.get("lean4_statement", "").encode()).hexdigest()
    hashes.setdefault(h, []).append(d["_key"])

unique_statements = len(hashes)
duplicates = {h: keys for h, keys in hashes.items() if len(keys) > 1}
duplicate_count = sum(len(v) - 1 for v in duplicates.values())
duplicate_examples = []
for h, keys in list(duplicates.items())[:5]:
    duplicate_examples.append({"hash": h[:16], "keys": keys})

print(f"Check 1 — Dedup: {unique_statements} unique, {duplicate_count} duplicates")

# ---------------------------------------------------------------------------
# 3. Check 2 — Framework Coverage
# ---------------------------------------------------------------------------
framework_counts: Counter = Counter()
for d in docs:
    fw = d.get("source_framework", "unknown")
    framework_counts[fw] += 1

# Get total controls per framework from sparta_controls if available
framework_totals: dict[str, int] = {}
try:
    if db.has_collection("sparta_controls"):
        cursor = db.aql.execute(
            "FOR c IN sparta_controls COLLECT fw = c.source_framework WITH COUNT INTO cnt RETURN {fw, cnt}"
        )
        for row in cursor:
            framework_totals[row["fw"]] = row["cnt"]
except Exception as e:
    print(f"  (could not get framework totals: {e})")

framework_coverage: dict[str, dict] = {}
for fw, count in framework_counts.most_common():
    entry: dict = {"formalized": count}
    total_in_fw = framework_totals.get(fw)
    if total_in_fw:
        entry["total_controls"] = total_in_fw
        entry["coverage_pct"] = round(100.0 * count / total_in_fw, 2)
    framework_coverage[fw] = entry

print(f"Check 2 — Framework coverage: {dict(framework_counts)}")

# ---------------------------------------------------------------------------
# 4. Check 3 — Tactic Analysis
# ---------------------------------------------------------------------------
sorry_count = 0
tactic_counter: Counter = Counter()
tactic_counts_per_doc: list[int] = []

for d in docs:
    stmt = d.get("lean4_statement", "")
    tactics = d.get("tactics", [])
    tactic_counts_per_doc.append(len(tactics))
    for t in tactics:
        tactic_counter[t] += 1
    if "sorry" in stmt:
        sorry_count += 1

avg_tactics = round(sum(tactic_counts_per_doc) / max(len(tactic_counts_per_doc), 1), 2)
tactic_distribution = dict(tactic_counter.most_common(30))

print(f"Check 3 — Tactics: sorry_count={sorry_count}, avg_tactics={avg_tactics}")

# ---------------------------------------------------------------------------
# 5. Check 4 — Structure Validation
# ---------------------------------------------------------------------------
empty_english = 0
empty_lean4 = 0
not_verified = 0
lean4_lengths: list[int] = []

for d in docs:
    if not d.get("english", "").strip():
        empty_english += 1
    stmt = d.get("lean4_statement", "")
    if not stmt.strip():
        empty_lean4 += 1
    lean4_lengths.append(len(stmt))
    if not d.get("verified", False):
        not_verified += 1

avg_lean4_length = round(sum(lean4_lengths) / max(len(lean4_lengths), 1), 1)

print(f"Check 4 — Structure: empty_english={empty_english}, empty_lean4={empty_lean4}, not_verified={not_verified}, avg_len={avg_lean4_length}")

# ---------------------------------------------------------------------------
# 6. Check 5 — Re-compile 10 random samples
# ---------------------------------------------------------------------------
from compiler import ParallelCompiler

random.seed(42)
samples = random.sample(docs, min(10, len(docs)))

recompile_results: list[dict] = []
recompile_pass = 0

stmts = [s.get("lean4_statement", "") for s in samples]

print("Check 5 — Compiling 10 random samples...")
compiler = ParallelCompiler(n_workers=5, timeout=60.0, lean_version="v4.16.0")
results = compiler.compile_batch(stmts)
compiler.close()

for sample, result in zip(samples, results):
    entry = {
        "key": sample["_key"],
        "source_key": sample.get("source_key", ""),
        "compiled": result.success,
        "error": result.error,
    }
    recompile_results.append(entry)
    if result.success:
        recompile_pass += 1
    status = "PASS" if result.success else "FAIL"
    print(f"  {sample['_key']}: {status}")

recompile_rate = round(recompile_pass / max(len(samples), 1), 2)
print(f"Check 5 — Recompile: {recompile_pass}/{len(samples)} passed ({recompile_rate})")

# ---------------------------------------------------------------------------
# 7. Compute compile_rate from original data
# ---------------------------------------------------------------------------
verified_count = sum(1 for d in docs if d.get("verified", False))
compile_rate = round(verified_count / max(total_pairs, 1), 4)

# ---------------------------------------------------------------------------
# 8. Build recommendation
# ---------------------------------------------------------------------------
issues = []
if duplicate_count > 0:
    issues.append(f"{duplicate_count} duplicate lean4_statements found — deduplicate before training")
if sorry_count > 0:
    issues.append(f"{sorry_count} formalizations use 'sorry' — these have unproven subgoals")
if empty_english > 0 or empty_lean4 > 0:
    issues.append(f"{empty_english} empty english, {empty_lean4} empty lean4_statement fields")
if not_verified > 0:
    issues.append(f"{not_verified} documents with verified != true")
if recompile_pass < len(samples):
    issues.append(f"Recompilation: {recompile_pass}/{len(samples)} passed — some stored code may not compile")

if not issues:
    recommendation = (
        f"All {total_pairs} formalization pairs pass structural and compilation checks. "
        f"Dataset covers {len(framework_coverage)} frameworks with {unique_statements} unique statements. "
        f"Average {avg_tactics} tactics per proof, {avg_lean4_length:.0f} chars per Lean4 statement. "
        "Ready for GRPO training and round-trip evaluation (LLM-based round-trip deferred)."
    )
else:
    recommendation = "Issues found: " + "; ".join(issues) + ". Address before training."

# ---------------------------------------------------------------------------
# 9. Write report
# ---------------------------------------------------------------------------
LEAN4_PROVE_DIR = Path(__file__).resolve().parent
report = {
    "total_pairs": total_pairs,
    "compile_rate": compile_rate,
    "unique_statements": unique_statements,
    "duplicate_count": duplicate_count,
    "duplicate_examples": duplicate_examples,
    "sorry_count": sorry_count,
    "framework_coverage": framework_coverage,
    "tactic_distribution": tactic_distribution,
    "avg_tactics_per_formalization": avg_tactics,
    "avg_lean4_length": avg_lean4_length,
    "structure_validation": {
        "empty_english": empty_english,
        "empty_lean4": empty_lean4,
        "not_verified": not_verified,
    },
    "recompile_check": {
        "samples": len(samples),
        "passed": recompile_pass,
        "rate": recompile_rate,
        "details": recompile_results,
    },
    "round_trip_score": None,  # Requires LLM, deferred
    "recommendation": recommendation,
    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
}

out_path = LEAN4_PROVE_DIR / "data" / "formalization_report.json"
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(report, indent=2))
print(f"\nReport written to {out_path}")
print(f"\nRecommendation: {recommendation}")
