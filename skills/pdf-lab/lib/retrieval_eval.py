"""Cross-modal retrieval quality evaluation against localhost:8601 memory daemon."""

from __future__ import annotations

import time
from math import log2
from statistics import mean

import httpx
from loguru import logger

from .metrics_models import RetrievalMetrics

_BASE = "http://localhost:8601"
_TIMEOUT = httpx.Timeout(30.0, connect=5.0)


def _dcg(relevance: list[int]) -> float:
    total = 0.0
    for idx, rel in enumerate(relevance, start=1):
        total += rel / log2(idx + 1)
    return total


def _ndcg_at_k(keys: list[str], relevant: set[str], k: int) -> float:
    gains = [1 if key in relevant else 0 for key in keys[:k]]
    ideal = [1] * min(len(relevant), k)
    denom = _dcg(ideal)
    if denom == 0:
        return 0.0
    return _dcg(gains) / denom


def _mrr_at_k(keys: list[str], relevant: set[str], k: int) -> float:
    for idx, key in enumerate(keys[:k], start=1):
        if key in relevant:
            return 1.0 / idx
    return 0.0


def evaluate_retrieval(
    judgements: list[dict],
    ks: tuple[int, ...] = (1, 5, 10),
) -> RetrievalMetrics:
    """Evaluate retrieval quality against memory daemon search endpoint."""
    max_k = max(ks)
    recall: dict[int, list[float]] = {k: [] for k in ks}
    ndcg: dict[int, list[float]] = {k: [] for k in ks}
    mrr: dict[int, list[float]] = {k: [] for k in ks}
    hit_rate: dict[int, list[float]] = {k: [] for k in ks}
    latencies: list[float] = []

    client = httpx.Client(timeout=_TIMEOUT)
    for j in judgements:
        query, relevant = j["query"], set(j["relevant_keys"])
        t0 = time.perf_counter()
        try:
            r = client.post(f"{_BASE}/search-collection", json={"collection": "sections", "q": query, "k": max_k})
            r.raise_for_status()
            hits = [h["_key"] for h in r.json().get("results", [])]
        except Exception as e:
            logger.warning("search failed for query {!r}: {}", query[:60], e)
            hits = []
        latencies.append((time.perf_counter() - t0) * 1000)

        for k in ks:
            top = hits[:k]
            hit_count = sum(1 for key in top if key in relevant)
            recall[k].append(hit_count / max(1, len(relevant)))
            ndcg[k].append(_ndcg_at_k(hits, relevant, k))
            mrr[k].append(_mrr_at_k(hits, relevant, k))
            hit_rate[k].append(1.0 if hit_count > 0 else 0.0)
    client.close()

    sorted_lat = sorted(latencies)
    p95_idx = int(round((len(sorted_lat) - 1) * 0.95)) if sorted_lat else 0
    return RetrievalMetrics(
        num_queries=len(judgements),
        recall_at_k={k: mean(v) if v else 0.0 for k, v in recall.items()},
        ndcg_at_k={k: mean(v) if v else 0.0 for k, v in ndcg.items()},
        mrr_at_k={k: mean(v) if v else 0.0 for k, v in mrr.items()},
        hit_rate_at_k={k: mean(v) if v else 0.0 for k, v in hit_rate.items()},
        mean_latency_ms=mean(latencies) if latencies else None,
        p95_latency_ms=sorted_lat[p95_idx] if sorted_lat else None,
    )


def build_auto_judgements(sample_size: int = 20) -> list[dict]:
    """Build self-retrieval judgements from existing sections with titles."""
    try:
        r = httpx.post(
            f"{_BASE}/list",
            json={"collection": "sections", "k": sample_size, "return_fields": ["_key", "title"]},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        docs = r.json().get("results", [])
    except Exception as e:
        logger.warning("build_auto_judgements failed: {}", e)
        return []
    return [
        {"query": d["title"], "relevant_keys": [d["_key"]]}
        for d in docs
        if d.get("title")
    ]
