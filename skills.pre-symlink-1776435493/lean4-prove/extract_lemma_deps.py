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
import os
import typer
import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import httpx

# Removed: memory accessed via httpx to Unix socket (see _memory_cmd)
def _memory_cmd(args: list, timeout: int = 60) -> dict:
    """Call embry-memory daemon via Unix socket HTTP API."""
    str_args = [str(a) for a in args]
    subcmd = str_args[0] if str_args else ""
    rest = str_args[1:]

    # Parse CLI-style flags into a dict
    params: dict = {}
    list_keys: dict[str, list] = {}
    i = 0
    while i < len(rest):
        if rest[i].startswith("--"):
            key = rest[i][2:].replace("-", "_")
            if i + 1 < len(rest) and not rest[i + 1].startswith("--"):
                val = rest[i + 1]
                if key in ("tag", "tags", "collections"):
                    list_keys.setdefault(key, []).append(val)
                else:
                    params[key] = val
                i += 2
            else:
                params[key] = True
                i += 1
        else:
            i += 1
    for k, v in list_keys.items():
        params[k] = v

    transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
    with httpx.Client(transport=transport, base_url="http://localhost", timeout=float(timeout)) as client:
        if subcmd == "recall":
            body = {"q": params.get("q", params.get("query", "")), "k": int(params.get("k", params.get("limit", 5)))}
            for opt in ("scope", "threshold"):
                if opt in params:
                    body[opt] = float(params[opt]) if opt == "threshold" else params[opt]
            if "collections" in params:
                c = params["collections"]
                body["collections"] = c if isinstance(c, list) else [c]
            if "tags" in params:
                t = params["tags"]
                body["tags"] = t if isinstance(t, list) else [t]
            resp = client.post("/recall", json=body)
        elif subcmd == "learn":
            body = {"problem": params.get("problem", ""), "solution": params.get("solution", "")}
            if "scope" in params:
                body["scope"] = params["scope"]
            if "collection" in params:
                body["scope"] = params["collection"]
            if "tag" in params:
                body["tags"] = params["tag"] if isinstance(params["tag"], list) else [params["tag"]]
            if "tags" in params:
                body["tags"] = params["tags"] if isinstance(params["tags"], list) else [params["tags"]]
            if "json" in params:
                body.update(json.loads(params["json"]))
            resp = client.post("/learn", json=body)
        elif subcmd == "count":
            coll = params.get("collection", params.get("scope", "lessons"))
            # Use /list endpoint instead of raw AQL (all AQL must be in memory project)
            list_resp = client.post("/list", json={"collection": coll, "limit": 1})
            list_resp.raise_for_status()
            return {"documents": [list_resp.json().get("total", 0)]}
        elif subcmd == "sample":
            body = {"collection": params.get("collection", "lessons"), "limit": int(params.get("limit", 10))}
            if "fields" in params:
                body["return_fields"] = [f.strip() for f in str(params["fields"]).split(",")]
            resp = client.post("/list", json=body)
        elif subcmd == "tag":
            if "doc" in params:
                doc = json.loads(params["doc"]) if isinstance(params["doc"], str) else params["doc"]
                resp = client.post("/upsert", json={"collection": params.get("collection", "lessons"), "documents": [doc]})
            elif "key" in params:
                tags_val = params.get("tags", "[]")
                tags_list = json.loads(tags_val) if isinstance(tags_val, str) else tags_val
                field = params.get("field", "tags")
                resp = client.post("/upsert", json={"collection": params.get("collection", "lessons"), "documents": [{"_key": params["key"], field: tags_list}]})
            else:
                raise RuntimeError(f"Unsupported tag args: {rest}")
        elif subcmd == "search":
            body = {"q": params.get("q", params.get("query", "")), "k": int(params.get("limit", 10))}
            if "collection" in params:
                body["collections"] = [params["collection"]]
            if "scope" in params:
                body["scope"] = params["scope"]
            resp = client.post("/recall", json=body)
        else:
            raise RuntimeError(f"Unsupported memory subcommand via httpx: {subcmd}")
        resp.raise_for_status()
        return resp.json()

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
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )

        # Compile with JSON output
        result = subprocess.run(
            ["docker", "exec", "-w", "/workspace/mathlib_project", container,
             "lake", "env", "lean", "--json", temp_file],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
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
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
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


def update_theorem_deps(key: str, lemma_deps: List[str]) -> bool:
    """Update theorem with extracted dependencies via /memory learn."""
    try:
        doc = {
            "_key": key,
            "lemma_deps": lemma_deps,
            "deps_extracted_at": datetime.utcnow().isoformat(),
        }
        _memory_cmd([
            "learn",
            "--problem", f"deps_update:{key}",
            "--solution", json.dumps(doc),
            "--scope", "lean4",
        ])
        return True
    except RuntimeError as e:
        print(f"  Failed to update {key}: {e}", file=sys.stderr)
        return False


def create_dependency_edges(theorem_key: str, lemma_deps: List[str]):
    """Create edges from theorem to its dependencies via /memory learn."""
    if not lemma_deps:
        return

    for dep in lemma_deps:
        edge_doc = {
            "_from": f"lean_theorems/{theorem_key}",
            "_to": f"mathlib/{dep}",
            "type": "uses_lemma",
            "lemma": dep,
            "weight": 1.0,
        }
        try:
            _memory_cmd([
                "learn",
                "--problem", f"edge:dep:{theorem_key}:{dep}",
                "--solution", json.dumps(edge_doc),
                "--scope", "lean4",
            ])
        except RuntimeError as e:
            print(f"  Edge creation failed for {dep}: {e}", file=sys.stderr)


app = typer.Typer(help="Extract lemma dependencies from proven theorems")


@app.command()
def main(
    limit: int = typer.Option(0, help=""),
    workers: int = typer.Option(1, help="Parallel workers"),
    container: str = typer.Option("lean_runner", help="Docker container"),
    timeout: int = typer.Option(30, help="Compile timeout per theorem"),
    skip_existing: bool = typer.Option(False, help="Skip theorems with deps"),
    do_create_edges: bool = typer.Option(False, "--create-edges", help="Create dependency edges"),
    batch_size: int = typer.Option(100, help="Progress report interval"),
):
    print("Using /memory subprocess for all DB access")

    # Query theorems via /memory recall
    query = "status:ok OR status:proven"
    if skip_existing:
        query += " lemma_deps:null"

    try:
        theorems = _memory_cmd([
            "recall", "--q", query,
            "--collections", "lean_theorems",
        ], timeout=120)
    except RuntimeError as e:
        print(f"Failed to fetch theorems: {e}", file=sys.stderr)
        raise typer.Exit(1)

    if not isinstance(theorems, list):
        theorems = theorems.get("results", [])

    if limit > 0:
        theorems = theorems[:limit]

    print(f"Processing {len(theorems)} theorems...")

    # Stats
    success = 0
    failed = 0
    total_deps = 0
    start_time = time.time()

    def process_one(thm):
        return compile_and_extract(thm, container=container, timeout=timeout)

    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(process_one, t): t for t in theorems}

            for i, future in enumerate(as_completed(futures)):
                result = future.result()

                if result["success"]:
                    success += 1
                    deps = result["lemma_deps"] or []
                    total_deps += len(deps)
                    update_theorem_deps(result["_key"], deps)
                    if do_create_edges:
                        create_dependency_edges(result["_key"], deps)
                else:
                    failed += 1

                if (i + 1) % batch_size == 0:
                    elapsed = time.time() - start_time
                    rate = (i + 1) / elapsed
                    eta = (len(theorems) - i - 1) / rate / 60
                    print(f"  Progress: {i+1}/{len(theorems)} "
                          f"({success} ok, {failed} failed) "
                          f"ETA: {eta:.1f} min")
    else:
        for i, thm in enumerate(theorems):
            result = process_one(thm)

            if result["success"]:
                success += 1
                deps = result["lemma_deps"] or []
                total_deps += len(deps)
                update_theorem_deps(result["_key"], deps)
                if do_create_edges:
                    create_dependency_edges(result["_key"], deps)
            else:
                failed += 1
                if limit <= 10:
                    print(f"  {result['_key']}: {result['error']}")

            if (i + 1) % batch_size == 0:
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
    app()
