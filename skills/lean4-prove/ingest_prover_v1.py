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
import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

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
    # Default to 'memory' database which is where graph_memory stores data
    db_name = os.getenv("ARANGO_DB", "memory")
    user = os.getenv("ARANGO_USER", "root")
    password = os.getenv("ARANGO_PASS", "")

    client = ArangoClient(hosts=url)
    return client.db(db_name, username=user, password=password)


def ensure_collection(db, name: str, indexes: List[Dict] = None):
    """Ensure collection exists with indexes."""
    if not db.has_collection(name):
        db.create_collection(name)
        print(f"Created collection: {name}")

    col = db.collection(name)
    if indexes:
        existing = {idx["name"] for idx in col.indexes()}
        for idx in indexes:
            if idx.get("name") not in existing:
                if idx.get("type") == "persistent":
                    col.add_persistent_index(
                        fields=idx["fields"],
                        name=idx["name"],
                        unique=idx.get("unique", False),
                    )
                    print(f"Created index: {idx['name']}")
    return col


def ensure_view(db, view_name: str, collection: str, fields: List[str]):
    """Ensure ArangoSearch view exists."""
    existing_views = [v["name"] for v in db.views()]
    if view_name in existing_views:
        return

    db.create_arangosearch_view(
        name=view_name,
        properties={
            "links": {
                collection: {
                    "analyzers": ["text_en", "identity"],
                    "includeAllFields": False,
                    "fields": {field: {"analyzers": ["text_en"]} for field in fields},
                }
            }
        },
    )
    print(f"Created view: {view_name}")


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

    # Common Lean 4 tactics
    tactic_pattern = r'\b(simp|ring|omega|decide|exact|apply|intro|rfl|norm_num|linarith|nlinarith|positivity|ext|funext|congr|cases|induction|rcases|obtain|have|let|show|calc|by_contra|by_cases|push_neg|contrapose|trivial|assumption|contradiction|exfalso|constructor|left|right|use|exists|refine|convert|rw|rewrite|subst|unfold|dsimp|change|clear|rename|specialize|generalize|suffices|wlog|fin_cases|interval_cases|norm_cast|field_simp|ring_nf|polyrith|nlinarith|aesop|tauto|itauto|decide|native_decide)\b'

    tactics = re.findall(tactic_pattern, proof.lower())
    return list(set(tactics))


def compute_key(statement: str) -> str:
    """Compute deterministic key from statement."""
    return hashlib.sha256(statement.encode()).hexdigest()[:16]


def ingest_to_arango(
    examples: List[Dict[str, Any]],
    db,
    batch_size: int = 100,
) -> Dict[str, int]:
    """Ingest examples into ArangoDB."""
    col = ensure_collection(
        db,
        "lean_theorems",
        indexes=[
            {"name": "idx_status", "type": "persistent", "fields": ["status"]},
            {"name": "idx_scope", "type": "persistent", "fields": ["scope"]},
        ],
    )

    ensure_view(
        db,
        "lean_theorems_search",
        "lean_theorems",
        fields=["formal_statement", "goal", "formal_proof", "tactics"],
    )

    stats = {"inserted": 0, "skipped": 0, "errors": 0}
    batch = []

    for i, ex in enumerate(examples):
        # Build document
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
            "status": "pending",  # Will be updated by compile-filter
            "created_at": datetime.utcnow().isoformat(),
        }

        batch.append(doc)

        if len(batch) >= batch_size:
            result = col.import_bulk(batch, on_duplicate="ignore")
            stats["inserted"] += result.get("created", 0)
            stats["skipped"] += result.get("ignored", 0)
            stats["errors"] += result.get("errors", 0)
            batch = []
            print(f"Progress: {i + 1}/{len(examples)} ({stats['inserted']} inserted)")

    # Final batch
    if batch:
        result = col.import_bulk(batch, on_duplicate="ignore")
        stats["inserted"] += result.get("created", 0)
        stats["skipped"] += result.get("ignored", 0)
        stats["errors"] += result.get("errors", 0)

    print(f"\nIngest complete: {stats}")
    return stats


def compile_filter(
    db,
    container: str = "lean_runner",
    timeout: int = 60,
    batch_size: int = 10,
) -> Dict[str, int]:
    """Compile-filter pending theorems, marking status=ok or status=error."""
    col = db.collection("lean_theorems")

    # Get pending theorems
    pending = list(db.aql.execute(
        "FOR t IN lean_theorems FILTER t.status == 'pending' RETURN t"
    ))

    print(f"Compile-filtering {len(pending)} pending theorems...")
    stats = {"ok": 0, "error": 0, "timeout": 0}

    for i, thm in enumerate(pending):
        # Build full Lean file
        code = f"""{thm['header']}

{thm['formal_statement']}
  {thm['formal_proof']}
"""

        try:
            # Write to container and compile
            temp_file = f"/tmp/proof_{thm['_key']}.lean"

            # Write code
            subprocess.run(
                ["docker", "exec", container, "bash", "-c", f"cat > {temp_file}"],
                input=code,
                text=True,
                check=True,
                timeout=10,
            )

            # Compile
            result = subprocess.run(
                ["docker", "exec", container, "bash", "-c",
                 f"cd /workspace && lake env lean '{temp_file}' 2>&1"],
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            # Cleanup
            subprocess.run(
                ["docker", "exec", container, "rm", "-f", temp_file],
                capture_output=True,
                timeout=5,
            )

            if result.returncode == 0:
                status = "ok"
                stats["ok"] += 1
            else:
                status = "error"
                stats["error"] += 1

            # Update document
            col.update({
                "_key": thm["_key"],
                "status": status,
                "compile_output": result.stdout[:1000] if result.stdout else None,
                "compiled_at": datetime.utcnow().isoformat(),
            })

        except subprocess.TimeoutExpired:
            col.update({
                "_key": thm["_key"],
                "status": "timeout",
                "compiled_at": datetime.utcnow().isoformat(),
            })
            stats["timeout"] += 1
        except Exception as e:
            col.update({
                "_key": thm["_key"],
                "status": "error",
                "compile_output": str(e)[:500],
                "compiled_at": datetime.utcnow().isoformat(),
            })
            stats["error"] += 1

        if (i + 1) % 10 == 0:
            print(f"Progress: {i + 1}/{len(pending)} (ok={stats['ok']}, error={stats['error']})")

    print(f"\nCompile-filter complete: {stats}")
    return stats


def main():
    parser = argparse.ArgumentParser(description="Ingest DeepSeek-Prover-V1 dataset")
    parser.add_argument("--limit", type=int, help="Limit number of examples to ingest")
    parser.add_argument("--compile-filter", action="store_true", help="Run compile-filter pass")
    parser.add_argument("--container", default="lean_runner", help="Docker container for compilation")
    parser.add_argument("--timeout", type=int, default=60, help="Compile timeout per theorem")
    parser.add_argument("--skip-ingest", action="store_true", help="Skip ingest, only compile-filter")

    args = parser.parse_args()

    db = get_db()
    print(f"Connected to ArangoDB: {os.getenv('ARANGO_URL', 'http://127.0.0.1:8529')}")

    if not args.skip_ingest:
        examples = load_dataset(limit=args.limit)
        ingest_to_arango(examples, db)

    if args.compile_filter:
        # Check container is running
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
        )
        if args.container not in result.stdout:
            print(f"Error: Container '{args.container}' not running")
            sys.exit(1)

        compile_filter(db, args.container, args.timeout)


if __name__ == "__main__":
    main()
