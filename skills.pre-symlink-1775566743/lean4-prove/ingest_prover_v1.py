#!/usr/bin/env python3
"""
Ingest DeepSeek-Prover-V1 dataset into ArangoDB for retrieval-augmented proving.

Downloads from HuggingFace, structures for BM25 + semantic search, optionally
compile-filters to mark valid proofs.

Usage:
    # Ingest all (27.5k rows)
    python ingest_prover_v1.py

    # Ingest subset for testing
    python ingest_prover_v1.py --limit 100

    # Compile-filter after ingest
    python ingest_prover_v1.py --compile-filter --container lean_runner

Environment:
    HF_TOKEN - HuggingFace token (optional, dataset is public)
    ARANGO_URL - ArangoDB URL (default: http://127.0.0.1:8529)
    ARANGO_DB - Database name (default: lessons)
"""
import typer
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

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

def load_dataset(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Load DeepSeek-Prover-V1 from HuggingFace."""
    from datasets import load_dataset as hf_load

    print("Loading DeepSeek-Prover-V1 from HuggingFace...")
    token = os.getenv("HF_TOKEN")

    ds = hf_load(
        "deepseek-ai/DeepSeek-Prover-V1",
        split="train",
        token=token,
    )

    if limit:
        ds = ds.select(range(min(limit, len(ds))))

    print(f"Loaded {len(ds)} examples")
    return list(ds)


def extract_tactics(proof: str) -> List[str]:
    """Extract tactic names from a Lean 4 proof."""
    import re
import httpx

    # Common Lean 4 tactics
    tactic_pattern = r'\b(simp|ring|omega|decide|exact|apply|intro|rfl|norm_num|linarith|nlinarith|positivity|ext|funext|congr|cases|induction|rcases|obtain|have|let|show|calc|by_contra|by_cases|push_neg|contrapose|trivial|assumption|contradiction|exfalso|constructor|left|right|use|exists|refine|convert|rw|rewrite|subst|unfold|dsimp|change|clear|rename|specialize|generalize|suffices|wlog|fin_cases|interval_cases|norm_cast|field_simp|ring_nf|polyrith|nlinarith|aesop|tauto|itauto|decide|native_decide)\b'

    tactics = re.findall(tactic_pattern, proof.lower())
    return list(set(tactics))


def compute_key(statement: str) -> str:
    """Compute deterministic key from statement."""
    return hashlib.sha256(statement.encode()).hexdigest()[:16]


def ingest_to_memory(
    examples: List[Dict[str, Any]],
    batch_size: int = 100,
) -> Dict[str, int]:
    """Ingest examples via /memory learn commands."""
    stats = {"inserted": 0, "skipped": 0, "errors": 0}

    for i, ex in enumerate(examples):
        statement = ex.get("formal_statement", "")
        proof = ex.get("formal_proof", "")

        doc = {
            "_key": compute_key(statement),
            "name": ex.get("name", f"thm_{i}"),
            "formal_statement": statement,
            "goal": ex.get("goal", ""),
            "header": ex.get("header", ""),
            "formal_proof": proof,
            "tactics": extract_tactics(proof),
            "source": "deepseek-prover-v1",
            "scope": "lean4-proofs",
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
        }

        try:
            _memory_cmd([
                "learn",
                "--problem", statement[:500] or f"theorem_{i}",
                "--solution", json.dumps(doc),
                "--scope", "lean4",
            ])
            stats["inserted"] += 1
        except RuntimeError:
            stats["errors"] += 1

        if (i + 1) % batch_size == 0:
            print(f"Progress: {i + 1}/{len(examples)} ({stats['inserted']} inserted)")

    print(f"\nIngest complete: {stats}")
    return stats


def do_compile_filter(
    container: str = "lean_runner",
    timeout: int = 60,
    batch_size: int = 10,
) -> Dict[str, int]:
    """Compile-filter pending theorems, marking status=ok or status=error."""
    # Get pending theorems via /memory recall
    pending = _memory_cmd(["recall", "--q", "status:pending", "--collections", "lean_theorems"], timeout=120)
    if not isinstance(pending, list):
        pending = pending.get("results", [])

    print(f"Compile-filtering {len(pending)} pending theorems...")
    stats = {"ok": 0, "error": 0, "timeout": 0}

    for i, thm in enumerate(pending):
        # Build full Lean file
        code = f"""{thm.get('header', '')}

{thm.get('formal_statement', '')}
  {thm.get('formal_proof', '')}
"""

        status = "error"
        compile_output = None

        try:
            temp_file = f"/tmp/proof_{thm.get('_key', i)}.lean"

            subprocess.run(
                ["docker", "exec", container, "bash", "-c", f"cat > {temp_file}"],
                input=code, text=True, check=True, timeout=10,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )

            result = subprocess.run(
                ["docker", "exec", container, "bash", "-c",
                 f"cd /workspace && lake env lean '{temp_file}' 2>&1"],
                capture_output=True, text=True, timeout=timeout,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )

            subprocess.run(
                ["docker", "exec", container, "rm", "-f", temp_file],
                capture_output=True, timeout=5,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )

            if result.returncode == 0:
                status = "ok"
                stats["ok"] += 1
            else:
                status = "error"
                stats["error"] += 1
            compile_output = result.stdout[:1000] if result.stdout else None

        except subprocess.TimeoutExpired:
            status = "timeout"
            stats["timeout"] += 1
        except Exception as e:
            status = "error"
            compile_output = str(e)[:500]
            stats["error"] += 1

        # Update via /memory learn (overwrite)
        update_doc = {
            "status": status,
            "compile_output": compile_output,
            "compiled_at": datetime.utcnow().isoformat(),
        }
        try:
            _memory_cmd([
                "learn",
                "--problem", thm.get("formal_statement", "")[:500] or f"theorem_{i}",
                "--solution", json.dumps(update_doc),
                "--scope", "lean4",
            ])
        except RuntimeError as e:
            print(f"  Failed to update {thm.get('_key', '?')}: {e}", file=sys.stderr)

        if (i + 1) % 10 == 0:
            print(f"Progress: {i + 1}/{len(pending)} (ok={stats['ok']}, error={stats['error']})")

    print(f"\nCompile-filter complete: {stats}")
    return stats


app = typer.Typer(help="Ingest DeepSeek-Prover-V1 dataset")


@app.command()
def main(
    limit: int = typer.Option(None, help="Limit number of examples to ingest"),
    run_compile_filter: bool = typer.Option(False, "--compile-filter", help="Run compile-filter pass"),
    container: str = typer.Option("lean_runner", help="Docker container for compilation"),
    timeout: int = typer.Option(60, help="Compile timeout per theorem"),
    skip_ingest: bool = typer.Option(False, help="Skip ingest, only compile-filter"),
):
    print("Using /memory subprocess for all DB access")

    if not skip_ingest:
        examples = load_dataset(limit=limit)
        ingest_to_memory(examples)

    if run_compile_filter:
        # Check container is running
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if container not in result.stdout:
            print(f"Error: Container '{container}' not running")
            sys.exit(1)

        do_compile_filter(container, timeout)


if __name__ == "__main__":
    app()
