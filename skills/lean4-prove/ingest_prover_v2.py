#!/usr/bin/env python3
"""
Ingest DeepSeek-Prover-V2 dataset (Cartinoe5930) into ArangoDB.

This is a community-contributed dataset with 66.7k theorems.
"""
import typer
import hashlib
import json
import os
import re
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

def update_progress(task_id: str, completed: int, total: int, status: str = "running"):
    """Update progress in task_states via /memory learn."""
    doc = {
        "task_type": "ingest",
        "scope": "lean_theorems_v2",
        "completed": completed,
        "total": total,
        "status": status,
        "percent": round(100 * completed / total, 1) if total else 0,
        "updated_at": datetime.utcnow().isoformat(),
    }
    try:
        _memory_cmd([
            "learn",
            "--problem", f"task_progress:{task_id}",
            "--solution", json.dumps(doc),
            "--scope", "lean4",
        ])
    except RuntimeError as e:
        print(f"  Progress update failed: {e}", file=sys.stderr)


def extract_tactics(proof: str) -> List[str]:
    tactic_pattern = r'\b(simp|ring|omega|decide|exact|apply|intro|rfl|norm_num|linarith|nlinarith|positivity|ext|funext|congr|cases|induction|rcases|obtain|have|let|show|calc|by_contra|by_cases|push_neg|constructor|left|right|use|refine|rw|rewrite|unfold|dsimp|aesop|tauto)\b'
    tactics = re.findall(tactic_pattern, proof.lower())
    return list(set(tactics))


def compute_key(statement: str) -> str:
    return hashlib.sha256(statement.encode()).hexdigest()[:16]


def load_v2_dataset(limit: Optional[int] = None):
    from datasets import load_dataset
    
    print("Loading Cartinoe5930/DeepSeek-Prover-V2-dataset from HuggingFace...")
    token = os.getenv("HF_TOKEN")
    
    ds = load_dataset(
        "Cartinoe5930/DeepSeek-Prover-V2-dataset",
        split="train",
        token=token,
    )
    
    if limit:
        ds = ds.select(range(min(limit, len(ds))))
    
    print(f"Loaded {len(ds)} examples")
    return list(ds)


def ingest_to_memory(examples: List[Dict[str, Any]], batch_size: int = 100) -> Dict[str, int]:
    """Ingest examples via /memory learn commands."""
    task_id = f"ingest_v2_{datetime.utcnow().strftime('%Y%m%d_%H%M')}"

    stats = {"inserted": 0, "skipped": 0, "errors": 0}
    total = len(examples)

    for i, ex in enumerate(examples):
        statement = ex.get("formal_statement", ex.get("statement", ""))
        proof = ex.get("formal_proof", ex.get("proof", ""))
        header = ex.get("header", "import Mathlib\nimport Aesop\nset_option maxHeartbeats 0")

        if not statement:
            stats["skipped"] += 1
            continue

        doc = {
            "_key": compute_key(statement),
            "name": ex.get("name", f"v2_thm_{i}"),
            "formal_statement": statement,
            "goal": ex.get("goal", ""),
            "header": header,
            "formal_proof": proof,
            "tactics": extract_tactics(proof) if proof else [],
            "source": "deepseek-prover-v2",
            "scope": "lean4-proofs",
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
        }

        try:
            _memory_cmd([
                "learn",
                "--problem", statement[:500],
                "--solution", json.dumps(doc),
                "--scope", "lean4",
            ])
            stats["inserted"] += 1
        except RuntimeError:
            stats["errors"] += 1

        if (i + 1) % 1000 == 0:
            print(f"Progress: {i + 1}/{total} ({stats['inserted']} inserted)")
            update_progress(task_id, i + 1, total)

    update_progress(task_id, total, total, "complete")
    print(f"\nIngest complete: {stats}")
    return stats


app = typer.Typer(help="Ingest DeepSeek-Prover-V2 dataset")


@app.command()
def main(
    limit: int = typer.Option(None, help="Limit examples"),
    batch_size: int = typer.Option(100, help=""),
):
    print("Using /memory subprocess for all DB access")

    examples = load_v2_dataset(limit=limit)
    ingest_to_memory(examples, batch_size=batch_size)


if __name__ == "__main__":
    app()
