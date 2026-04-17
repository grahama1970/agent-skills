"""Deterministic gate testing for QRA quality audit.

Runs 6 gates with zero LLM calls:
  1. On-topic (keyword heuristic)
  1b. Sentence decomposition (regex)
  2. /memory recall (daemon)
  2_entities. Entity extraction (deterministic)
  2b. Grounding (fabricated ID detection)
  3. Technique bridge (tag coherence + entity overlap)

Used by `test` and `test-batch` CLI commands in evidence_case.py.
"""

from __future__ import annotations

import json
import math
import time as _time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from loguru import logger
from rich.console import Console

console = Console()


def compute_test_verdict(gates: list[dict], latency_ms: float) -> dict:
    """Compute verdict from gates. Returns result dict."""
    gates_passed = sum(1 for g in gates if g.get("passed"))
    total_gates = len(gates)

    if gates_passed >= 6:
        verdict = "SATISFIED"
    elif gates_passed >= 2:
        verdict = "INCONCLUSIVE"
    else:
        verdict = "NOT_SATISFIED"

    return {
        "verdict": verdict,
        "gates_passed": gates_passed,
        "gates_total": total_gates,
        "gates": {g["gate"]: g["passed"] for g in gates},
        "gate_details": {g["gate"]: g["detail"] for g in gates},
        "latency_ms": latency_ms,
    }


def run_deterministic_gates(claim: str) -> dict:
    """Run 6 deterministic gates on a claim. Returns verdict dict.

    No LLM calls. No subprocess calls. Direct function calls only.
    """
    from collect import (
        collect_entities,
        collect_recall,
        decompose_sentence,
        group_by_technique,
        EntityExtractionFailure,
    )
    from strategies import auto_categorize

    t0 = _time.monotonic()
    gates: list[dict] = []

    # Gate 1: On-topic (keyword heuristic ONLY — no LLM fallback)
    category = auto_categorize(claim)
    on_topic = category != "general"
    gates.append({
        "gate": "step_1_topic",
        "passed": on_topic,
        "detail": f"category={category}" if on_topic else "no keyword match",
    })

    if not on_topic:
        return compute_test_verdict(gates, round((_time.monotonic() - t0) * 1000, 1))

    # Gate 1b: Sentence decomposition (regex heuristic)
    decomposition = decompose_sentence(claim)
    has_components = bool(
        decomposition.get("given_components") or decomposition.get("then_components")
    )
    gates.append({
        "gate": "step_1b_decompose",
        "passed": has_components,
        "detail": (
            f"given={len(decomposition.get('given_components', []))}, "
            f"then={len(decomposition.get('then_components', []))}"
        ),
    })

    # Gate 2: /memory recall
    try:
        qra_items = collect_recall(claim)
    except Exception as exc:
        qra_items = []
        logger.warning("recall failed: {}", exc)
    has_recall = len(qra_items) > 0
    gates.append({
        "gate": "step_2_recall",
        "passed": has_recall,
        "detail": f"{len(qra_items)} QRAs returned",
    })

    if not has_recall:
        return compute_test_verdict(gates, round((_time.monotonic() - t0) * 1000, 1))

    # Gate 2_entities: Entity extraction
    entities_failed = False
    try:
        entities = collect_entities(claim)
    except (EntityExtractionFailure, Exception) as exc:
        entities_failed = True
        entities = {
            "grounding_ok": True,
            "warnings": [],
            "resolution_map": {},
            "unresolved_terms": [],
            "all_control_ids": [],
            "related_pairs": [],
        }
        gates.append({
            "gate": "step_2_entities",
            "passed": False,
            "detail": f"extraction unavailable: {str(exc)[:100]}",
        })

    entity_warnings = entities.get("warnings", []) if isinstance(entities, dict) else []
    grounding_ok = entities.get("grounding_ok", True) if isinstance(entities, dict) else True
    n_fabricated = sum(1 for w in entity_warnings if w.get("category") == "fabricated_id")
    resolved_count = sum(
        1 for v in (entities.get("resolution_map", {}) if isinstance(entities, dict) else {}).values()
        if isinstance(v, dict) and v.get("exists")
    )
    if not entities_failed:
        gates.append({
            "gate": "step_2_entities",
            "passed": True,
            "detail": f"{resolved_count} resolved, {n_fabricated} fabricated",
        })

    # Gate 2b: Grounding (fabricated ID detection)
    grounding_gate_passed = grounding_ok and n_fabricated == 0
    gates.append({
        "gate": "step_2b_grounding",
        "passed": grounding_gate_passed,
        "detail": (
            f"grounding_ok={grounding_ok}, fabricated={n_fabricated}"
            if not grounding_gate_passed
            else f"{resolved_count} entities grounded"
        ),
    })

    # Gate 3: Technique bridge
    technique_groups = group_by_technique(qra_items)
    named_techniques = {k for k in technique_groups if k and k != "UNTAGGED"}

    all_tags = []
    for item in qra_items:
        tags = item.get("tactical_tags", [])
        if tags and isinstance(tags, list):
            all_tags.extend(t for t in tags if t)
    tag_counts: dict[str, int] = {}
    for t in all_tags:
        tag_counts[t] = tag_counts.get(t, 0) + 1
    dominant_tag = max(tag_counts, key=tag_counts.get) if tag_counts else ""
    dominant_count = tag_counts.get(dominant_tag, 0)
    coherence = dominant_count / len(qra_items) if qra_items else 0

    entity_ids = set(entities.get("all_control_ids", [])) if entities else set()
    recall_ids = sorted({item.get("control_id", "") for item in qra_items if item.get("control_id")})
    overlap = entity_ids & set(recall_ids) if entity_ids else set()
    related_pairs = (entities or {}).get("related_pairs", [])

    max_scatter = 5 if coherence >= 0.7 else 3
    has_tag_bridge = coherence >= 0.5 and len(named_techniques) <= max_scatter and len(named_techniques) > 0
    has_entity_bridge = (bool(overlap) or bool(related_pairs)) and len(named_techniques) > 0
    has_technique_bridge = has_tag_bridge or has_entity_bridge

    gates.append({
        "gate": "step_3_technique_bridge",
        "passed": has_technique_bridge,
        "detail": (
            f"dominant={dominant_tag} ({coherence:.0%}), "
            f"{len(named_techniques)} techniques, "
            f"{len(overlap)} entity overlap"
        ),
    })

    return compute_test_verdict(gates, round((_time.monotonic() - t0) * 1000, 1))


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score confidence interval."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
    return (max(0.0, center - spread), min(1.0, center + spread))


def load_qras_from_scope(scope: str, limit: int = 500) -> list[dict]:
    """Load QRAs via daemon /list endpoint with random offset.

    Uses /list for bulk retrieval — /recall is for relevance-ranked search,
    not random sampling.
    """
    import random

    from collect import _get_memory_http

    client = _get_memory_http()

    # Get total count
    resp = client.post("/list", json={"collection": scope, "limit": 1})
    if resp.status_code != 200:
        logger.error("/list failed: {} {}", resp.status_code, resp.text[:200])
        return []
    total = resp.json().get("total", 0)
    if total == 0:
        logger.warning("Collection {} is empty", scope)
        return []

    # Random offset for diversity
    max_offset = max(0, total - limit)
    offset = random.randint(0, max_offset) if max_offset > 0 else 0

    resp = client.post("/list", json={
        "collection": scope,
        "limit": limit,
        "offset": offset,
    })
    if resp.status_code != 200:
        logger.error("/list failed: {} {}", resp.status_code, resp.text[:200])
        return []

    docs = resp.json().get("documents", [])
    logger.info("Loaded {} QRAs via /list (offset={}, total={})", len(docs), offset, total)

    # Ensure QRA shape — need at least question + answer
    qras: list[dict] = []
    seen_keys: set[str] = set()
    for doc in docs:
        key = doc.get("_key", "")
        if key in seen_keys:
            continue
        if not doc.get("question") and not doc.get("problem"):
            continue
        seen_keys.add(key)
        qras.append(doc)
        if len(qras) >= limit:
            break

    return qras


def run_batch(
    qras: list[dict],
    output_file: str,
    workers: int = 5,
    processed_keys: set[str] | None = None,
) -> dict[str, Any]:
    """Run deterministic gates on a batch of QRAs. Returns summary dict."""
    if processed_keys:
        qras = [q for q in qras if q.get("_key", "") not in processed_keys]

    if not qras:
        return {"total": 0, "verdicts": {}, "skipped": "no QRAs to process"}

    t0 = _time.monotonic()
    verdicts = {"SATISFIED": 0, "INCONCLUSIVE": 0, "NOT_SATISFIED": 0, "ERROR": 0}
    results: list[dict] = []

    def _process_qra(qra: dict) -> dict:
        claim = qra.get("question", qra.get("problem", qra.get("title", "")))
        if not claim:
            return {"_key": qra.get("_key", ""), "verdict": "ERROR", "error": "no question field"}
        try:
            result = run_deterministic_gates(claim)
            result["_key"] = qra.get("_key", "")
            result["tactical_tags"] = qra.get("tactical_tags", [])
            result["control_ids"] = qra.get("control_ids", [])
            return result
        except Exception as exc:
            return {"_key": qra.get("_key", ""), "verdict": "ERROR", "error": str(exc)[:200]}

    completed = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_process_qra, q): q for q in qras}
        with open(output_file, "a") as f:
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                verdicts[result.get("verdict", "ERROR")] += 1
                f.write(json.dumps(result, default=str) + "\n")
                completed += 1
                if completed % 50 == 0 or completed == len(qras):
                    elapsed = _time.monotonic() - t0
                    rate = completed / elapsed if elapsed > 0 else 0
                    console.print(
                        f"[dim]{completed}/{len(qras)} "
                        f"({elapsed:.0f}s, {rate:.1f}/s) — "
                        f"S={verdicts['SATISFIED']} I={verdicts['INCONCLUSIVE']} "
                        f"N={verdicts['NOT_SATISFIED']} E={verdicts['ERROR']}[/]"
                    )

    total_s = _time.monotonic() - t0
    total = len(results)

    return {
        "total": total,
        "verdicts": verdicts,
        "rates": {k: round(v / total, 4) if total else 0 for k, v in verdicts.items()},
        "wilson_ci_95": {
            k: [round(lo, 4), round(hi, 4)] for k, (lo, hi)
            in {k: wilson_ci(v, total) for k, v in verdicts.items()}.items()
        },
        "total_seconds": round(total_s, 1),
        "mean_latency_ms": round(
            sum(r.get("latency_ms", 0) for r in results) / total if total else 0, 1
        ),
        "output_file": output_file,
    }
