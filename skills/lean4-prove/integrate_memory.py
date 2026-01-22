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
import argparse
import os
import sys
from datetime import datetime
from typing import List, Dict, Any

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


def get_embedder():
    """Get embedding model or service."""
    service_url = os.getenv("EMBEDDING_SERVICE_URL")
    if service_url:
        import requests
        def embed(text: str) -> List[float]:
            resp = requests.post(f"{service_url}/embed", json={"text": text}, timeout=30)
            return resp.json()["vector"]
        return embed
    else:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")
        def embed(text: str) -> List[float]:
            return model.encode([text], normalize_embeddings=True)[0].tolist()
        return embed


def create_embeddings(db, batch_size: int = 100):
    """Embed all lean theorems and store in lesson_embeddings."""
    embed = get_embedder()

    # Ensure collection exists
    if not db.has_collection("lesson_embeddings"):
        db.create_collection("lesson_embeddings")
    emb_col = db.collection("lesson_embeddings")

    # Get proven theorems without embeddings (V1 and V2)
    aql = """
    FOR t IN lean_theorems
    FILTER t.status IN ["proven", "ok"]
    LET emb_key = CONCAT("lean_theorems_", t._key)
    LET existing = DOCUMENT("lesson_embeddings", emb_key)
    FILTER existing == null
    RETURN {_key: t._key, text: t.formal_statement}
    """

    pending = list(db.aql.execute(aql))
    print(f"Embedding {len(pending)} theorems...")

    batch = []
    for i, thm in enumerate(pending):
        text = thm["text"] or ""
        if len(text) > 512:
            text = text[:512]

        try:
            vector = embed(text)
            batch.append({
                "_key": f"lean_theorems_{thm['_key']}",
                "lesson_id": f"lean_theorems/{thm['_key']}",
                "vector": vector,
                "embedding": vector,  # Store in both fields for compatibility
                "source": "lean_theorem",
                "dim": len(vector),
                "model_id": "sentence-transformers/all-MiniLM-L6-v2",
                "content_hash": hash(text),
                "updated_at": datetime.utcnow().isoformat(),
            })
        except Exception as e:
            print(f"  Error embedding {thm['_key']}: {e}")
            continue

        if len(batch) >= batch_size:
            emb_col.import_bulk(batch, on_duplicate="replace")
            print(f"  Progress: {i + 1}/{len(pending)}")
            batch = []

    if batch:
        emb_col.import_bulk(batch, on_duplicate="replace")

    print(f"Embedded {len(pending)} theorems")


def create_edges(db, similarity_threshold: float = 0.7, max_edges_per_node: int = 5):
    """Create edges between similar theorems based on tactic overlap and embedding similarity."""

    # Ensure edge collection exists
    if not db.has_collection("lesson_edges"):
        db.create_collection("lesson_edges", edge=True)
    edge_col = db.collection("lesson_edges")

    # Strategy 1: Connect theorems with same primary tactics (V1 and V2)
    print("Creating tactic-based edges...")
    aql_tactics = """
    FOR t1 IN lean_theorems
    FILTER t1.status IN ["proven", "ok"]
    FILTER LENGTH(t1.tactics) > 0
    LET primary_tactic = FIRST(t1.tactics)
    FOR t2 IN lean_theorems
    FILTER t2.status IN ["proven", "ok"]
    FILTER t2._key != t1._key
    FILTER LENGTH(t2.tactics) > 0
    FILTER FIRST(t2.tactics) == primary_tactic
    LIMIT @max_edges
    RETURN DISTINCT {
        _from: CONCAT("lean_theorems/", t1._key),
        _to: CONCAT("lean_theorems/", t2._key),
        type: "same_tactic",
        tactic: primary_tactic,
        weight: 0.6
    }
    """

    tactic_edges = list(db.aql.execute(aql_tactics, bind_vars={"max_edges": 10000}))
    if tactic_edges:
        edge_col.import_bulk(tactic_edges, on_duplicate="ignore")
        print(f"  Created {len(tactic_edges)} tactic edges")

    # Strategy 2: Connect theorems with similar embeddings
    print("Creating semantic similarity edges...")

    # Get all proven theorems with embeddings (V1 and V2)
    aql_emb = """
    FOR t IN lean_theorems
    FILTER t.status IN ["proven", "ok"]
    LET emb = DOCUMENT("lesson_embeddings", CONCAT("lean_theorems_", t._key))
    FILTER emb != null
    LET vec = emb.vector != null ? emb.vector : emb.embedding
    FILTER vec != null
    RETURN {_key: t._key, vector: vec}
    """

    theorems = list(db.aql.execute(aql_emb))
    print(f"  Found {len(theorems)} theorems with embeddings")

    if len(theorems) < 2:
        print("  Skipping semantic edges (not enough embeddings)")
        return

    # Use numpy for fast similarity computation
    try:
        import numpy as np
        vectors = np.array([t["vector"] for t in theorems], dtype=np.float32)
        keys = [t["_key"] for t in theorems]

        # Compute pairwise similarities in batches
        batch_edges = []
        batch_size = 500

        for i in range(0, len(keys), batch_size):
            batch_vectors = vectors[i:i+batch_size]
            # Cosine similarity (vectors are already normalized)
            similarities = np.dot(batch_vectors, vectors.T)

            for j, sim_row in enumerate(similarities):
                src_idx = i + j
                # Get top-k similar (excluding self)
                top_indices = np.argsort(sim_row)[::-1][1:max_edges_per_node+1]

                for tgt_idx in top_indices:
                    if sim_row[tgt_idx] >= similarity_threshold:
                        batch_edges.append({
                            "_from": f"lean_theorems/{keys[src_idx]}",
                            "_to": f"lean_theorems/{keys[tgt_idx]}",
                            "type": "similar_embedding",
                            "weight": float(sim_row[tgt_idx]),
                        })

            if len(batch_edges) >= 1000:
                edge_col.import_bulk(batch_edges, on_duplicate="ignore")
                print(f"  Progress: {i + batch_size}/{len(keys)}, edges: {len(batch_edges)}")
                batch_edges = []

        if batch_edges:
            edge_col.import_bulk(batch_edges, on_duplicate="ignore")

        print(f"  Created semantic edges")

    except ImportError:
        print("  Skipping semantic edges (numpy not available)")


def main():
    parser = argparse.ArgumentParser(description="Integrate lean theorems with memory skill")
    parser.add_argument("--embeddings-only", action="store_true", help="Only create embeddings")
    parser.add_argument("--edges-only", action="store_true", help="Only create edges")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size for embeddings")
    parser.add_argument("--similarity-threshold", type=float, default=0.7, help="Min similarity for edges")

    args = parser.parse_args()

    db = get_db()
    print(f"Connected to ArangoDB: {db.name}")

    if not args.edges_only:
        create_embeddings(db, batch_size=args.batch_size)

    if not args.embeddings_only:
        create_edges(db, similarity_threshold=args.similarity_threshold)

    print("\nIntegration complete!")
    print("Lean theorems are now searchable via:")
    print("  - BM25: lean_theorems_search view")
    print("  - Semantic: lesson_embeddings collection")
    print("  - Graph: lesson_edges collection")


if __name__ == "__main__":
    main()
