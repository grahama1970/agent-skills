#!/usr/bin/env python3
"""
Batch extract lemma dependencies from proven Lean4 theorems.

Compiles each theorem and runs #print to get the proof term,
then extracts referenced lemmas to build a dependency graph.

Usage:
    # Full extraction (resumable)
    python extract_lemma_deps.py

    # Limit for testing
    python extract_lemma_deps.py --limit 100

    # Parallel with multiple containers
    python extract_lemma_deps.py --workers 4

    # Skip already processed
    python extract_lemma_deps.py --skip-existing
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List, Dict, Any, Optional

# Load .env
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True))
except ImportError:
    pass


def get_db():
    """Get ArangoDB connection."""
    from arango import ArangoClient
    url = os.getenv("ARANGO_URL", "http://127.0.0.1:8529")
    db_name = os.getenv("ARANGO_DB", "memory")
    user = os.getenv("ARANGO_USER", "root")
    password = os.getenv("ARANGO_PASS", "")
    client = ArangoClient(hosts=url)
    return client.db(db_name, username=user, password=password)


def parse_proof_term(proof_text: str) -> List[str]:
    """Extract lemma references from a Lean4 proof term."""
    # Patterns for Lean4 qualified names
    patterns = [
        r'\b([A-Z][a-zA-Z0-9_]*\.[a-zA-Z0-9_.]+)\b',  # Qualified: Nat.add_comm
        r'\b([a-z][a-z0-9_]+(?:\.[a-zA-Z0-9_]+)*)\b',  # Local or qualified lowercase
    ]

    all_refs = set()
    for pattern in patterns:
        all_refs.update(re.findall(pattern, proof_text))

    # Filter out noise
    exclude = {
        # Core Lean constructors
        'Eq.mpr', 'Eq.refl', 'Eq.trans', 'Eq.symm', 'Eq.subst', 'Eq.mp',
        'id', 'rfl', 'trivial', 'absurd',
        # Keywords/syntax
        'fun', 'let', 'by', 'where', 'in', 'do', 'match', 'with',
        # Bound variables
        'n', 'm', 'h', 'x', 'y', 'a', 'b', 'p', 'q', 'k', 'i', 'j',
        'h0', 'h1', 'h2', 'h3', 'ih', 'this',
        # Type names
        'Nat', 'Int', 'Bool', 'List', 'Option', 'Type', 'Prop', 'Sort',
        'True', 'False', 'And', 'Or', 'Not', 'Iff',
    }

    deps = []
    for ref in all_refs:
        if ref in exclude:
            continue
        if ref.startswith('_'):
            continue
        # Keep qualified names or meaningful snake_case
        if '.' in ref or (len(ref) > 3 and '_' in ref):
            deps.append(ref)

    return sorted(set(deps))


def extract_theorem_name(code: str) -> Optional[str]:
    """Extract theorem/lemma name from Lean code."""
    patterns = [
        r'theorem\s+(\w+)',
        r'lemma\s+(\w+)',
        r'def\s+(\w+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, code)
        if match:
            return match.group(1)
    return None


def compile_and_extract(
    theorem: Dict[str, Any],
    container: str = "lean_runner",
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    Compile a theorem and extract its dependencies.

    Returns:
        {
            "_key": theorem key,
            "success": bool,
            "lemma_deps": [...] or None,
            "error": error message or None,
            "compile_time": seconds
        }
    """
    key = theorem["_key"]
    start = time.time()

    # Build full code
    header = theorem.get("header", "") or ""
    statement = theorem.get("formal_statement", "") or ""
    proof = theorem.get("formal_proof", "") or ""

    # Skip if no real proof
    if not proof or proof.strip() == "sorry" or len(proof.strip()) < 5:
        return {
            "_key": key,
            "success": False,
            "lemma_deps": None,
            "error": "No proof or sorry proof",
            "compile_time": 0,
        }

    # Handle different proof formats
    # V1/V2 DeepSeek format: statement ends with `:= by` in tactic mode
    if statement and proof:
        # Check if statement already has := by
        if statement.rstrip().endswith(":= by"):
            code = f"{header}\n\n{statement}\n{proof}"
        elif ":= by" in statement:
            code = f"{header}\n\n{statement}\n{proof}"
        elif ":=" in statement:
            code = f"{header}\n\n{statement}\n{proof}"
        else:
            # Statement doesn't have := by, add it
            code = f"{header}\n\n{statement} := by\n{proof}"
    elif theorem.get("full_code"):
        code = theorem["full_code"]
    elif theorem.get("lean_code"):
        code = theorem["lean_code"]
    else:
        return {
            "_key": key,
            "success": False,
            "lemma_deps": None,
            "error": "No code available",
            "compile_time": 0,
        }

    # Extract theorem name
    thm_name = extract_theorem_name(code)
    if not thm_name:
        thm_name = "main_theorem"
        # Wrap code if no theorem name found
        if "theorem" not in code and "lemma" not in code:
            return {
                "_key": key,
                "success": False,
                "lemma_deps": None,
                "error": "Could not find theorem name",
                "compile_time": 0,
            }

    # Add #print command
    code_with_print = f"{code}\n\n#print {thm_name}"

    # Write to container
    temp_file = f"/tmp/dep_extract_{key}.lean"
    try:
        subprocess.run(
            ["docker", "exec", container, "bash", "-c", f"cat > {temp_file}"],
            input=code_with_print,
            text=True,
            check=True,
            timeout=10,
        )

        # Compile with JSON output
        result = subprocess.run(
            ["docker", "exec", "-w", "/workspace/mathlib_project", container,
             "lake", "env", "lean", "--json", temp_file],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        compile_time = time.time() - start

        # Parse JSON output for #print result
        lemma_deps = None
        for line in result.stdout.split('\n'):
            if not line.strip():
                continue
            try:
                msg = json.loads(line)
                if msg.get('severity') == 'information':
                    data = msg.get('data', '')
                    if thm_name in data and ':=' in data:
                        lemma_deps = parse_proof_term(data)
                        break
            except json.JSONDecodeError:
                continue

        # Cleanup
        subprocess.run(
            ["docker", "exec", container, "rm", "-f", temp_file],
            capture_output=True,
        )

        if result.returncode != 0 and lemma_deps is None:
            # Try to extract error
            error = None
            for line in result.stdout.split('\n'):
                try:
                    msg = json.loads(line)
                    if msg.get('severity') == 'error':
                        error = msg.get('data', '')[:200]
                        break
                except json.JSONDecodeError:
                    pass
            return {
                "_key": key,
                "success": False,
                "lemma_deps": None,
                "error": error or "Compilation failed",
                "compile_time": compile_time,
            }

        return {
            "_key": key,
            "success": True,
            "lemma_deps": lemma_deps or [],
            "error": None,
            "compile_time": compile_time,
        }

    except subprocess.TimeoutExpired:
        return {
            "_key": key,
            "success": False,
            "lemma_deps": None,
            "error": f"Timeout after {timeout}s",
            "compile_time": timeout,
        }
    except Exception as e:
        return {
            "_key": key,
            "success": False,
            "lemma_deps": None,
            "error": str(e)[:200],
            "compile_time": time.time() - start,
        }


def update_theorem_deps(db, key: str, lemma_deps: List[str]) -> bool:
    """Update theorem with extracted dependencies."""
    try:
        db.collection("lean_theorems").update({
            "_key": key,
            "lemma_deps": lemma_deps,
            "deps_extracted_at": datetime.utcnow().isoformat(),
        })
        return True
    except Exception as e:
        print(f"  Failed to update {key}: {e}", file=sys.stderr)
        return False


def create_dependency_edges(db, theorem_key: str, lemma_deps: List[str]):
    """Create edges from theorem to its dependencies."""
    if not lemma_deps:
        return

    # Ensure edge collection exists
    if not db.has_collection("lesson_edges"):
        db.create_collection("lesson_edges", edge=True)

    edge_col = db.collection("lesson_edges")

    edges = []
    for dep in lemma_deps:
        # Create edge key from theorem and dep
        edge_key = f"dep_{theorem_key}_{dep.replace('.', '_')}"[:250]
        edges.append({
            "_key": edge_key,
            "_from": f"lean_theorems/{theorem_key}",
            "_to": f"mathlib/{dep}",  # Virtual node for Mathlib refs
            "type": "uses_lemma",
            "lemma": dep,
            "weight": 1.0,
        })

    if edges:
        edge_col.import_bulk(edges, on_duplicate="ignore")


def main():
    parser = argparse.ArgumentParser(description="Extract lemma dependencies from proven theorems")
    parser.add_argument("--limit", type=int, default=0, help="Limit theorems to process (0=all)")
    parser.add_argument("--workers", type=int, default=1, help="Parallel workers")
    parser.add_argument("--container", default="lean_runner", help="Docker container")
    parser.add_argument("--timeout", type=int, default=30, help="Compile timeout per theorem")
    parser.add_argument("--skip-existing", action="store_true", help="Skip theorems with deps")
    parser.add_argument("--create-edges", action="store_true", help="Create dependency edges")
    parser.add_argument("--batch-size", type=int, default=100, help="Progress report interval")

    args = parser.parse_args()

    db = get_db()
    print(f"Connected to ArangoDB: {db.name}")

    # Query theorems
    if args.skip_existing:
        aql = """
        FOR t IN lean_theorems
        FILTER t.status IN ["proven", "ok"]
        FILTER t.lemma_deps == null
        LIMIT @limit
        RETURN t
        """
    else:
        aql = """
        FOR t IN lean_theorems
        FILTER t.status IN ["proven", "ok"]
        LIMIT @limit
        RETURN t
        """

    limit = args.limit if args.limit > 0 else 1000000
    theorems = list(db.aql.execute(aql, bind_vars={"limit": limit}))
    print(f"Processing {len(theorems)} theorems...")

    # Stats
    success = 0
    failed = 0
    total_deps = 0
    start_time = time.time()

    def process_one(thm):
        return compile_and_extract(thm, container=args.container, timeout=args.timeout)

    if args.workers > 1:
        # Parallel processing
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(process_one, t): t for t in theorems}

            for i, future in enumerate(as_completed(futures)):
                result = future.result()

                if result["success"]:
                    success += 1
                    deps = result["lemma_deps"] or []
                    total_deps += len(deps)
                    update_theorem_deps(db, result["_key"], deps)
                    if args.create_edges:
                        create_dependency_edges(db, result["_key"], deps)
                else:
                    failed += 1

                if (i + 1) % args.batch_size == 0:
                    elapsed = time.time() - start_time
                    rate = (i + 1) / elapsed
                    eta = (len(theorems) - i - 1) / rate / 60
                    print(f"  Progress: {i+1}/{len(theorems)} "
                          f"({success} ok, {failed} failed) "
                          f"ETA: {eta:.1f} min")
    else:
        # Sequential processing
        for i, thm in enumerate(theorems):
            result = process_one(thm)

            if result["success"]:
                success += 1
                deps = result["lemma_deps"] or []
                total_deps += len(deps)
                update_theorem_deps(db, result["_key"], deps)
                if args.create_edges:
                    create_dependency_edges(db, result["_key"], deps)
            else:
                failed += 1
                if args.limit <= 10:  # Show errors for small batches
                    print(f"  {result['_key']}: {result['error']}")

            if (i + 1) % args.batch_size == 0:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed
                eta = (len(theorems) - i - 1) / rate / 60
                print(f"  Progress: {i+1}/{len(theorems)} "
                      f"({success} ok, {failed} failed) "
                      f"ETA: {eta:.1f} min")

    elapsed = time.time() - start_time
    print(f"\nDone in {elapsed/60:.1f} minutes")
    print(f"  Success: {success}")
    print(f"  Failed: {failed}")
    print(f"  Total deps extracted: {total_deps}")
    print(f"  Avg deps per theorem: {total_deps/max(success,1):.1f}")


if __name__ == "__main__":
    main()
