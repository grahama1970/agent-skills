#!/usr/bin/env python3
"""
lean4-prove: Generate and verify Lean4 proofs using Claude CLI.

Takes a requirement + optional tactics + optional persona, generates proof
candidates via Claude, compiles each in Docker, retries with error feedback.

Supports retrieval-augmented generation from the DeepSeek-Prover-V1 dataset
stored in ArangoDB (via memory skill).
"""
import json
import os
import subprocess
import sys
import time
import concurrent.futures
from pathlib import Path
from typing import Optional, List, Dict, Any

# Default model for theorem proving
DEFAULT_MODEL = os.getenv("LEAN4_PROVE_MODEL", "opus")

# Retrieval settings
RETRIEVAL_ENABLED = os.getenv("LEAN4_RETRIEVAL", "1") != "0"
RETRIEVAL_K = int(os.getenv("LEAN4_RETRIEVAL_K", "5"))

# Learn-back settings (store new proofs for corpus evolution)
LEARN_ENABLED = os.getenv("LEAN4_LEARN", "1") != "0"


def get_arango_db() -> Any:
    """Get ArangoDB connection for retrieval."""
    try:
        from arango import ArangoClient
        url = os.getenv("ARANGO_URL", "http://127.0.0.1:8529")
        # Use LEAN4_ARANGO_DB if set, otherwise fall back to ARANGO_DB, default to 'memory'
        # Note: 'memory' database contains 94k+ theorems from DeepSeek-Prover datasets
        db_name = os.getenv("LEAN4_ARANGO_DB", os.getenv("ARANGO_DB", "memory"))
        # Override to 'memory' if explicitly set to 'lessons' (legacy config)
        if db_name == "lessons":
            db_name = "memory"
        user = os.getenv("ARANGO_USER", "root")
        password = os.getenv("ARANGO_PASS", "")
        client = ArangoClient(hosts=url)
        return client.db(db_name, username=user, password=password)
    except Exception:
        return None


def retrieve_similar_proofs(
    requirement: str,
    tactics: List[str] | None = None,
    k: int = RETRIEVAL_K,
) -> List[Dict[str, Any]]:
    """Retrieve similar proofs using hybrid search (BM25 + semantic + graph).

    Uses the memory project's hybrid_search_lean_theorems combining keyword
    matching (BM25), semantic similarity (cosine), and graph traversal.
    Falls back to BM25-only if memory project unavailable.
    """
    db = get_arango_db()
    if not db:
        return []

    try:
        # Build search query combining requirement and tactics
        search_terms = requirement
        if tactics:
            search_terms += " " + " ".join(tactics)

        # Try hybrid search first (BM25 + semantic + graph)
        try:
            # Add memory src to path for hybrid_search import
            import sys
            memory_src = os.path.expanduser("~/workspace/experiments/memory/src")
            if memory_src not in sys.path:
                sys.path.insert(0, memory_src)

            from graph_memory.hybrid_search import hybrid_search_lean_theorems

            results = hybrid_search_lean_theorems(
                db,
                query=search_terms,
                k=k,
                bm25_weight=0.4,
                vector_weight=0.4,
                graph_weight=0.2,
            )

            # Convert to expected format
            return [{
                "formal_statement": r.get("formal_statement"),
                "formal_proof": r.get("formal_proof"),
                "header": r.get("header"),
                "tactics": r.get("tactics", []),
                "score": r.get("scores", {}).get("combined", 0),
            } for r in results]

        except ImportError:
            pass  # Fall back to BM25-only

        # Fallback: BM25-only search on lean_theorems_search view
        aql = """
        FOR doc IN lean_theorems_search
        SEARCH ANALYZER(
            doc.formal_statement IN TOKENS(@query, 'text_en') OR
            doc.goal IN TOKENS(@query, 'text_en'),
            'text_en'
        )
        FILTER doc.status IN ["proven", "ok"]
        LET score = BM25(doc)
        SORT score DESC
        LIMIT @k
        RETURN {
            formal_statement: doc.formal_statement,
            formal_proof: doc.formal_proof,
            header: doc.header,
            tactics: doc.tactics,
            score: score
        }
        """

        results = list(db.aql.execute(aql, bind_vars={
            "query": search_terms,
            "k": k,
        }))

        return results
    except Exception as e:
        # Retrieval failure is non-fatal - proceed without exemplars
        print(f"Retrieval warning: {e}", file=sys.stderr)
        return []


def build_support_pack(exemplars: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a support pack from retrieved exemplars."""
    if not exemplars:
        return {"imports": set(), "tactics": set(), "examples": []}

    imports = set()
    tactics = set()
    examples = []

    for ex in exemplars:
        # Extract imports from header
        header = ex.get("header", "")
        for line in header.split("\n"):
            if line.strip().startswith("import "):
                imports.add(line.strip())
            elif line.strip().startswith("open "):
                imports.add(line.strip())

        # Collect tactics
        for tac in ex.get("tactics", []):
            tactics.add(tac)

        # Format example
        examples.append({
            "statement": ex.get("formal_statement", "")[:200],
            "proof": ex.get("formal_proof", "")[:150],
        })

    return {
        "imports": imports,
        "tactics": tactics,
        "examples": examples[:3],  # Limit to 3 examples to avoid prompt bloat
    }


def extract_theorem_name(code: str) -> Optional[str]:
    """Extract theorem/lemma name from Lean4 code."""
    import re
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


def parse_proof_term(proof_term: str) -> List[str]:
    """Extract lemma dependencies from a Lean4 proof term.

    Parses the output of `#print theorem_name` to find referenced lemmas.
    """
    import re

    # Patterns for Lean4 qualified names
    patterns = [
        r'\b([A-Z][a-zA-Z0-9_]*\.[a-zA-Z0-9_.]+)\b',  # Qualified: Nat.add_comm
        r'\b([a-z][a-z0-9_]+(?:\.[a-zA-Z0-9_]+)*)\b',  # Local or qualified lowercase
    ]

    all_refs = set()
    for pattern in patterns:
        all_refs.update(re.findall(pattern, proof_term))

    # Filter out noise
    exclude = {
        # Core Lean constructors
        'Eq.mpr', 'Eq.refl', 'Eq.trans', 'Eq.symm', 'Eq.subst', 'Eq.mp',
        'id', 'rfl', 'trivial', 'absurd', 'congrArg', 'of_eq_true',
        # Keywords/syntax
        'fun', 'let', 'by', 'where', 'in', 'do', 'match', 'with',
        # Bound variables
        'n', 'm', 'h', 'x', 'y', 'a', 'b', 'p', 'q', 'k', 'i', 'j',
        'h0', 'h1', 'h2', 'h3', 'ih', 'this', 'eq_self',
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


def extract_lemma_deps(
    code: str,
    container: str = "lean_runner",
    timeout: int = 30,
) -> List[str]:
    """Extract lemma dependencies by compiling with #print.

    Appends #print to the code, compiles, and parses the proof term.
    Returns list of lemma dependencies.
    """
    theorem_name = extract_theorem_name(code)
    if not theorem_name:
        return []

    # Append #print command
    code_with_print = f"{code}\n\n#print {theorem_name}"

    temp_file = f"/tmp/deps_{int(time.time() * 1000)}.lean"

    try:
        # Use single bash command to write and compile
        # This avoids issues with separate subprocess calls
        bash_cmd = f"""cat > {temp_file} << 'LEANEOF'
{code_with_print}
LEANEOF

cd /workspace/mathlib_project && lake env lean --json {temp_file}
rm -f {temp_file}
"""
        result = subprocess.run(
            ["docker", "exec", container, "bash", "-c", bash_cmd],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        # Parse JSON output for #print result
        for line in result.stdout.split('\n'):
            if not line.strip():
                continue
            try:
                msg = json.loads(line)
                if msg.get('severity') == 'information':
                    data = msg.get('data', '')
                    if theorem_name in data and ':=' in data:
                        return parse_proof_term(data)
            except json.JSONDecodeError:
                continue

        return []

    except Exception as e:
        print(f"Dependency extraction warning: {e}", file=sys.stderr)
        return []


def create_dependency_edges(
    db,
    theorem_key: str,
    lemma_deps: List[str],
    project: Optional[str] = None,
) -> int:
    """Create uses_lemma edges from theorem to its dependencies.

    Returns number of edges created.
    """
    if not lemma_deps or not db:
        return 0

    try:
        # Ensure edge collection exists
        if not db.has_collection("lesson_edges"):
            db.create_collection("lesson_edges", edge=True)

        edge_col = db.collection("lesson_edges")
        thm_col = db.collection("lean_theorems")

        edges = []
        for dep in lemma_deps:
            # Check if dependency is one of our theorems (same project)
            if project:
                # Look for matching theorem in same project
                matches = list(db.aql.execute('''
                    FOR t IN lean_theorems
                    FILTER t.name == @dep AND t.project == @project
                    LIMIT 1
                    RETURN t._key
                ''', bind_vars={"dep": dep, "project": project}))

                if matches:
                    target = f"lean_theorems/{matches[0]}"
                else:
                    target = f"mathlib/{dep}"
            else:
                target = f"mathlib/{dep}"

            edge_key = f"dep_{theorem_key}_{dep}".replace(".", "_")[:250]
            edges.append({
                "_key": edge_key,
                "_from": f"lean_theorems/{theorem_key}",
                "_to": target,
                "type": "uses_lemma",
                "lemma": dep,
                "project": project,
            })

        if edges:
            edge_col.import_bulk(edges, on_duplicate="replace")

        return len(edges)

    except Exception as e:
        print(f"Edge creation warning: {e}", file=sys.stderr)
        return 0


def learn_result(
    requirement: str,
    code: str | None,
    success: bool,
    errors: List[str] | None,
    tactics: List[str] | None = None,
    metadata: Dict[str, Any] | None = None,
    project: str | None = None,
    lemma_deps: List[str] | None = None,
) -> str | None:
    """Store proof result back into lean_theorems for corpus evolution.

    Stores both successful and failed attempts so the system learns from:
    - Working proofs (expand corpus)
    - Failed attempts (avoid repeating mistakes)
    - User requirements (understand query patterns)

    Args:
        requirement: Original user requirement
        code: Generated Lean4 code
        success: Whether compilation succeeded
        errors: List of error messages
        tactics: List of tactics used
        metadata: Additional metadata
        project: Project identifier for grouping related proofs
        lemma_deps: List of lemma dependencies (for dependency graph)

    Returns:
        The _key of the stored document, or None if storage failed.
    """
    if not LEARN_ENABLED:
        return None

    db = get_arango_db()
    if not db:
        return None

    try:
        import hashlib
        from datetime import datetime

        # Generate deterministic key from requirement + code
        content = f"{requirement}::{code or 'none'}"
        key = hashlib.sha256(content.encode()).hexdigest()[:16]

        # Extract header and proof from generated code
        header = ""
        formal_statement = ""
        formal_proof = ""

        if code:
            lines = code.split("\n")
            in_header = True
            proof_lines = []

            for line in lines:
                if in_header and (line.strip().startswith("import ") or
                                  line.strip().startswith("open ") or
                                  line.strip().startswith("set_option ") or
                                  line.strip() == ""):
                    header += line + "\n"
                else:
                    in_header = False
                    proof_lines.append(line)

            proof_text = "\n".join(proof_lines)
            # Split into statement and proof at ":= by" or ":= "
            if ":= by" in proof_text:
                parts = proof_text.split(":= by", 1)
                formal_statement = parts[0].strip() + " := by"
                formal_proof = parts[1].strip() if len(parts) > 1 else ""
            elif ":= " in proof_text:
                parts = proof_text.split(":= ", 1)
                formal_statement = parts[0].strip() + " := "
                formal_proof = parts[1].strip() if len(parts) > 1 else ""
            else:
                formal_statement = proof_text

        # Extract tactics from code
        extracted_tactics = []
        if code:
            import re
            tactic_pattern = r'\b(simp|ring|omega|decide|exact|apply|intro|rfl|norm_num|linarith|nlinarith|induction|cases|have|let|rw|unfold|ext|funext|constructor|use|refine|aesop)\b'
            extracted_tactics = list(set(re.findall(tactic_pattern, code.lower())))

        # Extract theorem name for dependency tracking
        theorem_name = extract_theorem_name(code) if code else None

        doc = {
            "_key": key,
            "name": theorem_name,  # Theorem name for dependency lookups
            "requirement": requirement,  # Original user request
            "formal_statement": formal_statement,
            "formal_proof": formal_proof,
            "header": header.strip(),
            "full_code": code,
            "tactics": tactics or extracted_tactics,
            "source": "agent-generated",
            "scope": "lean4-proofs",
            "status": "ok" if success else "error",
            "errors": errors,
            "metadata": metadata or {},
            "project": project,  # Project for grouping related proofs
            "lemma_deps": lemma_deps,  # Dependencies for graph traversal
            "created_at": datetime.utcnow().isoformat(),
        }

        col = db.collection("lean_theorems")
        col.insert(doc, overwrite=True)

        # Create dependency edges for successful proofs
        if success and lemma_deps:
            edges_created = create_dependency_edges(db, key, lemma_deps, project)
            if edges_created > 0:
                print(f"Created {edges_created} dependency edges", file=sys.stderr)

        return key
    except Exception as e:
        print(f"Learn warning: {e}", file=sys.stderr)
        return None


def call_claude(prompt: str, system: str, model: str = None) -> str:
    """Call Claude via Claude Code CLI in headless non-interactive mode.

    Args:
        prompt: The user prompt
        system: System prompt
        model: Model alias (sonnet, opus, haiku) or full name

    Returns:
        The Claude response text
    """
    model = model or DEFAULT_MODEL

    # Build the full prompt with system context
    full_prompt = f"{system}\n\n{prompt}"

    # Use Claude Code CLI with -p for print/headless mode
    # Key flags for headless operation:
    # - -p: print mode (non-interactive, outputs to stdout)
    # - --output-format text: plain text output
    # - --max-turns 1: single turn, no conversation
    # - --no-stream: wait for full response (don't stream)
    cmd = [
        "claude",
        "-p", full_prompt,
        "--model", model,
        "--output-format", "text",
        "--max-turns", "1",
    ]

    # Clean environment to avoid Claude detecting it's being called from Claude
    env = os.environ.copy()
    env.pop("CLAUDE_CODE", None)
    env.pop("CLAUDECODE", None)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,  # 3 minutes for complex proofs
            cwd=Path.home(),  # Run from home to avoid workspace issues
            env=env,
        )

        if result.returncode != 0:
            stderr = result.stderr.strip()
            if stderr:
                raise RuntimeError(f"Claude CLI error: {stderr}")
            raise RuntimeError(f"Claude CLI failed with code {result.returncode}")

        return result.stdout.strip()

    except subprocess.TimeoutExpired:
        raise RuntimeError("Claude CLI timeout after 180s")
    except FileNotFoundError:
        raise RuntimeError("Claude CLI not found - ensure 'claude' is in PATH")


def compile_lean(code: str, container: str, timeout: int) -> Dict[str, Any]:
    """Compile Lean4 code in Docker container."""
    skill_dir = Path(__file__).parent.parent / "lean4-verify"
    run_script = skill_dir / "run.sh"

    if run_script.exists():
        # Use lean4-verify skill
        result = subprocess.run(
            [str(run_script), "--container", container, "--timeout", str(timeout)],
            input=code,
            capture_output=True,
            text=True,
            timeout=timeout + 10
        )
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"success": False, "exit_code": 1, "stdout": result.stdout, "stderr": result.stderr}
    else:
        # Direct Docker compilation
        temp_file = f"/tmp/proof_{int(time.time() * 1000)}.lean"

        # Write code to container
        subprocess.run(
            ["docker", "exec", container, "bash", "-c", f"cat > {temp_file}"],
            input=code,
            text=True,
            check=True
        )

        # Compile
        result = subprocess.run(
            ["docker", "exec", container, "bash", "-c",
             f"cd /workspace && lake env lean '{temp_file}' 2>&1"],
            capture_output=True,
            text=True,
            timeout=timeout
        )

        # Cleanup
        subprocess.run(["docker", "exec", container, "rm", "-f", temp_file],
                      capture_output=True)

        return {
            "success": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr
        }


def extract_lean_code(response: str) -> str:
    """Extract Lean4 code from Claude response."""
    # Look for ```lean or ```lean4 blocks
    import re

    patterns = [
        r'```lean4?\s*\n(.*?)```',
        r'```\s*\n(.*?)```',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, response, re.DOTALL)
        if matches:
            return matches[0].strip()

    # If no code blocks, return the whole response (might be raw code)
    return response.strip()


def build_system_prompt(
    tactics: list[str] | None,
    persona: str | None,
    support_pack: Dict[str, Any] | None = None,
) -> str:
    """Build system prompt with optional tactics, persona, and retrieved exemplars."""
    parts = [
        "You are an expert Lean4 theorem prover. Generate valid, compilable Lean4 code.",
        "Return ONLY the Lean4 code in a ```lean4 code block. No explanations.",
        "The code must be self-contained and compile with `lake env lean`."
    ]

    # Add validated imports from exemplars
    if support_pack and support_pack.get("imports"):
        imports_list = sorted(support_pack["imports"])
        parts.append(f"\nUse these imports (validated to work):\n```lean4\n{chr(10).join(imports_list)}\n```")

    # Add tactics from user + exemplars
    all_tactics = set(tactics or [])
    if support_pack and support_pack.get("tactics"):
        all_tactics.update(support_pack["tactics"])
    if all_tactics:
        parts.append(f"\nPreferred tactics: {', '.join(sorted(all_tactics))}")

    # Add similar proof examples
    if support_pack and support_pack.get("examples"):
        parts.append("\n## Similar proofs that compiled successfully:")
        for i, ex in enumerate(support_pack["examples"], 1):
            parts.append(f"\nExample {i}:")
            parts.append(f"Statement: {ex['statement']}")
            parts.append(f"Proof: {ex['proof']}")

    if persona:
        parts.append(f"\nPersona: {persona}")

    return "\n".join(parts)


def build_retry_prompt(requirement: str, previous_code: str, error: str) -> str:
    """Build prompt for retry attempt with error feedback."""
    return f"""Previous attempt failed to compile.

Requirement: {requirement}

Previous code:
```lean4
{previous_code}
```

Compiler error:
{error}

Fix the code to compile successfully. Return ONLY the corrected Lean4 code."""


def generate_candidate(
    requirement: str,
    system_prompt: str,
    model: str,
    candidate_id: int
) -> tuple[int, str]:
    """Generate a single proof candidate."""
    prompt = f"Prove the following in Lean4:\n\n{requirement}"
    response = call_claude(prompt, system_prompt, model)
    code = extract_lean_code(response)
    return (candidate_id, code)


def prove(
    requirement: str,
    tactics: list[str] | None = None,
    persona: str | None = None,
    max_retries: int = 3,
    candidates: int = 3,
    model: str = "opus",
    container: str = "lean_runner",
    timeout: int = 120,
    project: str | None = None,
    extract_deps: bool = False,
) -> Dict[str, Any]:
    """
    Generate and verify a Lean4 proof.

    Args:
        requirement: The theorem to prove
        tactics: Preferred tactics to use (e.g., ["simp", "ring", "omega"])
        persona: Optional persona context (e.g., "cryptographer")
        max_retries: Maximum retry attempts per candidate
        candidates: Number of parallel proof candidates to generate
        model: Claude model alias (sonnet, opus, haiku) or full name
        container: Docker container name
        timeout: Compilation timeout in seconds
        project: Project identifier for grouping related proofs (for dependency graph)
        extract_deps: Whether to extract lemma dependencies after successful proof

    Returns:
        dict with success, code, attempts, errors
    """
    # Check container
    result = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"],
        capture_output=True,
        text=True
    )
    if container not in result.stdout:
        return {
            "success": False,
            "error": f"Container '{container}' not running",
            "code": None,
            "attempts": 0
        }

    # Retrieval-augmented generation: fetch similar proofs
    support_pack = None
    retrieval_info = None
    if RETRIEVAL_ENABLED:
        exemplars = retrieve_similar_proofs(requirement, tactics, k=RETRIEVAL_K)
        if exemplars:
            support_pack = build_support_pack(exemplars)
            retrieval_info = {
                "retrieved": len(exemplars),
                "tactics_added": list(support_pack.get("tactics", [])),
                "imports_count": len(support_pack.get("imports", [])),
            }

    system_prompt = build_system_prompt(tactics, persona, support_pack)
    all_errors = []
    total_attempts = 0

    # Generate candidates in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=candidates) as executor:
        futures = [
            executor.submit(generate_candidate, requirement, system_prompt, model, i)
            for i in range(candidates)
        ]

        candidate_codes = []
        for future in concurrent.futures.as_completed(futures):
            try:
                cid, code = future.result()
                candidate_codes.append((cid, code))
            except Exception as e:
                all_errors.append(f"Generation error: {e}")

    # Try each candidate with retries
    for cid, code in candidate_codes:
        for attempt in range(max_retries):
            total_attempts += 1

            try:
                result = compile_lean(code, container, timeout)
            except subprocess.TimeoutExpired:
                all_errors.append(f"Candidate {cid} attempt {attempt + 1}: timeout")
                continue
            except Exception as e:
                all_errors.append(f"Candidate {cid} attempt {attempt + 1}: {e}")
                continue

            if result.get("success"):
                # Extract lemma dependencies if requested
                lemma_deps = None
                if extract_deps:
                    lemma_deps = extract_lemma_deps(code, container, timeout)

                # Learn from success - store for corpus evolution
                learned_key = learn_result(
                    requirement=requirement,
                    code=code,
                    success=True,
                    errors=None,
                    tactics=tactics,
                    metadata={
                        "model": model,
                        "attempts": total_attempts,
                        "candidate": cid,
                        "retrieval_count": retrieval_info.get("retrieved") if retrieval_info else 0,
                    },
                    project=project,
                    lemma_deps=lemma_deps,
                )

                return {
                    "success": True,
                    "code": code,
                    "attempts": total_attempts,
                    "candidate": cid,
                    "errors": all_errors if all_errors else None,
                    "retrieval": retrieval_info,
                    "learned": learned_key,
                    "project": project,
                    "lemma_deps": lemma_deps,
                }

            # Failed - prepare retry with error feedback
            error_msg = result.get("stdout", "") or result.get("stderr", "")
            all_errors.append(f"Candidate {cid} attempt {attempt + 1}: {error_msg[:500]}")

            if attempt < max_retries - 1:
                # Retry with error feedback
                retry_prompt = build_retry_prompt(requirement, code, error_msg)
                try:
                    response = call_claude(retry_prompt, system_prompt, model)
                    code = extract_lean_code(response)
                except Exception as e:
                    all_errors.append(f"Retry generation error: {e}")

    # Learn from failure - store failed attempt for analysis
    # Use the last attempted code if any candidates were generated
    last_code = candidate_codes[-1][1] if candidate_codes else None
    learned_key = learn_result(
        requirement=requirement,
        code=last_code,
        success=False,
        errors=all_errors,
        tactics=tactics,
        metadata={
            "model": model,
            "attempts": total_attempts,
            "retrieval_count": retrieval_info.get("retrieved") if retrieval_info else 0,
        },
        project=project,
        lemma_deps=None,  # No deps for failed proofs
    )

    return {
        "success": False,
        "code": None,
        "attempts": total_attempts,
        "errors": all_errors,
        "retrieval": retrieval_info,
        "learned": learned_key,
        "project": project,
    }


def main() -> None:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate and verify Lean4 proofs")
    parser.add_argument("--requirement", "-r", help="Theorem to prove")
    parser.add_argument("--tactics", "-t", help="Comma-separated tactics")
    parser.add_argument("--persona", "-p", help="Persona context")
    parser.add_argument("--retries", type=int, default=3, help="Max retries per candidate")
    parser.add_argument("--candidates", "-n", type=int, default=3, help="Parallel candidates")
    parser.add_argument("--model", default="opus", help="Claude model (opus, sonnet, haiku)")
    parser.add_argument("--container", default="lean_runner", help="Docker container")
    parser.add_argument("--timeout", type=int, default=120, help="Compile timeout")
    parser.add_argument("--project", help="Project identifier for grouping related proofs")
    parser.add_argument("--extract-deps", action="store_true", help="Extract lemma dependencies after successful proof")

    args = parser.parse_args()

    # Get requirement from args or stdin
    if args.requirement:
        requirement = args.requirement
    else:
        # Try JSON from stdin
        stdin_data = sys.stdin.read().strip()
        if stdin_data:
            try:
                data = json.loads(stdin_data)
                requirement = data.get("requirement", stdin_data)
                # Override with JSON values if present
                if "tactics" in data and not args.tactics:
                    args.tactics = ",".join(data["tactics"]) if isinstance(data["tactics"], list) else data["tactics"]
                if "persona" in data and not args.persona:
                    args.persona = data["persona"]
                if "project" in data and not args.project:
                    args.project = data["project"]
                if data.get("extract_deps") and not args.extract_deps:
                    args.extract_deps = True
            except json.JSONDecodeError:
                requirement = stdin_data
        else:
            parser.error("--requirement or stdin input required")

    tactics = args.tactics.split(",") if args.tactics else None

    result = prove(
        requirement=requirement,
        tactics=tactics,
        persona=args.persona,
        max_retries=args.retries,
        candidates=args.candidates,
        model=args.model,
        container=args.container,
        timeout=args.timeout,
        project=args.project,
        extract_deps=args.extract_deps,
    )

    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()

