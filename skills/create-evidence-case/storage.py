"""Persistence layer for evidence cases via embry-memory daemon.

All memory access goes through the embry-memory Unix socket daemon.
No subprocess calls, no raw AQL.

Inputs: Node dicts from models.py.
Outputs: Stored/retrieved evidence trees.
Failures: API errors logged, never raised (graceful degradation).
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

STORAGE_ROOT = Path("/mnt/storage12tb/skills/create-evidence-case")
UCT_CACHE = STORAGE_ROOT / "uct_cache"
AUDIT_LOG = STORAGE_ROOT / "audit_logs"

# Fallback if 12TB not mounted
if not STORAGE_ROOT.exists():
    STORAGE_ROOT = Path(__file__).parent / "state"
    UCT_CACHE = STORAGE_ROOT / "uct_cache"
    AUDIT_LOG = STORAGE_ROOT / "audit_logs"
    UCT_CACHE.mkdir(parents=True, exist_ok=True)
    AUDIT_LOG.mkdir(parents=True, exist_ok=True)

# embry-memory daemon Unix socket
_MEMORY_SOCKET = os.environ.get(
    "EMBRY_MEMORY_SOCKET",
    f"/run/user/{os.getuid()}/embry/memory.sock",
)

# Thread-local httpx clients for memory daemon (safe for ThreadPoolExecutor)
_thread_local = threading.local()


def _get_memory_http() -> httpx.Client:
    """Get per-thread httpx client for embry-memory Unix socket. Thread-safe."""
    client = getattr(_thread_local, "memory_http", None)
    if client is None:
        transport = httpx.HTTPTransport(uds=_MEMORY_SOCKET)
        client = httpx.Client(
            transport=transport,
            base_url="http://localhost",
            timeout=30.0,
        )
        _thread_local.memory_http = client
    return client


def _run_memory_learn(problem: str, solution: str, scope: str, tags: list[str]) -> dict[str, Any]:
    """Learn via embry-memory daemon (legacy — use _upsert_evidence_case for new cases)."""
    try:
        client = _get_memory_http()
        resp = client.post("/learn", json={
            "problem": problem,
            "solution": solution,
            "scope": scope,
            "tags": tags,
        })
        if resp.status_code == 200:
            data = resp.json()
            return {"meta": {"ok": data.get("stored", False)}}
        return {"meta": {"ok": False}, "error": f"learn returned {resp.status_code}"}
    except Exception as exc:
        logger.warning("memory learn via daemon failed: {}", exc)
        return {"meta": {"ok": False}, "error": str(exc)}


def _upsert_evidence_case(case: dict[str, Any]) -> bool:
    """Upsert an evidence case into the dedicated evidence_cases collection.

    _key is derived from control_ids + verdict to allow idempotent re-runs.
    Previous runs for the same control update in place.
    """
    import hashlib

    control_ids = case.get("control_ids", [])
    question = case.get("question", "")
    # Deterministic key: hash of control_ids + question prefix for dedup
    key_source = "|".join(sorted(control_ids)) + "|" + question[:200]
    _key = hashlib.sha256(key_source.encode()).hexdigest()[:16]

    doc = {
        "_key": _key,
        **case,
        "tags": [
            "sensai-cascade-label",
            "evidence-case",
            f"verdict:{case.get('verdict', 'unknown')}",
            case.get("category", ""),
        ],
    }

    try:
        client = _get_memory_http()
        resp = client.post("/upsert", json={
            "collection": "evidence_cases",
            "documents": [doc],
        })
        if resp.status_code == 200:
            data = resp.json()
            ok = data.get("inserted", 0) + data.get("updated", 0) > 0
            if ok:
                logger.debug("evidence case upserted: _key={}", _key)
            return ok
        logger.warning("evidence case upsert failed: HTTP {}", resp.status_code)
        return False
    except Exception as exc:
        logger.warning("evidence case upsert failed: {}", exc)
        return False


def _run_memory_recall(q: str, scope: str = "", tags: list[str] | None = None) -> dict[str, Any]:
    """Recall via embry-memory daemon."""
    try:
        client = _get_memory_http()
        payload: dict[str, Any] = {"q": q}
        if scope:
            payload["scope"] = scope
        if tags:
            payload["tags"] = tags
        resp = client.post("/recall", json=payload)
        if resp.status_code == 200:
            return resp.json()
        return {"results": [], "error": f"recall returned {resp.status_code}"}
    except Exception as exc:
        logger.warning("memory recall via daemon failed: {}", exc)
        return {"results": [], "error": str(exc)}


class EvidenceCaseStore:
    """CRUD for evidence case trees via /memory."""

    @staticmethod
    def learn_node(node: dict, scope: str = "evidence_cases") -> bool:
        """Store a single node via embry-memory daemon."""
        tags = ["evidence_case", node.get("node_type", "unknown")]
        if node.get("category"):
            tags.append(node["category"])

        node_json = json.dumps(node, default=str)
        node_type = node.get("node_type", "unknown")
        node_id = node.get("id", "?")

        if node_type == "claim":
            problem = f"Evidence case claim: {node.get('text', '')}"
        elif node_type == "strategy":
            problem = f"Evidence strategy: {node.get('name', '')} score={node.get('score', 0):.3f}"
        elif node_type == "evidence":
            problem = f"Evidence: {node.get('method', '')} via {node.get('layer', '')} confidence={node.get('confidence', 0):.2f}"
        elif node_type == "verdict":
            problem = f"Evidence verdict: {node.get('state', '')} grade={node.get('grade', '')} — {node.get('reasoning', '')[:200]}"
        else:
            problem = node_json

        resp = _run_memory_learn(problem=problem, solution=node_json, scope=scope, tags=tags)
        ok = resp.get("meta", {}).get("ok", False)
        if not ok:
            logger.warning("learn_node failed for {}: {}", node_id, resp.get("error"))
        return ok

    @staticmethod
    def learn_edge(from_id: str, to_id: str, relation: str, scope: str = "evidence_cases") -> bool:
        """Store an edge via embry-memory daemon."""
        edge_json = json.dumps({"from": from_id, "to": to_id, "relation": relation})
        summary = f"edge: {from_id} --[{relation}]--> {to_id}"
        resp = _run_memory_learn(
            problem=edge_json, solution=summary,
            scope=scope, tags=["evidence_edge", relation],
        )
        return resp.get("meta", {}).get("ok", False)

    @staticmethod
    def recall_strategies(category: str, scope: str = "evidence_cases") -> list[dict]:
        """Recall UCT history for a category."""
        query = f"evidence strategy node_type:strategy category:{category}"
        resp = _run_memory_recall(q=query, scope=scope, tags=["evidence_case", "strategy"])

        items = resp.get("results") or resp.get("items") or []
        if not items:
            return []

        strategies = []
        for item in items:
            # /memory recall returns items with problem/solution fields
            text = item.get("solution", item.get("problem", item.get("text", item.get("content", ""))))
            try:
                parsed = json.loads(text) if isinstance(text, str) else text
                if isinstance(parsed, dict) and parsed.get("node_type") == "strategy":
                    strategies.append(parsed)
            except (json.JSONDecodeError, TypeError):
                continue
        return strategies

    @staticmethod
    def recall_case(case_id: str, scope: str = "evidence_cases") -> dict | None:
        """Recall a full evidence case by claim ID."""
        resp = _run_memory_recall(
            q=f"evidence_case claim id:{case_id}",
            scope=scope,
            tags=["evidence_case", "claim"],
        )

        items = resp.get("results") or resp.get("items") or []
        for item in items:
            text = item.get("solution", item.get("problem", item.get("text", item.get("content", ""))))
            try:
                parsed = json.loads(text) if isinstance(text, str) else text
                if isinstance(parsed, dict) and parsed.get("id") == case_id:
                    return parsed
            except (json.JSONDecodeError, TypeError):
                continue
        return None

    @staticmethod
    def save_uct_cache(category: str, strategies: list[dict]) -> None:
        """Save UCT state to local disk cache for fast exploit lookups."""
        cache_file = UCT_CACHE / f"{category}.json"
        try:
            cache_file.write_text(json.dumps(strategies, indent=2, default=str))
        except OSError as exc:
            logger.warning("uct cache write failed: {}", exc)

    @staticmethod
    def load_uct_cache(category: str) -> list[dict]:
        """Load UCT state from local disk cache."""
        cache_file = UCT_CACHE / f"{category}.json"
        if not cache_file.exists():
            return []
        try:
            return json.loads(cache_file.read_text())
        except (json.JSONDecodeError, OSError):
            return []

    @staticmethod
    def learn_stress_result(result: dict, run_name: str = "") -> bool:
        """Store a stress test verdict in /memory for queryability.

        Enables:
          /memory recall "evidence case false positives"
          /memory recall "plausibility failures SPARTA"
          /memory recall "evidence case adversarial gate_failed"
        """
        qid = result.get("id", "?")
        verdict = result.get("actual", "unknown")
        expected = result.get("expected", "unknown")
        correct = result.get("correct", False)
        gate = result.get("gate_failed", "none")
        reason = result.get("reason", "")[:300]

        # Build problem as natural-language summary for BM25 recall
        status = "correct" if correct else "WRONG"
        problem = (
            f"Evidence case stress test [{qid}] {status}: "
            f"expected={expected} got={verdict}. "
            f"Gate: {gate}. {reason}"
        )
        solution = json.dumps(result, default=str)

        # Tags for filtered queries
        tags = [
            "evidence_case_stress",
            f"verdict_{verdict}",
            f"expected_{expected}",
        ]
        if not correct:
            tags.append("wrong_verdict")
            if expected == "satisfied" and verdict == "not_satisfied":
                tags.append("false_reject")
            elif expected == "not_satisfied" and verdict == "satisfied":
                tags.append("false_positive")
        if gate and gate != "none":
            tags.append(f"gate_{gate}")
        if run_name:
            tags.append(f"run_{run_name}")

        resp = _run_memory_learn(
            problem=problem, solution=solution,
            scope="evidence_cases", tags=tags,
        )
        return resp.get("meta", {}).get("ok", False)

    @staticmethod
    def learn_stress_summary(summary: dict, run_name: str = "") -> bool:
        """Store the aggregate summary of a stress test run."""
        problem = (
            f"Evidence case stress test run '{run_name}': "
            f"{summary.get('correct', 0)}/{summary.get('total', 0)} "
            f"({summary.get('accuracy', 0)}%) correct. "
            f"Real: {summary.get('real_accuracy', 0)}%, "
            f"Adversarial: {summary.get('adv_accuracy', 0)}%"
        )
        tags = ["evidence_case_stress", "run_summary"]
        if run_name:
            tags.append(f"run_{run_name}")

        resp = _run_memory_learn(
            problem=problem,
            solution=json.dumps(summary, default=str),
            scope="evidence_cases",
            tags=tags,
        )
        return resp.get("meta", {}).get("ok", False)

    @staticmethod
    def append_audit(case_id: str, entry: dict) -> None:
        """Append to audit log (append-only JSONL)."""
        log_file = AUDIT_LOG / f"{case_id}.jsonl"
        try:
            with log_file.open("a") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except OSError as exc:
            logger.warning("audit log write failed: {}", exc)
