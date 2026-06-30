#!/usr/bin/env python3
"""Module support for the lean4-prove skill."""
"""
ingest_autoformalization: Ingest HuggingFace autoformalization datasets into ArangoDB.

Follows the existing ingest_prover_v1.py pattern — ingests via /memory learn
subprocess, NOT direct ArangoDB access.

Supported datasets:
  - casey-martin/ntp-lean4-autoformalization (~10K English↔Lean4 pairs)
  - Goedel-LM/Lean-workbook-proofs (~500K verified proofs)
  - internlm/Lean-Workbook (NL + formal statement pairs)
  - phanerozoic/Lean4-FormalConjectures (2.5K DeepMind conjectures)
  - phanerozoic/Lean4-Mathlib (193K, import resolution / RAG)

EVAL-ONLY datasets (NEVER train):
  - cat-searcher/minif2f-lean4 (488, benchmark)
  - deepseek-ai/DeepSeek-ProverBench (competition benchmark)

Usage:
    python ingest_autoformalization.py --dataset casey-martin/ntp-lean4-autoformalization
    python ingest_autoformalization.py --dataset casey-martin/ntp-lean4-autoformalization --limit 100
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer

# Removed: memory accessed via httpx to Unix socket (see _memory_cmd)
# Tactic extraction regex (shared with ingest_prover_v1.py)
TACTIC_PATTERNS = [
    r'\b(simp|ring|omega|norm_num|decide|rfl|exact|apply|intro|have|let)',
    r'\b(induction|cases|rcases|obtain|constructor|ext|funext|congr)',
    r'\b(rw|rewrite|calc|show|suffices|by_contra|push_neg|contrapose)',
    r'\b(aesop|linarith|nlinarith|positivity|field_simp|ring_nf|norm_cast)',
    r'\b(trivial|assumption|contradiction|exfalso|absurd)',
]


def extract_tactics(proof: str) -> List[str]:
    """Extract tactic names from Lean4 proof text."""
    tactics = set()
    for pattern in TACTIC_PATTERNS:
        for match in re.finditer(pattern, proof or ""):
            tactics.add(match.group(1))
    return sorted(tactics)


def compute_key(text: str) -> str:
    """Deterministic SHA256 key from text content."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _memory_learn(doc: Dict[str, Any], collection: str = "lean4_autoformalization") -> bool:
    """Store a document via /memory learn subprocess."""
    try:
        payload = json.dumps(doc)
        result = subprocess.run(
            [MEMORY_RUN, "learn", "--collection", collection, "--json", payload],
            capture_output=True, text=True, timeout=30,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        return result.returncode == 0
    except Exception:
        return False


def load_dataset(dataset_id: str, limit: int = 0, split: str = "train") -> List[Dict]:
    """Load a HuggingFace dataset.

    Args:
        dataset_id: HuggingFace dataset identifier
        limit: Max rows (0 = all)
        split: Dataset split

    Returns:
        List of example dicts
    """
    from datasets import load_dataset as hf_load
import httpx

    token = os.getenv("HF_TOKEN")
    ds = hf_load(dataset_id, split=split, token=token)

    examples = []
    for i, row in enumerate(ds):
        if limit and i >= limit:
            break
        examples.append(dict(row))

    return examples


# ---------------------------------------------------------------------------
# Dataset-specific adapters
# ---------------------------------------------------------------------------

def _adapt_ntp_autoformalization(row: Dict) -> Dict:
    """Adapt casey-martin/ntp-lean4-autoformalization format."""
    english = row.get("nl_statement", row.get("informal_statement", ""))
    lean4_stmt = row.get("formal_statement", row.get("lean_statement", ""))
    lean4_proof = row.get("formal_proof", row.get("lean_proof", ""))
    header = row.get("header", "")

    return {
        "_key": compute_key(f"{english}:{lean4_stmt}"),
        "english": english,
        "lean4_statement": lean4_stmt,
        "lean4_proof": lean4_proof,
        "header": header,
        "tactics": extract_tactics(lean4_proof),
        "source": "casey-martin/ntp-lean4-autoformalization",
        "verified": False,
        "round_trip_ok": None,
    }


def _adapt_lean_workbook_proofs(row: Dict) -> Dict:
    """Adapt Goedel-LM/Lean-workbook-proofs format."""
    statement = row.get("formal_statement", row.get("statement", ""))
    proof = row.get("proof", row.get("formal_proof", ""))
    nl = row.get("nl_statement", row.get("natural_language", ""))

    return {
        "_key": compute_key(f"{statement}:{proof}"),
        "english": nl,
        "lean4_statement": statement,
        "lean4_proof": proof,
        "header": row.get("header", ""),
        "tactics": extract_tactics(proof),
        "source": "Goedel-LM/Lean-workbook-proofs",
        "verified": True,  # Pre-verified by Goedel-Prover
        "round_trip_ok": None,
    }


def _adapt_internlm_workbook(row: Dict) -> Dict:
    """Adapt internlm/Lean-Workbook format."""
    nl = row.get("natural_language_statement", row.get("informal_statement", ""))
    formal = row.get("formal_statement", "")
    proof = row.get("proof", "")

    return {
        "_key": compute_key(f"{nl}:{formal}"),
        "english": nl,
        "lean4_statement": formal,
        "lean4_proof": proof,
        "header": row.get("header", ""),
        "tactics": extract_tactics(proof),
        "source": "internlm/Lean-Workbook",
        "verified": bool(proof),
        "round_trip_ok": None,
    }


def _adapt_formal_conjectures(row: Dict) -> Dict:
    """Adapt phanerozoic/Lean4-FormalConjectures format."""
    statement = row.get("lean_statement", row.get("formal_statement", ""))
    nl = row.get("description", row.get("informal_statement", ""))

    return {
        "_key": compute_key(statement),
        "english": nl,
        "lean4_statement": statement,
        "lean4_proof": "",  # Conjectures — no proof
        "header": row.get("header", ""),
        "tactics": [],
        "source": "phanerozoic/Lean4-FormalConjectures",
        "verified": False,
        "round_trip_ok": None,
    }


def _adapt_generic(row: Dict, dataset_id: str) -> Dict:
    """Generic adapter for unknown dataset formats."""
    # Try common field names
    english = (
        row.get("nl_statement")
        or row.get("informal_statement")
        or row.get("natural_language")
        or row.get("description")
        or ""
    )
    statement = (
        row.get("formal_statement")
        or row.get("lean_statement")
        or row.get("statement")
        or ""
    )
    proof = (
        row.get("formal_proof")
        or row.get("lean_proof")
        or row.get("proof")
        or ""
    )

    return {
        "_key": compute_key(f"{english}:{statement}"),
        "english": english,
        "lean4_statement": statement,
        "lean4_proof": proof,
        "header": row.get("header", ""),
        "tactics": extract_tactics(proof),
        "source": dataset_id,
        "verified": False,
        "round_trip_ok": None,
    }


ADAPTERS = {
    "casey-martin/ntp-lean4-autoformalization": _adapt_ntp_autoformalization,
    "Goedel-LM/Lean-workbook-proofs": _adapt_lean_workbook_proofs,
    "internlm/Lean-Workbook": _adapt_internlm_workbook,
    "phanerozoic/Lean4-FormalConjectures": _adapt_formal_conjectures,
}


def ingest_to_memory(
    examples: List[Dict],
    dataset_id: str,
    batch_size: int = 500,
) -> Dict[str, int]:
    """Ingest examples into ArangoDB via /memory learn.

    Args:
        examples: Raw HuggingFace examples
        dataset_id: Dataset identifier (for adapter selection)
        batch_size: Progress report interval

    Returns:
        Stats dict: {inserted, skipped, errors}
    """
    adapter = ADAPTERS.get(dataset_id, lambda row: _adapt_generic(row, dataset_id))

    stats = {"inserted": 0, "skipped": 0, "errors": 0}
    t0 = time.time()

    for i, row in enumerate(examples):
        try:
            doc = adapter(row)
        except Exception as e:
            print(f"  Adapter error at row {i}: {e}", file=sys.stderr)
            stats["errors"] += 1
            continue

        # Skip empty entries
        if not doc.get("lean4_statement") and not doc.get("english"):
            stats["skipped"] += 1
            continue

        # Add timestamp
        doc["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")

        if _memory_learn(doc):
            stats["inserted"] += 1
        else:
            stats["errors"] += 1

        # Progress
        if (i + 1) % batch_size == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            print(
                f"  Progress: {i + 1}/{len(examples)} "
                f"({stats['inserted']} inserted, {stats['errors']} errors, "
                f"{rate:.0f} rows/s)",
                file=sys.stderr,
            )

    elapsed = time.time() - t0
    print(
        f"  Done: {stats['inserted']} inserted, {stats['skipped']} skipped, "
        f"{stats['errors']} errors in {elapsed:.1f}s",
        file=sys.stderr,
    )

    return stats


def main(
    dataset: str = "casey-martin/ntp-lean4-autoformalization",
    limit: int = 0,
    batch_size: int = 500,
    split: str = "train",
):
    """Main ingestion entry point.

    Args:
        dataset: HuggingFace dataset identifier
        limit: Max rows (0 = all)
        batch_size: Progress report interval
        split: Dataset split
    """
    # Guard: NEVER ingest eval-only datasets into training collection
    EVAL_ONLY = {"cat-searcher/minif2f-lean4", "deepseek-ai/DeepSeek-ProverBench"}
    if dataset in EVAL_ONLY:
        print(
            f"ERROR: {dataset} is EVAL-ONLY. NEVER ingest into training collection.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Loading dataset: {dataset} (split={split}, limit={limit or 'all'})")
    examples = load_dataset(dataset, limit=limit, split=split)
    print(f"  Loaded {len(examples)} examples")

    if not examples:
        print("  No examples found — skipping ingestion.", file=sys.stderr)
        return

    print(f"Ingesting into lean4_autoformalization collection...")
    stats = ingest_to_memory(examples, dataset, batch_size=batch_size)

    # Output summary as JSON
    print(json.dumps({
        "dataset": dataset,
        "total_loaded": len(examples),
        **stats,
    }, indent=2))


if __name__ == "__main__":
    typer.run(main)
