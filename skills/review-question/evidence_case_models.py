"""Data structures, /memory helpers, and classification logic for the evidence case pipeline.

Contains dataclasses (GateResult, EntityInfo, RelationshipPath,
DatalakeConnection, EvidenceCase), /memory access helpers, the classification
decision tree, and shadow-lego logging used by evidence_case.py gates.
"""
from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from loguru import logger
import httpx

# Shadow-lego log path
SHADOW_LOG = Path(__file__).parent / "results" / "shadow.jsonl"


# Hub node threshold -- nodes with more than this many edges are skipped
# during relationship traversal to avoid meaningless "everything connects
# through REC-0001" paths.
HUB_THRESHOLD = 100

# Allowlist characters for entity IDs -- prevents AQL injection when
# interpolated into /memory count --filter expressions.  Entity IDs from
# /memory intent are LLM-generated and MUST be sanitized before reaching
# any filter.
_SAFE_ENTITY_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.")


def _sanitize_entity_id(eid: str) -> str:
    """Validate entity ID against allowlist, raise ValueError if unsafe."""
    if not eid or not all(c in _SAFE_ENTITY_CHARS for c in eid):
        raise ValueError(f"Unsafe entity ID rejected: {eid!r}")
    return eid


# ---------------------------------------------------------------------------
# /memory helpers (subprocess, never direct AQL)
# ---------------------------------------------------------------------------

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
            # Use /list endpoint instead of raw AQL (all AQL must be in memory project)
            list_resp = client.post("/list", json={"collection": coll, "limit": 1})
            list_resp.raise_for_status()
            return {"documents": [list_resp.json().get("total", 0)]}
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
                field_name = params.get("field", "tags")
                resp = client.post("/upsert", json={"collection": params.get("collection", "lessons"), "documents": [{"_key": params["key"], field_name: tags_list}]})
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

def _memory_count(collection: str, filter_expr: str = "") -> int:
    """Count docs in a collection via /memory count."""
    args = ["count", "--collection", collection]
    if filter_expr:
        args += ["--filter", filter_expr]
    data = _memory_cmd(args)
    if isinstance(data, dict):
        return data.get("count", 0)
    return int(data) if data else 0


def _memory_recall(query: str, scope: str = "", k: int = 10, **kwargs) -> list[dict]:
    """Semantic recall via /memory recall."""
    args = ["recall", "--q", query, "--k", str(k)]
    if scope:
        args += ["--scope", scope]
    collections = kwargs.get("collections")
    if collections:
        args += ["--collections", collections]
    data = _memory_cmd(args, timeout=30)
    if isinstance(data, list):
        return data
    return data.get("items", data.get("results", []))


def _memory_trace(query: str, mode: str = "fast", k: int = 10) -> dict:
    """Graph trace via /memory trace (returns provenance graph)."""
    args = ["trace", "--q", query, "--mode", mode, "--k", str(k)]
    return _memory_cmd(args, timeout=30)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class GateResult:
    """Result from a single evidence gate."""
    gate: int
    name: str
    passed: bool
    time_ms: float
    details: dict = field(default_factory=dict)

    @property
    def icon(self) -> str:
        return "Y" if self.passed else "N"


@dataclass
class EntityInfo:
    """Information about a single extracted entity after lookup."""
    entity_id: str
    exists: bool = False
    qra_count: int = 0
    avg_grounding: float = 0.0
    control_name: Optional[str] = None
    suggestions: list[str] = field(default_factory=list)


@dataclass
class RelationshipPath:
    """A path between two entities in the SPARTA relationship graph."""
    source: str
    target: str
    hops: int = 0
    via: list[str] = field(default_factory=list)
    found: bool = False


@dataclass
class DatalakeConnection:
    """Taxonomy overlap between a datalake category and SPARTA controls."""
    category: str
    recall_confidence: float = 0.0
    avg_graph_score: float = 0.0
    datalake_bridges: dict[str, float] = field(default_factory=dict)
    sparta_bridges: dict[str, float] = field(default_factory=dict)
    shared_bridges: dict[str, float] = field(default_factory=dict)
    connected_controls: list[str] = field(default_factory=list)
    item_count: int = 0


@dataclass
class EvidenceCase:
    """Complete evidence case for a question."""
    question: str
    classification: str = "PENDING"
    entities: list[EntityInfo] = field(default_factory=list)
    relationships: list[RelationshipPath] = field(default_factory=list)
    components: list[list[str]] = field(default_factory=list)
    f36_categories: list[str] = field(default_factory=list)
    datalake_connections: list[DatalakeConnection] = field(default_factory=list)
    sub_cases: list["EvidenceCase"] = field(default_factory=list)
    gates: list[GateResult] = field(default_factory=list)
    total_qras: int = 0
    avg_grounding: float = 0.0
    lean4_verifiable: bool = False
    query_spec: dict = field(default_factory=dict)
    markdown_report: Optional[str] = None
    total_time_ms: float = 0.0

    def to_markdown(self) -> str:
        """Render the evidence case as a markdown report."""
        from evidence_render import render_markdown
        return render_markdown(self)


# ---------------------------------------------------------------------------
# Classification decision tree
# ---------------------------------------------------------------------------

def classify(
    gate1: GateResult,
    gate2: GateResult,
    gate3: GateResult,
    gate4: GateResult,
    gate5: GateResult,
    components: list[list[str]],
    sub_cases: list[EvidenceCase],
    *,
    f36_categories: list[str] | None = None,
    datalake_gate: GateResult | None = None,
) -> str:
    """Apply the classification decision tree.

    No entities AND no F36 categories    -> NEEDS_CLARIFICATION
    F36 category detected, recall fails  -> DATALAKE_NOT_CONNECTED
    Any entity doesn't exist             -> INVALID_IDS
    F36 + SPARTA, graph_score > 0        -> taxonomy path exists, proceed
    Entities exist, multiple components  -> DECOMPOSE (check sub-cases)
    Entities exist, 1 component, 0 QRAs -> NO_COVERAGE
    Entities exist, 1 component, QRAs   -> ANSWERABLE
    """
    if not gate1.passed:
        return "NEEDS_CLARIFICATION"

    if f36_categories and datalake_gate and not datalake_gate.passed:
        gate1_f36 = gate1.details.get("f36_categories", [])
        if gate1_f36:
            return "DATALAKE_NOT_CONNECTED"

    if not gate2.passed:
        return "INVALID_IDS"

    if len(components) > 1:
        if sub_cases:
            all_answerable = all(
                sc.classification == "ANSWERABLE" for sc in sub_cases
            )
            if all_answerable:
                return "ANSWERABLE"
            return "PARTIALLY_ANSWERABLE"
        return "DECOMPOSE"

    if not gate5.passed:
        return "NO_COVERAGE"

    return "ANSWERABLE"


# ---------------------------------------------------------------------------
# Shadow-lego logging
# ---------------------------------------------------------------------------

def log_shadow(case: EvidenceCase) -> None:
    """Log evidence case to shadow.jsonl for classifier training data."""
    try:
        SHADOW_LOG.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": time.time(),
            "question": case.question,
            "classification": case.classification,
            "entities": [e.entity_id for e in case.entities],
            "f36_categories": case.f36_categories,
            "entity_count": len(case.entities),
            "valid_entities": sum(1 for e in case.entities if e.exists),
            "total_qras": case.total_qras,
            "avg_grounding": case.avg_grounding,
            "components": len(case.components),
            "datalake_connections": [
                {
                    "category": c.category,
                    "recall_confidence": round(c.recall_confidence, 3),
                    "avg_graph_score": round(c.avg_graph_score, 3),
                    "datalake_bridges": {
                        k: round(v, 3) for k, v in c.datalake_bridges.items()
                    },
                    "sparta_bridges": {
                        k: round(v, 3) for k, v in c.sparta_bridges.items()
                    },
                    "shared_bridges": {
                        k: round(v, 3) for k, v in c.shared_bridges.items()
                    },
                    "connected_controls": len(c.connected_controls),
                }
                for c in case.datalake_connections
            ],
            "gates": [
                {
                    "gate": g.gate,
                    "name": g.name,
                    "passed": g.passed,
                    "time_ms": g.time_ms,
                }
                for g in case.gates
            ],
            "total_time_ms": case.total_time_ms,
        }
        with open(SHADOW_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except (OSError, TypeError, ValueError) as exc:
        logger.debug(f"Shadow logging failed: {exc}")
