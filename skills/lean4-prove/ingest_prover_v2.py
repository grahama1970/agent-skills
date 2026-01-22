#!/usr/bin/env python3
"""
Ingest DeepSeek-Prover-V2 dataset (Cartinoe5930) into ArangoDB.

This is a community-contributed dataset with 66.7k theorems.
"""
import argparse
import hashlib
import os
import re
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True))
except ImportError:
    pass


def get_db():
    from arango import ArangoClient
    url = os.getenv("ARANGO_URL", "http://127.0.0.1:8529")
    db_name = os.getenv("ARANGO_DB", "memory")
    user = os.getenv("ARANGO_USER", "root")
    password = os.getenv("ARANGO_PASS", "")
    client = ArangoClient(hosts=url)
    return client.db(db_name, username=user, password=password)


def update_progress(db, task_id: str, completed: int, total: int, status: str = "running"):
    """Update progress in task_states for inter-agent monitoring."""
    col = db.collection("task_states")
    col.insert({
        "_key": task_id,
        "task_type": "ingest",
        "scope": "lean_theorems_v2",
        "completed": completed,
        "total": total,
        "status": status,
        "percent": round(100 * completed / total, 1) if total else 0,
        "updated_at": datetime.utcnow().isoformat(),
    }, overwrite=True)


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


def ingest_to_arango(examples: List[Dict[str, Any]], db, batch_size: int = 100) -> Dict[str, int]:
    col = db.collection("lean_theorems")
    task_id = f"ingest_v2_{datetime.utcnow().strftime('%Y%m%d_%H%M')}"
    
    stats = {"inserted": 0, "skipped": 0, "errors": 0}
    batch = []
    total = len(examples)
    
    for i, ex in enumerate(examples):
        # V2 dataset structure may differ - adapt as needed
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
        
        batch.append(doc)
        
        if len(batch) >= batch_size:
            result = col.import_bulk(batch, on_duplicate="ignore")
            stats["inserted"] += result.get("created", 0)
            stats["skipped"] += result.get("ignored", 0)
            stats["errors"] += result.get("errors", 0)
            batch = []
            
            if (i + 1) % 1000 == 0:
                print(f"Progress: {i + 1}/{total} ({stats['inserted']} inserted)")
                update_progress(db, task_id, i + 1, total)
    
    if batch:
        result = col.import_bulk(batch, on_duplicate="ignore")
        stats["inserted"] += result.get("created", 0)
        stats["skipped"] += result.get("ignored", 0)
        stats["errors"] += result.get("errors", 0)
    
    update_progress(db, task_id, total, total, "complete")
    print(f"\nIngest complete: {stats}")
    return stats


def main():
    parser = argparse.ArgumentParser(description="Ingest DeepSeek-Prover-V2 dataset")
    parser.add_argument("--limit", type=int, help="Limit examples")
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()
    
    db = get_db()
    print(f"Connected to ArangoDB: {db.name}")
    
    examples = load_v2_dataset(limit=args.limit)
    ingest_to_arango(examples, db, batch_size=args.batch_size)


if __name__ == "__main__":
    main()
