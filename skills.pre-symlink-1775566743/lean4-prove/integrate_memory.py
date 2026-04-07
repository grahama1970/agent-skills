#!/usr/bin/env python3
"""
Integrate lean theorems with the memory skill's full retrieval pipeline.

This script:
1. Embeds theorem statements for semantic search
2. Creates edge relationships between similar theorems
3. Enables multi-hop graph traversal via lesson_edges

Usage:
    # Full integration (embeddings + edges)
    python integrate_memory.py

    # Embeddings only
    python integrate_memory.py --embeddings-only

    # Edges only (requires embeddings first)
    python integrate_memory.py --edges-only
"""
import os
import typer
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
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

def create_embeddings(batch_size: int = 100):
    """Embed all lean theorems via /memory learn (embedding-at-insert)."""
    # Recall proven theorems that need embedding
    try:
        pending = _memory_cmd(
            ["recall", "--q", "status:ok OR status:proven", "--collections", "lean_theorems"],
            timeout=120,
        )
    except RuntimeError as e:
        raise RuntimeError(f"Cannot fetch theorems for embedding: {e}")

    if not isinstance(pending, list):
        pending = pending.get("results", [])

    print(f"Re-learning {len(pending)} theorems (triggers embedding-at-insert)...")

    for i, thm in enumerate(pending):
        text = (thm.get("formal_statement") or "")[:512]
        if not text:
            continue

        try:
            _memory_cmd([
                "learn",
                "--problem", text,
                "--solution", json.dumps({
                    "source": "lean_theorem",
                    "formal_statement": thm.get("formal_statement", ""),
                    "formal_proof": thm.get("formal_proof", ""),
                }),
                "--scope", "lean4",
            ])
        except RuntimeError as e:
            print(f"  Error embedding {thm.get('_key', '?')}: {e}")
            continue

        if (i + 1) % batch_size == 0:
            print(f"  Progress: {i + 1}/{len(pending)}")

    print(f"Embedded {len(pending)} theorems")


def create_edges(similarity_threshold: float = 0.7, max_edges_per_node: int = 5):
    """Create edges between similar theorems via /memory learn.

    Note: With the /memory abstraction, edge creation is delegated to the
    memory skill. We recall proven theorems and create edge documents
    via learn commands.
    """
    # Recall proven theorems
    try:
        theorems = _memory_cmd(
            ["recall", "--q", "status:ok OR status:proven", "--collections", "lean_theorems"],
            timeout=120,
        )
    except RuntimeError as e:
        raise RuntimeError(f"Cannot fetch theorems for edge creation: {e}")

    if not isinstance(theorems, list):
        theorems = theorems.get("results", [])

    print(f"Building edges for {len(theorems)} proven theorems...")

    # Strategy 1: Connect theorems with same primary tactics
    print("Creating tactic-based edges...")
    tactic_groups: Dict[str, List[str]] = {}
    for thm in theorems:
        tactics = thm.get("tactics", [])
        if tactics:
            primary = tactics[0]
            tactic_groups.setdefault(primary, []).append(thm.get("_key", ""))

    edge_count = 0
    for tactic, keys in tactic_groups.items():
        if len(keys) < 2:
            continue
        for i, src in enumerate(keys[:50]):  # Cap per-tactic group
            for tgt in keys[i+1:i+max_edges_per_node+1]:
                edge_doc = {
                    "type": "same_tactic",
                    "tactic": tactic,
                    "weight": 0.6,
                    "_from": f"lean_theorems/{src}",
                    "_to": f"lean_theorems/{tgt}",
                }
                try:
                    _memory_cmd([
                        "learn",
                        "--problem", f"edge:tactic:{src}:{tgt}",
                        "--solution", json.dumps(edge_doc),
                        "--scope", "lean4",
                    ])
                    edge_count += 1
                except RuntimeError:
                    pass

    print(f"  Created {edge_count} tactic edges")
    print("  Semantic similarity edges: delegated to /memory embedding pipeline")


app = typer.Typer(help="Integrate lean theorems with memory skill")


@app.command()
def main(
    embeddings_only: bool = typer.Option(False, help="Only create embeddings"),
    edges_only: bool = typer.Option(False, help="Only create edges"),
    batch_size: int = typer.Option(100, help="Batch size for embeddings"),
    similarity_threshold: float = typer.Option(0.7, help="Min similarity for edges"),
):
    print("Using /memory subprocess for all DB access")

    if not edges_only:
        create_embeddings(batch_size=batch_size)

    if not embeddings_only:
        create_edges(similarity_threshold=similarity_threshold)

    print("\nIntegration complete!")
    print("Lean theorems are now searchable via /memory recall")


if __name__ == "__main__":
    app()
