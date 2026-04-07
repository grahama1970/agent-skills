#!/usr/bin/env python3
"""Taxonomy Sweep — Classify untagged lessons with bridge attributes.

Queries ArangoDB for lessons missing bridge_attributes, runs keyword-based
taxonomy extraction, and updates documents. Nightly complement to edge-verifier.

Uses common.taxonomy for extraction (keyword mode by default, LLM mode optional).
"""
import os
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List
from loguru import logger

try:
    import typer
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "typer", "-q"],
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )
    import typer

try:
    from dotenv import find_dotenv, load_dotenv
    load_dotenv(find_dotenv(usecwd=True), override=False)
except Exception as e:
    logger.debug("loading failed: {}", e)

# Add skills root to path for common imports
SKILLS_DIR = Path(__file__).parent.parent
if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))

try:
    from common.taxonomy import (
        extract_taxonomy_features,
        get_bridge_attributes,
        ContentType,
    )
    HAS_TAXONOMY = True
except ImportError as e:
    print(f"[taxonomy-sweep] Cannot import common.taxonomy: {e}", file=sys.stderr)
    HAS_TAXONOMY = False

import subprocess

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
            resp = client.post("/list", json={"collection": coll, "limit": 0})
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

try:
    sys.path.insert(0, str(Path(__file__).parent.parent / "edge-verifier"),
    env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )
    from task_monitor_client import EdgeVerifierTaskClient
    TASK_MONITOR_AVAILABLE = True
except ImportError:
    TASK_MONITOR_AVAILABLE = False


def find_unclassified(collection: str = "lessons", scope: str = "", limit: int = 500) -> List[Dict[str, Any]]:
    """Find documents missing bridge_attributes via /memory sample."""
    cmd = ["sample", "--collection", collection, "--limit", str(limit),
           "--filter", "bridge_attributes==null"]
    if scope:
        cmd += ["--scope", scope]
    return _memory_cmd(cmd, timeout=120)


def classify_keyword(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Classify a document using keyword-based extraction (fast, no LLM)."""
    title = doc.get("title") or ""
    problem = doc.get("problem") or ""
    solution = doc.get("solution") or ""
    tags = doc.get("tags") or []

    combined_text = f"{title} {problem} {solution}"

    if HAS_TAXONOMY:
        result = extract_taxonomy_features(
            content_type=ContentType.OPERATIONAL,
            title=title,
            description=f"{problem} {solution}",
            tags=tags,
        )
        return {
            "bridge_attributes": result.bridge_attributes,
            "taxonomy": {
                "content_type": result.content_type,
                "collection_tags": {
                    "domain": result.collection_tags.domain if result.collection_tags else [],
                    "thematic_weight": result.collection_tags.thematic_weight if result.collection_tags else [],
                    "function": result.collection_tags.function if result.collection_tags else [],
                    "perspective": result.collection_tags.perspective if result.collection_tags else [],
                },
                "confidence": result.confidence,
            },
        }
    else:
        # Fallback: use local get_bridge_attributes from taxonomy.py
        from taxonomy import _get_bridge_keywords
        bridges = []
        text_lower = combined_text.lower()
        for attr, keywords in _get_bridge_keywords().items():
            for kw in keywords:
                if kw in text_lower:
                    if attr not in bridges:
                        bridges.append(attr)
                    break
        return {
            "bridge_attributes": bridges[:3],
            "taxonomy": {"content_type": "operational", "confidence": 0.3},
        }


def classify_llm(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Classify using LLM extraction (slower, higher quality)."""
    if not HAS_TAXONOMY:
        return classify_keyword(doc)

    title = doc.get("title") or ""
    problem = doc.get("problem") or ""
    solution = doc.get("solution") or ""
    tags = doc.get("tags") or []

    # LLM mode uses high_fidelity=True in extract_taxonomy_features
    # but that requires scillm. For now, just use keyword with enriched text.
    result = extract_taxonomy_features(
        content_type=ContentType.OPERATIONAL,
        title=title,
        description=f"{problem} {solution}",
        tags=tags,
    )
    return {
        "bridge_attributes": result.bridge_attributes,
        "taxonomy": {
            "content_type": result.content_type,
            "collection_tags": {
                "domain": result.collection_tags.domain if result.collection_tags else [],
                "thematic_weight": result.collection_tags.thematic_weight if result.collection_tags else [],
                "function": result.collection_tags.function if result.collection_tags else [],
                "perspective": result.collection_tags.perspective if result.collection_tags else [],
            },
            "confidence": result.confidence,
        },
    }


def _load_classifier(model_path: str = "") -> tuple:
    """Load trained bridge-tag classifier model.

    Returns:
        (model, scaler, embedding_dim) or (None, None, None) if not available
    """
    if not model_path:
        model_path = str(Path(__file__).parent / "data" / "bridge_text_classifier.joblib")
    path = Path(model_path)
    if not path.exists():
        return None, None, None
    try:
        import joblib
        bundle = joblib.load(path)
        return bundle["model"], bundle.get("scaler"), bundle.get("embedding_dim", 384)
    except Exception as e:
        print(f"[taxonomy-sweep] Failed to load classifier: {e}", file=sys.stderr)
        return None, None, None


def _embed_text(text: str, embedding_url: str = "http://127.0.0.1:8602") -> list[float] | None:
    """Embed a single text via the embedding service."""
    try:
        import httpx
        resp = httpx.post(f"{embedding_url}/embed", json={"text": text}, timeout=30.0)
        resp.raise_for_status()
        return resp.json()["vector"]
    except Exception:
        return None


def _embed_texts_batch(texts: list[str], embedding_url: str = "http://127.0.0.1:8602",
                       batch_size: int = 64) -> list[list[float]]:
    """Embed multiple texts via the embedding service."""
    import httpx
    all_vectors = []
    client = httpx.Client(timeout=60.0)
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        try:
            resp = client.post(f"{embedding_url}/embed/batch", json={"texts": batch})
            resp.raise_for_status()
            all_vectors.extend(resp.json()["vectors"])
        except Exception:
            all_vectors.extend([[0.0] * 384] * len(batch))
    client.close()
    return all_vectors


BRIDGE_TAGS = ["Precision", "Resilience", "Fragility", "Corruption", "Loyalty", "Stealth"]


def classify_ml(doc: dict, model, scaler, embedding_url: str) -> dict:
    """Classify a document using trained ML classifier."""
    import numpy as np

    problem = doc.get("problem") or ""
    solution = doc.get("solution") or ""
    text = f"{problem}\n{solution}".strip()
    if not text:
        return {"bridge_attributes": [], "taxonomy": {"content_type": "operational", "confidence": 0.0}}

    vector = _embed_text(text, embedding_url)
    if vector is None:
        return {"bridge_attributes": [], "taxonomy": {"content_type": "operational", "confidence": 0.0}}

    X = np.array([vector])
    if scaler is not None:
        X = scaler.transform(X)

    # Multi-label prediction with probabilities
    if hasattr(model, "predict_proba"):
        probas = model.predict_proba(X)
        if isinstance(probas, list):
            scores = {}
            for i in range(min(len(probas), len(BRIDGE_TAGS))):
                if probas[i].shape[1] > 1:
                    scores[BRIDGE_TAGS[i]] = float(probas[i][0][1])
                else:
                    scores[BRIDGE_TAGS[i]] = float(probas[i][0][0])
            bridges = [tag for tag, score in scores.items() if score >= 0.5]
            confidence = max(scores.values()) if scores else 0.0
        else:
            bridges = []
            confidence = 0.0
    else:
        preds = model.predict(X)[0]
        bridges = [BRIDGE_TAGS[i] for i in range(len(preds)) if preds[i] == 1]
        confidence = 0.6

    return {
        "bridge_attributes": bridges,
        "taxonomy": {"content_type": "operational", "confidence": round(confidence, 3)},
    }


def classify_ml_batch(docs: list[dict], model, scaler,
                      embedding_url: str) -> list[dict]:
    """Classify a batch of documents using trained ML classifier."""
    import numpy as np

    texts = []
    for doc in docs:
        problem = doc.get("problem") or ""
        solution = doc.get("solution") or ""
        texts.append(f"{problem}\n{solution}".strip())

    vectors = _embed_texts_batch(texts, embedding_url)
    X = np.array(vectors)
    if scaler is not None:
        X = scaler.transform(X)

    results = []
    if hasattr(model, "predict_proba"):
        probas = model.predict_proba(X)
        for row_idx in range(len(docs)):
            scores = {}
            for i in range(min(len(probas), len(BRIDGE_TAGS))):
                if probas[i].shape[1] > 1:
                    scores[BRIDGE_TAGS[i]] = float(probas[i][row_idx][1])
                else:
                    scores[BRIDGE_TAGS[i]] = float(probas[i][row_idx][0])
            bridges = [tag for tag, score in scores.items() if score >= 0.5]
            confidence = max(scores.values()) if scores else 0.0
            results.append({
                "bridge_attributes": bridges,
                "taxonomy": {"content_type": "operational", "confidence": round(confidence, 3)},
            })
    else:
        preds = model.predict(X)
        for row_idx in range(len(docs)):
            bridges = [BRIDGE_TAGS[i] for i in range(preds.shape[1]) if preds[row_idx][i] == 1]
            results.append({
                "bridge_attributes": bridges,
                "taxonomy": {"content_type": "operational", "confidence": 0.6},
            })

    return results


app = typer.Typer()

@app.command()
def sweep(
    collection: str = typer.Option("lessons", help="ArangoDB collection to sweep"),
    mode: str = typer.Option("keyword", help="Extraction mode: keyword, llm, classifier"),
    scope: str = typer.Option("", help="Optional scope filter"),
    limit: int = typer.Option(500, help="Max documents to process per run"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Find unclassified docs only, don't update"),
    task_monitor: bool = typer.Option(False, "--task-monitor", help="Register with task-monitor"),
    json_stream: bool = typer.Option(False, "--json-stream", help="Output NDJSON per document"),
    model_path: str = typer.Option("", help="Path to trained classifier (for --mode classifier)"),
    embedding_url: str = typer.Option("http://127.0.0.1:8602", help="Embedding service URL"),
    batch_size: int = typer.Option(64, help="Batch size for classifier mode embedding"),
):
    """Sweep unclassified documents and apply taxonomy bridge attributes."""
    print(f"[taxonomy-sweep] Collection: {collection}, mode: {mode}, scope: {scope or '(any)'}", file=sys.stderr)

    # Load classifier model if needed
    ml_model, ml_scaler = None, None
    if mode == "classifier":
        ml_model, ml_scaler, emb_dim = _load_classifier(model_path)
        if ml_model is None:
            print("[taxonomy-sweep] ERROR: No trained classifier found. Train one first:", file=sys.stderr)
            print("  python train_bridge_text_classifier.py --db memory --no-sweep", file=sys.stderr)
            sys.exit(1)
        print(f"[taxonomy-sweep] Loaded ML classifier (embedding_dim={emb_dim})", file=sys.stderr)

    docs = find_unclassified(collection=collection, scope=scope, limit=limit)
    print(f"[taxonomy-sweep] Found {len(docs)} unclassified documents", file=sys.stderr)

    if dry_run:
        for doc in docs:
            print(json.dumps({"_key": doc["_key"], "title": doc.get("title", "?")}, ensure_ascii=False), flush=True)
        print(f"\n[taxonomy-sweep] Dry run complete: {len(docs)} unclassified docs found", file=sys.stderr)
        return

    if not docs:
        print("[taxonomy-sweep] No unclassified documents found", file=sys.stderr)
        return

    monitor = None
    if task_monitor and TASK_MONITOR_AVAILABLE:
        monitor = EdgeVerifierTaskClient("taxonomy-sweep", len(docs))

    classified = 0
    failed = 0
    skipped = 0
    ts = int(time.time())

    if mode == "classifier":
        # Batch mode: embed all docs at once for efficiency
        for batch_start in range(0, len(docs), batch_size):
            batch_docs = docs[batch_start:batch_start + batch_size]
            try:
                results = classify_ml_batch(batch_docs, ml_model, ml_scaler, embedding_url)
                for doc, result in zip(batch_docs, results):
                    bridges = result.get("bridge_attributes", [])
                    if not bridges:
                        skipped += 1
                        continue

                    tags = {
                        "bridge_attributes": bridges,
                        "taxonomy": result.get("taxonomy"),
                        "taxonomy_method": "sweep-classifier",
                        "taxonomy_updated_at": ts,
                    }
                    _memory_cmd([
                        "tag", "--collection", collection,
                        "--key", doc["_key"],
                        "--tags", json.dumps(tags),
                        "--field", "bridge_attributes",
                    ])
                    classified += 1

                    if json_stream:
                        print(json.dumps({
                            "_key": doc["_key"],
                            "title": doc.get("title", "?"),
                            "bridge_attributes": bridges,
                            "status": "classified",
                        }), flush=True)
            except Exception as e:
                print(f"[taxonomy-sweep] Batch error at {batch_start}: {e}", file=sys.stderr)
                failed += len(batch_docs)

            if monitor:
                monitor.update(f"batch_{batch_start}", edges_created=classified,
                               candidates_scored=batch_start + len(batch_docs))

            print(f"[taxonomy-sweep] Batch {batch_start}-{batch_start+len(batch_docs)}: "
                  f"classified={classified}, skipped={skipped}", file=sys.stderr)
    else:
        classify_fn = classify_llm if mode == "llm" else classify_keyword

        for idx, doc in enumerate(docs):
            try:
                result = classify_fn(doc)
                bridges = result.get("bridge_attributes", [])

                if not bridges:
                    skipped += 1
                    continue

                # Update the document via /memory tag
                tags = {
                    "bridge_attributes": bridges,
                    "taxonomy": result.get("taxonomy"),
                    "taxonomy_method": f"sweep-{mode}",
                    "taxonomy_updated_at": ts,
                }
                _memory_cmd([
                    "tag", "--collection", collection,
                    "--key", doc["_key"],
                    "--tags", json.dumps(tags),
                    "--field", "bridge_attributes",
                ])
                classified += 1

                if json_stream:
                    print(json.dumps({
                        "_key": doc["_key"],
                        "title": doc.get("title", "?"),
                        "bridge_attributes": bridges,
                        "status": "classified",
                    }), flush=True)

            except Exception as e:
                print(f"[taxonomy-sweep] Error processing {doc['_key']}: {e}", file=sys.stderr)
                failed += 1

            if monitor and (idx + 1) % 10 == 0:
                monitor.update(f"batch_{idx}", edges_created=classified, candidates_scored=idx + 1)

    if monitor:
        monitor.finish()

    # Summary
    print(f"\n[taxonomy-sweep] === SWEEP COMPLETE ===", file=sys.stderr)
    print(f"  Total unclassified:  {len(docs)}", file=sys.stderr)
    print(f"  Classified:          {classified}", file=sys.stderr)
    print(f"  Skipped (no match):  {skipped}", file=sys.stderr)
    print(f"  Failed:              {failed}", file=sys.stderr)

    # NDJSON summary line
    print(json.dumps({
        "collection": collection,
        "mode": mode,
        "total": len(docs),
        "classified": classified,
        "skipped": skipped,
        "failed": failed,
    }), flush=True)


if __name__ == "__main__":
    app()
