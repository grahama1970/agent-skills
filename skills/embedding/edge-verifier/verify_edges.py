#!/usr/bin/env python3
"""verify_edges - edge-verifier.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

import typer
import asyncio
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import httpx

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True), override=False)

try:
    from graph_memory.arango_client import get_db
    from graph_memory.api import search as gm_search
    from graph_memory.lessons import recall as recall_utils
except ImportError as e:
    print(f"Error importing graph_memory: {e}")
    sys.exit(1)

try:
    from scillm import parallel_acompletions
except ImportError:
    scillm_path = os.getenv("SCILLM_PATH")
    if scillm_path and scillm_path not in sys.path:
        sys.path.append(scillm_path)
    try:
        from scillm import parallel_acompletions
    except ImportError:
        parallel_acompletions = None

if not parallel_acompletions:

    async def parallel_acompletions(reqs, api_base=None, api_key=None, **kwargs):
        """Fallback: call Chutes directly."""
        results = []
        headers = {
            "Authorization": f"Bearer {api_key or os.getenv('SCILLM_PROXY_KEY', 'sk-dev-proxy-123')}",
            "Content-Type": "application/json",
        }
        base = api_base or os.getenv("SCILLM_API_BASE", "http://localhost:4001")
        for req in reqs:
            try:
                payload = {
                    "model": req.get("model"),
                    "messages": req.get("messages"),
                    "temperature": req.get("temperature", 0.0),
                    "response_format": req.get("response_format"),
                }
                resp = httpx.post(
                    f"{base}/chat/completions", json=payload, headers=headers, timeout=30
                )
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    results.append({"content": content, "ok": True})
                else:
                    results.append({"error": f"HTTP {resp.status_code}", "ok": False})
            except Exception as exc:
                results.append({"error": str(exc), "ok": False})
        return results


def _normalize_bm25(value: float) -> float:
    return min(1.0, max(0.0, value / 20.0))


def score_candidates(db, text: str, scope: str, k: int) -> List[Dict[str, Any]]:
    raw = gm_search(q=text, scope=scope, k=k * 2)
    items = raw.get("items", [])
    if not items:
        return []
    # Use the same helper as recall.py so VECTOR_ENGINE=cuvs triggers cuVS search and FAISS is the fallback.
    dense_scores = recall_utils._maybe_dense_scores(db, lessons=items, q=text, k=len(items))
    for item in items:
        bm25 = float(item.get("scores", {}).get("bm25", 0.0))
        dense = float(dense_scores.get(str(item.get("_key")), 0.0))
        item["dense_score"] = dense
        item["bm25_score"] = bm25
        item["score"] = 0.7 * dense + 0.3 * _normalize_bm25(bm25)
    items.sort(key=lambda entry: entry.get("score", 0.0), reverse=True)
    return items


def stratified_sample(candidates: List[Dict[str, Any]], per_stratum: int) -> Dict[str, List[Dict[str, Any]]]:
    buckets = {"low": [], "mid": [], "high": []}
    for item in candidates:
        val = item.get("dense_score", 0.0)
        if val < 0.35:
            buckets["low"].append(item)
        elif val < 0.65:
            buckets["mid"].append(item)
        else:
            buckets["high"].append(item)
    samples: Dict[str, List[Dict[str, Any]]] = {}
    for level, bucket in buckets.items():
        if not bucket or per_stratum <= 0:
            samples[level] = []
            continue
        count = min(per_stratum, len(bucket))
        samples[level] = random.sample(bucket, count)
    return samples


async def verify_and_create_edges(
    db,
    source_id: str,
    content_summary: str,
    candidates: List[Dict[str, Any]],
    verify_top: int,
    max_calls: int,
):
    if not candidates:
        print("No candidates available for verification.")
        return

    chosen = candidates[:verify_top]
    if not chosen:
        print("No candidates passed the scoring filter.")
        return

    system_prompt = (
        "You are a Knowledge Graph Auditor. Score the relationship between an episodic memory and a knowledge lesson. "
        'Return JSON { "weight": float, "stance": "supports"|"contradicts"|"neutral"|"irrelevant", "rationale": string }.'
    )

    # Try gateway-first approach via /assistant validate
    _use_gateway = os.environ.get("EDGE_VERIFIER_USE_GATEWAY", "1") == "1"
    _gateway_available = False
    if _use_gateway:
        try:
            _assistant_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assistant")
            if _assistant_dir not in sys.path:
                sys.path.insert(0, _assistant_dir)
            from assistant import validate as _gw_validate
            _gateway_available = True
        except ImportError:
            _gateway_available = False

    if _gateway_available:
        # Gateway path: route through 4-tier cascade
        responses_gw = []
        for cand in chosen:
            input_data = {
                "source_episode": {"id": source_id, "summary": content_summary[:800]},
                "target_lesson": {
                    "id": cand.get("_key"),
                    "title": cand.get("title"),
                    "problem": (cand.get("problem") or "")[:400],
                },
            }
            try:
                gw_result = _gw_validate(
                    input_data=input_data,
                    task="edge-relevance-scorer",
                )
                responses_gw.append({"content": json.dumps(gw_result.result)})
            except Exception as e:
                responses_gw.append({"error": str(e)})
        responses = responses_gw
    else:
        # Fallback: original parallel_acompletions path
        reqs = []
        for cand in chosen:
            payload = {
                "task": "verify_episodic_relevance",
                "source_episode": {"id": source_id, "summary": content_summary[:800]},
                "target_lesson": {
                    "id": cand.get("_key"),
                    "title": cand.get("title"),
                    "problem": (cand.get("problem") or "")[:400],
                },
            }
            reqs.append(
                {
                    "model": os.getenv("CHUTES_TEXT_MODEL", "sonar-medium"),
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": json.dumps(payload)},
                    ],
                    "temperature": 0.0,
                    "response_format": {"type": "json_object"},
                }
            )

        responses = await parallel_acompletions(
            reqs,
            api_base=os.getenv("SCILLM_API_BASE", "http://localhost:4001"),
            api_key=os.getenv("SCILLM_PROXY_KEY", "sk-dev-proxy-123"),
            custom_llm_provider="openai_like",
            timeout=45,
        )

    inserted = 0
    for idx, result in enumerate(responses):
        if result.get("error"):
            continue
        try:
            data = json.loads(result.get("content") or "{}")
            stance = (data.get("stance") or "irrelevant").lower()
            weight = float(data.get("weight", 0.0))
            rationale = data.get("rationale", "")
        except Exception:
            continue

        if stance not in {"supports", "contradicts", "neutral"}:
            continue
        if stance == "neutral" and weight <= 0.5:
            continue

        target_id = chosen[idx].get("_id")
        if not target_id:
            continue

        edge_type = "related"
        if stance == "supports":
            edge_type = "verifies"
        elif stance == "contradicts":
            edge_type = "contradicts"

        ts = int(time.time())
        edge_doc = {
            "_from": source_id,
            "_to": target_id,
            "type": edge_type,
            "source": "edge-verifier",
            "llm_rationale": rationale,
            "weight_llm": weight,
            "stance": stance,
            "updated_at": ts,
            "created_at": ts,
        }

        db.aql.execute(
            """
            UPSERT { _from: @_from, _to: @_to, type: @type }
            INSERT @doc
            UPDATE {
                llm_rationale: @doc.llm_rationale,
                weight_llm: @doc.weight_llm,
                stance: @doc.stance,
                updated_at: @doc.updated_at
            } IN lesson_edges
            """,
            bind_vars={
                "_from": source_id,
                "_to": target_id,
                "type": edge_type,
                "doc": edge_doc,
            },
        )
        print(
            f"[edge] {edge_type} ({weight:.2f}) → {chosen[idx].get('title')} (dense={chosen[idx].get('dense_score'):.3f})"
        )
        inserted += 1
        if max_calls and inserted >= max_calls:
            print(f"Max LLM edge count reached ({max_calls}); stopping verification loop.")
            break

    print(f"Total edges upserted: {inserted}")


app = typer.Typer(help="Verify episodic edges via KNN + LLM")


@app.command()
def main(
    source_id: str = typer.Option(..., help="Document id for the episode/turn (lessons/<key>)"),
    text: str = typer.Option(..., help="Text content to compare"),
    scope: str = typer.Option("", help="Optional scope filter"),
    k: int = typer.Option(25, help="Initial candidate pool size"),
    verify_top: int = typer.Option(5, help="How many candidates to pass to the LLM"),
    sample_per_stratum: int = typer.Option(5, help="Audit sample per similarity stratum"),
    max_llm: int = typer.Option(int(os.getenv("EDGE_VERIFIER_MAX_LLM", "0") or 0), help="Maximum LLM verifications to run this execution (0 = no limit)"),
):
    db = get_db()
    print(f"KNN search (k={k}) for {source_id} ...")
    candidates = score_candidates(db, text, scope, k)
    if not candidates:
        print("No candidates returned from hybrid search.")
        return

    samples = stratified_sample(candidates, sample_per_stratum)
    for level, rows in samples.items():
        if not rows:
            continue
        print(f"[sample:{level}] {len(rows)} candidates")
        for row in rows:
            print(
                json.dumps(
                    {
                        "lesson": row.get("_id"),
                        "title": row.get("title"),
                        "dense_score": row.get("dense_score"),
                        "bm25_score": row.get("bm25_score"),
                    }
                )
            )

    asyncio.run(
        verify_and_create_edges(
            db,
            source_id,
            text,
            candidates,
            verify_top,
            max_llm,
        )
    )


if __name__ == "__main__":
    app()
