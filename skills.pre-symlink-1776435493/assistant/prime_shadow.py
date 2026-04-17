#!/usr/bin/env python3
"""Prime shadow data by batching samples through /scillm parallel_acompletions_iter.

Pulls samples from ArangoDB, builds prompts per task/persona, and sends them
through scillm's batch API. Results are written to shadow.jsonl for
/assistant-lab agreement tracking.

Designed to be called from:
  - Manual: uv run --directory ~/.pi/skills/scillm python ~/.pi/skills/assistant/prime_shadow.py --task qra-assessor --samples 100
  - /monitor-memory nightly: same invocation via scheduler
  - /assistant-lab: as part of auto-improve when shadow data is insufficient

IMPORTANT: This script MUST run within scillm's venv (via uv run --directory)
to access parallel_acompletions_iter per the SCILLM_PAVED_PATH_CONTRACT.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer
from loguru import logger

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SKILL_DIR = Path(__file__).resolve().parent
SKILLS_DIR = SKILL_DIR.parent
PROMPT_DIR = SKILLS_DIR / "prompt-lab" / "prompts"


def _load_prompt(name: str) -> str:
    """Load a validated prompt from /prompt-lab/prompts/{name}.txt."""
    path = PROMPT_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(
            f"Prompt '{name}' not found at {path}. "
            f"Run /prompt-lab eval to create and validate it."
        )
    return path.read_text().strip()
SHADOW_FILE = Path("~/.pi/assistant/shadow.jsonl").expanduser()
METRICS_FILE = Path("~/.pi/assistant/metrics.jsonl").expanduser()

# ---------------------------------------------------------------------------
# dotenv
# ---------------------------------------------------------------------------
try:
    from dotenv import find_dotenv, load_dotenv
    load_dotenv(find_dotenv(usecwd=True), override=False)
    _root_env = SKILLS_DIR.parent / ".env"
    if _root_env.exists():
        load_dotenv(_root_env, override=False)
except ImportError:
    pass

app = typer.Typer(add_completion=False, help="Prime shadow data via /scillm batch")

# ---------------------------------------------------------------------------
# Task → persona scope + data source mapping
# ---------------------------------------------------------------------------
TASK_CONFIG = {
    "qra-assessor": {
        "scope": "brandon_bailey",
        "db": "memory",
        "collection": "sparta_qra",
        "mode": "validate",
        "system": _load_prompt("shadow_qra_assessor_v5"),
        "prompt_template": "Question: {question}\nAnswer: {answer}",
        "fields": ["question", "answer"],
        "sample_query": "FOR d IN sparta_qra SORT RAND() LIMIT @n RETURN {question: d.question, answer: d.answer, citations: d.citations, control_id: d.control_id}",
        "t0_grounding": True,
    },
    "bridge-tagger": {
        "scope": "brandon_bailey",
        "db": "memory",
        "collection": "datalake_chunks",
        "mode": "classify",
        "system": _load_prompt("shadow_bridge_tagger"),
        "prompt_template": "Text: {text}",
        "text_field": "text",
        "sample_query": "FOR d IN datalake_chunks FILTER d.text != null AND LENGTH(d.text) > 50 SORT RAND() LIMIT @n RETURN d.text",
    },
    "edge-relevance-scorer": {
        "scope": "brandon_bailey",
        "db": "memory",
        "collection": "lesson_edges",
        "mode": "validate",
        "system": _load_prompt("shadow_edge_relevance_scorer"),
        "prompt_template": "Edge from: {_from}\nEdge to: {_to}\nRelationship type: {type}\nWeight: {weight}",
        "fields": ["_from", "_to", "type", "weight"],
        "sample_query": "FOR d IN lesson_edges SORT RAND() LIMIT @n RETURN {_from: d._from, _to: d._to, type: d.type, weight: d.weight}",
    },
    "extraction-quality-assessor": {
        "scope": "margaret_chen",
        "db": "memory",
        "collection": "datalake_docs",
        "mode": "validate",
        "system": _load_prompt("shadow_extraction_quality_assessor"),
        "prompt_template": "Asset type: {asset_type}\nExtracted text: {text}",
        "fields": ["text", "asset_type"],
        "sample_query": "FOR d IN datalake_docs FILTER d.text != null SORT RAND() LIMIT @n RETURN {text: SUBSTRING(d.text, 0, 500), asset_type: d.asset_type || 'document'}",
    },
    "sparta-pipeline-validator": {
        "scope": "brandon_bailey",
        "db": "memory",
        "collection": "sparta_qra",
        "mode": "validate",
        "system": _load_prompt("shadow_sparta_pipeline_validator"),
        "prompt_template": "Item type: {item_type}\nContent: {content}",
        "fields": ["item_type", "content"],
        "sample_query": "FOR d IN sparta_qra SORT RAND() LIMIT @n RETURN {item_type: 'qra', content: CONCAT(d.question, '\\n', d.answer)}",
    },
    "sparta-ambiguity": {
        "scope": "brandon_bailey",
        "db": "memory",
        "collection": "sparta_qra",
        "mode": "classify",
        "system": _load_prompt("shadow_sparta_ambiguity"),
        "prompt_template": "Query: {question}",
        "fields": ["question"],
        "sample_query": "FOR d IN sparta_qra FILTER d.question != null SORT RAND() LIMIT @n RETURN d.question",
    },
    "sparta-intent": {
        "scope": "brandon_bailey",
        "db": "memory",
        "collection": "sparta_qra",
        "mode": "classify",
        "system": _load_prompt("shadow_sparta_intent"),
        "prompt_template": "Query: {question}",
        "fields": ["question"],
        "sample_query": "FOR d IN sparta_qra FILTER d.question != null SORT RAND() LIMIT @n RETURN d.question",
    },
    "page-anticipation": {
        "scope": "embry",
        "db": "memory",
        "collection": "agent_conversations",
        "mode": "classify",
        "system": _load_prompt("shadow_page_anticipation"),
        "prompt_template": "Persona: {persona}\nMode: {mode}\nTopic: {topic}",
        "fields": ["persona", "mode", "topic"],
        "sample_query": (
            "FOR d IN agent_conversations "
            "FILTER d.persona != null AND d.mode != null "
            "SORT RAND() LIMIT @n "
            "RETURN {persona: d.persona, mode: d.mode, topic: d.topic || d.summary || 'general'}"
        ),
    },
    "table-strategy-selector": {
        "scope": "margaret_chen",
        "db": "memory",
        "collection": "datalake_chunks",
        "mode": "classify",
        "system": _load_prompt("shadow_table_strategy_selector"),
        "prompt_template": "Text chunk:\n{text}",
        "text_field": "text",
        "sample_query": (
            "FOR d IN datalake_chunks "
            "FILTER d.text != null AND LENGTH(d.text) > 100 "
            "AND (CONTAINS(LOWER(d.text), 'table') OR CONTAINS(d.text, '|') OR CONTAINS(d.text, '---')) "
            "SORT RAND() LIMIT @n RETURN d.text"
        ),
    },
}


# ---------------------------------------------------------------------------
# Memory-first sample fetcher (no direct ArangoDB access)
# ---------------------------------------------------------------------------
import subprocess

# Removed: memory accessed via httpx to Unix socket (see _memory_cmd)
def _get_arango_samples(db_name: str, query: str, n: int) -> List[Any]:
    """Pull random samples via /memory sample — fail loud, never fallback to direct DB.

    The query param is legacy (was raw AQL) — we extract the collection name from
    the task config and use /memory sample --random instead.
    """
    # Extract collection name from AQL query (e.g. "FOR d IN sparta_qra ..." → "sparta_qra")
    collection = ""
    for token in query.split():
        if token.upper() == "IN":
            idx = query.split().index(token)
            parts = query.split()
            if idx + 1 < len(parts):
                collection = parts[idx + 1]
                break

    if not collection:
        logger.error(f"Could not extract collection from query: {query}")
        return []

    # Extract fields from RETURN clause if present (e.g. "RETURN {question: d.question, ...}")
    fields = ""
    if "RETURN" in query.upper():
        return_part = query[query.upper().index("RETURN"):]
        # Extract field names from "{field: d.field, ...}" pattern
        import re
        field_matches = re.findall(r'(\w+):\s*d\.', return_part)
        if field_matches:
            fields = ",".join(field_matches)

    cmd = [MEMORY_RUN, "sample", "--collection", collection, "--limit", str(n), "--random"]
    if fields:
        cmd += ["--fields", fields]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode != 0:
            logger.error(f"Memory unavailable (rc={result.returncode}): {result.stderr}")
            raise RuntimeError(f"Cannot proceed without /memory (rc={result.returncode}): {result.stderr}")
        data = json.loads(result.stdout)
        return data.get("items", [])
    except RuntimeError:
        raise
    except Exception as e:
        logger.error(f"/memory sample failed: {e}")
        raise RuntimeError(f"Cannot proceed without /memory: {e}")


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------
def _build_prompt(cfg: Dict, item: Any) -> str:
    """Build user prompt from task config and data item."""
    tmpl = cfg["prompt_template"]
    if isinstance(item, dict):
        # Use config fields if available, fall back to item keys
        keys = cfg.get("fields", list(item.keys()))
        return tmpl.format(**{k: str(item.get(k, ""))[:500] for k in keys})
    else:
        return tmpl.format(text=str(item)[:1000])


def _input_hash(item: Any) -> str:
    """Stable hash of input for shadow dedup."""
    raw = json.dumps(item, sort_keys=True, ensure_ascii=False) if isinstance(item, dict) else str(item)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# T0 grounding check via /memory recall confidence
# ---------------------------------------------------------------------------
def _t0_grounding(item: Dict) -> Dict:
    """Compute T0 local grade via /recall confidence on citations.

    Calls the daemon via httpx Unix socket. Returns {grade, confidence, detail}.
    """
    import httpx as _httpx

    citations = item.get("citations") or []
    if not citations or not isinstance(citations, list):
        return {"grade": "PASS", "confidence": 0.5, "detail": "no_citations_to_check"}

    transport = _httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
    client = _httpx.Client(transport=transport, base_url="http://localhost", timeout=10)

    best_conf = 0.0
    for cite in citations:
        if not isinstance(cite, str) or len(cite) < 20:
            continue
        try:
            resp = client.post("/recall", json={
                "q": cite[:200],
                "k": 3,
                "collections": ["sparta_url_knowledge"],
            })
            conf = resp.json().get("confidence", 0)
            if conf > best_conf:
                best_conf = conf
        except Exception:
            pass

    client.close()
    grade = "PASS" if best_conf >= 70 else "FAIL"
    return {"grade": grade, "confidence": best_conf, "detail": f"bm25_best={best_conf:.1f}"}


# ---------------------------------------------------------------------------
# Shadow + metrics logging
# ---------------------------------------------------------------------------
def _log_shadow(
    task: str, scope: str, result: Dict, input_h: str,
    input_data: Any = None, local_result: Optional[Dict] = None,
) -> None:
    """Write shadow entry — teacher label with optional T0 local comparison."""
    grade = ""
    for key in ("grade", "prediction", "verdict", "assessment", "label",
                 "rating", "status", "answer", "output", "action", "stance"):
        val = result.get(key)
        if val and isinstance(val, str) and len(val.strip()) < 200:
            grade = val.strip()
            break

    local_grade = local_result.get("grade", "") if local_result else ""
    local_conf = local_result.get("confidence", 0.0) if local_result else 0.0
    has_local = bool(local_result and local_grade)

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task": task,
        "scope": scope,
        "entry_type": "shadow_comparison" if has_local else "teacher_label",
        "local_tier": 0 if has_local else -1,
        "local_source": "bm25_recall_confidence" if has_local else "",
        "local_grade": local_grade,
        "local_confidence": local_conf,
        "teacher_grade": grade,
        "teacher_confidence": result.get("confidence", 1.0),
        "agreed": (local_grade == grade) if has_local else False,
        "input_hash": input_h,
        "input_data": (
            input_data if isinstance(input_data, dict)
            else {"text": str(input_data)} if input_data
            else {}
        ),
        "teacher_result": result,
    }

    SHADOW_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SHADOW_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


def _log_metric(task: str, scope: str, latency_ms: float, ok: bool) -> None:
    """Write metric entry."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task": task,
        "scope": scope,
        "tier": 2,
        "source": "scillm",
        "confidence": 1.0 if ok else 0.0,
        "latency_ms": round(latency_ms, 2),
        "cached": False,
    }
    METRICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(METRICS_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# Batch priming via parallel_acompletions_iter (SCILLM paved path)
# ---------------------------------------------------------------------------
def _prime_task_batch(
    task_name: str,
    cfg: Dict,
    data: List[Any],
    concurrency: int = 6,
    timeout: int = 30,
) -> Dict[str, Any]:
    """Batch-prime a task via scillm proxy (httpx direct calls)."""
    import asyncio

    try:
        import httpx
    except ImportError:
        return {"status": "error", "reason": "httpx not installed"}

    PROXY_URL = os.environ.get("SCILLM_API_BASE", "http://localhost:4001") + "/v1/chat/completions"
    PROXY_KEY = os.environ.get("SCILLM_PROXY_KEY", "sk-dev-proxy-123")

    hashes = []
    requests_data = []
    for item in data:
        prompt = _build_prompt(cfg, item)
        requests_data.append({
            "model": "text",
            "messages": [
                {"role": "system", "content": cfg["system"]},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 256,
        })
        hashes.append(_input_hash(item))

    typer.echo(f"  Sending {len(data)} requests via scillm proxy (concurrency={concurrency})")

    ok_count = err_count = 0
    sem = asyncio.Semaphore(concurrency)

    async def _call(idx: int, payload: dict) -> Optional[str]:
        nonlocal ok_count, err_count
        async with sem:
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(
                        PROXY_URL,
                        json=payload,
                        headers={"Authorization": f"Bearer {PROXY_KEY}"},
                    )
                    if resp.status_code != 200:
                        err_count += 1
                        logger.debug(f"  [{idx}] HTTP {resp.status_code}")
                        return None
                    body = resp.json()
                    content = body["choices"][0]["message"]["content"]
                    ok_count += 1
                    return content
            except Exception as e:
                err_count += 1
                logger.debug(f"  [{idx}] error: {e}")
                return None

    async def _run_all():
        tasks = [_call(i, req) for i, req in enumerate(requests_data)]
        return await asyncio.gather(*tasks)

    results = asyncio.run(_run_all())

    for idx, content in enumerate(results):
        if content is None:
            continue
        try:
            parsed = json.loads(content) if isinstance(content, str) else content
        except (json.JSONDecodeError, TypeError):
            parsed = {"raw": str(content)}

        raw_item = data[idx] if idx < len(data) else {}
        item_dict = raw_item if isinstance(raw_item, dict) else {"text": str(raw_item)}
        h = hashes[idx] if idx < len(hashes) else _input_hash(raw_item)

        # T0 local grade via /recall confidence (for tasks with t0_grounding)
        local_result = None
        if cfg.get("t0_grounding") and isinstance(raw_item, dict):
            local_result = _t0_grounding(raw_item)

        _log_shadow(task_name, cfg["scope"], parsed, h, input_data=item_dict, local_result=local_result)
        _log_metric(task_name, cfg["scope"], 0.0, True)

        if ok_count % 20 == 0:
            typer.echo(f"  Progress: {ok_count + err_count}/{len(data)} (ok={ok_count}, err={err_count})")

    return {"status": "primed", "samples": len(data), "ok": ok_count, "errors": err_count}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
@app.command()
def prime(
    task: str = typer.Option("", "--task", "-t", help="Task to prime (or --all)"),
    all_tasks: bool = typer.Option(False, "--all", help="Prime all registered tasks"),
    samples: int = typer.Option(50, "--samples", "-n", help="Number of samples per task"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done"),
    concurrency: int = typer.Option(6, "--concurrency", "-c", help="Parallel requests"),
    timeout: int = typer.Option(30, "--timeout", help="Per-request timeout (s)"),
):
    """Prime shadow data by batching samples through /scillm."""
    tasks_to_prime = list(TASK_CONFIG.keys()) if all_tasks else ([task] if task else [])

    if not tasks_to_prime:
        typer.echo("Error: specify --task NAME or --all")
        raise typer.Exit(1)

    summary = {}
    for task_name in tasks_to_prime:
        cfg = TASK_CONFIG.get(task_name)
        if not cfg:
            logger.warning(f"No config for task {task_name}, skipping")
            continue

        typer.echo(f"\n=== Priming {task_name} ({cfg['scope']}) ===")
        typer.echo(f"  Source: {cfg['db']}.{cfg['collection']}")
        typer.echo(f"  Samples: {samples}")

        if dry_run:
            typer.echo("  [dry-run] Would query ArangoDB and batch through /scillm")
            summary[task_name] = {"status": "dry-run", "samples": samples}
            continue

        try:
            # Pull samples from ArangoDB
            data = _get_arango_samples(cfg["db"], cfg["sample_query"], samples)
            if not data:
                typer.echo(f"  No data returned from {cfg['db']}.{cfg['collection']}")
                summary[task_name] = {"status": "no-data", "samples": 0}
                continue

            typer.echo(f"  Got {len(data)} samples from ArangoDB")

            # Batch through /scillm
            result = _prime_task_batch(
                task_name, cfg, data,
                concurrency=concurrency,
                timeout=timeout,
            )
            summary[task_name] = result
            typer.echo(f"  Done: ok={result.get('ok', 0)}, errors={result.get('errors', 0)}")
        except Exception as e:
            logger.error(f"Task {task_name} failed: {e}")
            typer.echo(f"  FAILED: {e}")
            summary[task_name] = {"status": "error", "error": str(e)}

    typer.echo("\n=== Summary ===")
    typer.echo(json.dumps(summary, indent=2))


if __name__ == "__main__":
    app()
