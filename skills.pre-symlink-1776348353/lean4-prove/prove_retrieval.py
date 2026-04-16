"""
prove_retrieval: Database retrieval, memory storage, and parsing utilities for lean4-prove.

Handles:
- ArangoDB connection and hybrid search (BM25 + semantic + graph)
- Support pack construction from retrieved exemplars
- Lean4 code parsing (theorem names, proof terms, lemma dependencies)
- Dependency edge creation in the knowledge graph
- Learn-back: storing proof results for corpus evolution
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

# Removed: memory accessed via httpx to Unix socket (see _memory_cmd)
# Retrieval settings
RETRIEVAL_ENABLED = os.getenv("LEAN4_RETRIEVAL", "1") != "0"
RETRIEVAL_K = int(os.getenv("LEAN4_RETRIEVAL_K", "5"))

# Learn-back settings (store new proofs for corpus evolution)
LEARN_ENABLED = os.getenv("LEAN4_LEARN", "1") != "0"


def get_arango_db():
    """Return a python-arango database handle for lean_theorems access.

    Used by sanity.sh to check collection existence and count, and by
    retrieve_similar_proofs for hybrid search. Returns None if ArangoDB
    is unavailable (caller must handle gracefully).
    """
    try:
        from arango import ArangoClient
    except ImportError:
        return None

    url = os.getenv("ARANGO_URL", f"http://{os.getenv('ARANGO_HOST', 'localhost')}:{os.getenv('ARANGO_PORT', '8529')}")
    db_name = os.getenv("ARANGO_DB", "memory")
    username = os.getenv("ARANGO_USER", "root")
    password = os.getenv("ARANGO_PASS", "")

    try:
        client = ArangoClient(hosts=url)
        db = client.db(db_name, username=username, password=password)
        # Verify connectivity
        db.version()
        return db
    except Exception:
        return None


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
            resp = client.post("/query", json={"aql": f"RETURN LENGTH({coll})", "bind_vars": {}})
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

def retrieve_similar_proofs(
    requirement: str,
    tactics: List[str] | None = None,
    k: int = RETRIEVAL_K,
) -> List[Dict[str, Any]]:
    """Retrieve similar proofs via /memory recall.

    Delegates to the memory skill which handles hybrid search
    (BM25 + semantic + graph) internally.
    """
    try:
        # Build search query combining requirement and tactics
        search_terms = requirement
        if tactics:
            search_terms += " " + " ".join(tactics)

        results = _memory_cmd([
            "recall", "--q", search_terms,
            "--collections", "lean_theorems",
        ], timeout=30)

        if not isinstance(results, list):
            results = results.get("results", [])

        # Convert to expected format and limit to k
        return [{
            "formal_statement": r.get("formal_statement"),
            "formal_proof": r.get("formal_proof"),
            "header": r.get("header"),
            "tactics": r.get("tactics", []),
            "score": r.get("score", 0),
        } for r in results[:k]]

    except (RuntimeError, json.JSONDecodeError) as e:
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
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
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
    theorem_key: str,
    lemma_deps: List[str],
    project: Optional[str] = None,
) -> int:
    """Create uses_lemma edges from theorem to its dependencies via /memory learn.

    Returns number of edges created.
    """
    if not lemma_deps:
        return 0

    created = 0
    for dep in lemma_deps:
        target = f"mathlib/{dep}"

        # Try to find matching theorem in same project
        if project:
            try:
                matches = _memory_cmd([
                    "recall", "--q", f"name:{dep} project:{project}",
                    "--collections", "lean_theorems",
                ], timeout=15)
                if isinstance(matches, list) and matches:
                    target = f"lean_theorems/{matches[0].get('_key', dep)}"
                elif isinstance(matches, dict) and matches.get("results"):
                    target = f"lean_theorems/{matches['results'][0].get('_key', dep)}"
            except (RuntimeError, json.JSONDecodeError):
                pass  # Fall back to mathlib target

        edge_doc = {
            "_from": f"lean_theorems/{theorem_key}",
            "_to": target,
            "type": "uses_lemma",
            "lemma": dep,
            "project": project,
        }
        try:
            _memory_cmd([
                "learn",
                "--problem", f"edge:dep:{theorem_key}:{dep}",
                "--solution", json.dumps(edge_doc),
                "--scope", "lean4",
            ])
            created += 1
        except RuntimeError as e:
            print(f"Edge creation warning: {e}", file=sys.stderr)

    return created


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

    try:
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
            tactic_pattern = r'\b(simp|ring|omega|decide|exact|apply|intro|rfl|norm_num|linarith|nlinarith|induction|cases|have|let|rw|unfold|ext|funext|constructor|use|refine|aesop)\b'
            extracted_tactics = list(set(re.findall(tactic_pattern, code.lower())))

        # Extract theorem name for dependency tracking
        theorem_name = extract_theorem_name(code) if code else None

        doc = {
            "_key": key,
            "name": theorem_name,
            "requirement": requirement,
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
            "project": project,
            "lemma_deps": lemma_deps,
            "created_at": datetime.utcnow().isoformat(),
        }

        _memory_cmd([
            "learn",
            "--problem", formal_statement[:500] or requirement[:500],
            "--solution", json.dumps(doc),
            "--scope", "lean4",
        ])

        # Create dependency edges for successful proofs
        if success and lemma_deps:
            edges_created = create_dependency_edges(key, lemma_deps, project)
            if edges_created > 0:
                print(f"Created {edges_created} dependency edges", file=sys.stderr)

        return key
    except Exception as e:
        print(f"Learn warning: {e}", file=sys.stderr)
        return None
