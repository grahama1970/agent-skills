#!/usr/bin/env python3
"""Edge Verifier — KNN + LLM verification for KG edges.

All graph traversal and edge writes delegate to /memory infrastructure
(graph_memory.lessons.recall, graph_memory.arango_utils) so that
edge-verifier never issues raw AQL.  Verification logic stays here.
"""
import typer
import asyncio
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import httpx

try:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True), override=False)

SKILLS_DIR = Path(__file__).resolve().parent.parent
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
        """Fallback: call proxy directly via httpx."""
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


def score_candidates(text: str, scope: str, k: int) -> List[Dict[str, Any]]:
    """Retrieve and score candidate lessons via /memory recall subprocess.

    Delegates BM25 + graph fusion + optional dense scoring to
    the /memory recall subcommand. Dense scores are attached for
    downstream stratified sampling.
    """
    args = ["recall", "--q", text, "--k", str(k * 2)]
    if scope:
        args.extend(["--scope", scope])
    try:
        result = _memory_cmd(args)
    except Exception:
        return []

    items = result.get("items", result.get("results", []))
    if not items:
        return []
    # Use the score returned by /memory as the primary sort key
    for item in items:
        item.setdefault("dense_score", item.get("_score", item.get("score", 0.0)))
        item.setdefault("score", item.get("dense_score", 0.0))
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
            custom_llm_provider="openai",
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
        edge_attrs = {
            "type": edge_type,
            "source": "edge-verifier",
            "llm_rationale": rationale,
            "weight_llm": weight,
            "stance": stance,
            "updated_at": ts,
            "created_at": ts,
        }

        # Delegate edge write to /memory infrastructure (no raw AQL).
        try:
            _memory_cmd([
                "learn",
                "--problem", f"edge:{edge_type}:{source_id}->{target_id}",
                "--solution", json.dumps(edge_attrs),
                "--scope", "operational",
                "--tag", f"edge,{edge_type},{stance}",
            ])
        except Exception as edge_err:
            print(f"[edge] write failed: {edge_err}")
            continue
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
    monitor = TaskClient("edge-verifier", total=3) if TaskClient else None
    print(f"KNN search (k={k}) for {source_id} ...")
    candidates = score_candidates(text, scope, k)
    if monitor:
        monitor.update(item="score_candidates")
    if not candidates:
        print("No candidates returned from hybrid search.")
        if monitor:
            monitor.finish()
        return

    samples = stratified_sample(candidates, sample_per_stratum)
    if monitor:
        monitor.update(item="stratified_sample")
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
            source_id,
            text,
            candidates,
            verify_top,
            max_llm,
        )
    )
    if monitor:
        monitor.update(item="verify_edges")
        monitor.finish()


if __name__ == "__main__":
    app()
