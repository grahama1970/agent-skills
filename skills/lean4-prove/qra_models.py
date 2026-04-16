"""Data structures for QRA consistency verification.

Defines the core domain types used across the QRA verification pipeline:
ControlRelationship, ControlChain, VerificationResult, and reasoning-step
result types.  Also provides the memory subprocess helper and the ArangoDB
query functions that fetch control data via the /memory skill.
"""
from __future__ import annotations
import os

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
import httpx

# Removed: memory accessed via httpx to Unix socket (see _memory_cmd)
# ---------------------------------------------------------------------------
# Memory subprocess access (replaces direct ArangoDB)
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

class ControlParameter:
    """A typed parameter on a control for what-if analysis.

    param_type determines UI control and Lean4 type:
      - "bool": toggle (enabled/disabled, vulnerable/not)
      - "float": slider with bounds (coverage %, confidence score)
      - "enum": dropdown (NOMINAL/DEGRADED/CRITICAL)
    """
    name: str
    param_type: str  # "bool" | "float" | "enum"
    value: Any = None
    bounds: Optional[Tuple[float, float]] = None  # For float: (min, max)
    choices: Optional[List[str]] = None  # For enum: list of valid values
    description: str = ""


def normalize_method(method: str) -> str:
    """Normalize ArangoDB method field to Lean4-safe predicate name.

    "maps-to" -> "maps_to", "countered-by" -> "countered_by", etc.
    """
    return method.replace("-", "_").replace(" ", "_").lower()


@dataclass
class ControlRelationship:
    """A directed relationship between two SPARTA controls."""
    source_control_id: str
    target_control_id: str
    combined_score: float = 0.0
    method: str = ""

    @property
    def predicate(self) -> str:
        """Lean4-safe predicate name derived from method field."""
        return normalize_method(self.method) if self.method else "subsumes"


@dataclass
class ControlChain:
    """An ordered chain of controls connected by relationships."""
    controls: List[str]
    relationships: List[ControlRelationship] = field(default_factory=list)
    parameters: List[ControlParameter] = field(default_factory=list)

    @property
    def length(self) -> int:
        return len(self.controls)

    def __repr__(self) -> str:
        return " -> ".join(self.controls)


@dataclass
class VerificationResult:
    """Result of verifying a single chain."""
    chain: ControlChain
    status: str  # PROVEN | UNPROVEN | CONTRADICTION | ERROR
    lean_code: str = ""
    compiler_output: str = ""
    elapsed_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Reasoning verification data structures (Gate 6)
# ---------------------------------------------------------------------------

# Error taxonomy from LogicGraph (arXiv:2602.21044)
ERROR_TAXONOMY = [
    "semantic_misinterpretation",
    "information_omission",
    "fact_hallucination",
    "invalid_deduction",
    "insufficient_premise",
    "rule_misapplication",
]


@dataclass
class ReasoningStepResult:
    """Result of verifying a single reasoning step."""
    step_text: str
    lean4_code: str = ""
    compiled: bool = False
    error_type: Optional[str] = None
    error_detail: str = ""


@dataclass
class ReasoningVerifyResult:
    """Result of verifying all reasoning steps in a QRA."""
    qra_id: str
    steps_total: int = 0
    steps_verified: int = 0
    steps_failed: int = 0
    error_taxonomy: Dict[str, int] = field(default_factory=dict)
    step_results: List[ReasoningStepResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# ArangoDB queries via /memory
# ---------------------------------------------------------------------------

def fetch_control_relationships(
    scope: str = "sparta",
    limit: int = 100,
    min_score: float = 0.0,
) -> List[ControlRelationship]:
    """Fetch control relationships via /memory recall from sparta_relationships.

    Args:
        scope: Dataset scope (sparta, nist, etc.)
        limit: Max relationships to return
        min_score: Minimum combined_score threshold

    Returns:
        List of ControlRelationship objects
    """
    try:
        raw = _memory_cmd([
            "recall", "--q", f"scope:{scope} combined_score:>={min_score}",
            "--collections", "sparta_relationships",
        ], timeout=30)

        if not isinstance(raw, list):
            raw = raw.get("results", [])

        results = []
        for row in raw[:limit]:
            results.append(ControlRelationship(
                source_control_id=row.get("source_control_id", ""),
                target_control_id=row.get("target_control_id", ""),
                combined_score=row.get("combined_score", 0.0),
                method=row.get("method", ""),
            ))
        return results
    except (RuntimeError, json.JSONDecodeError) as e:
        logger.error(f"Failed to fetch relationships: {e}")
        return []


def fetch_parent_child_chains(
    limit: int = 20,
) -> List[ControlChain]:
    """Fetch hierarchical parent-child control chains via /memory recall.

    Uses parent_id field to build subsumption chains (parent subsumes child).
    """
    try:
        raw = _memory_cmd([
            "recall", "--q", "parent_id:*",
            "--collections", "sparta_controls",
        ], timeout=30)

        if not isinstance(raw, list):
            raw = raw.get("results", [])

        # Build a lookup of control_id -> control
        controls_by_id = {c.get("control_id", ""): c for c in raw if c.get("control_id")}

        chains = []
        for child in raw[:limit]:
            child_id = child.get("control_id", "")
            parent_id = child.get("parent_id", "")
            if not parent_id or parent_id not in controls_by_id:
                continue

            parent = controls_by_id[parent_id]
            cids = [child_id, parent_id]

            grandparent_id = parent.get("parent_id", "")
            if grandparent_id and grandparent_id in controls_by_id:
                cids.append(grandparent_id)

            # Reverse: grandparent -> parent -> child (subsumption direction)
            cids.reverse()
            chains.append(ControlChain(controls=cids))

        return chains
    except (RuntimeError, json.JSONDecodeError) as e:
        logger.error(f"Failed to fetch parent-child chains: {e}")
        return []


def fetch_relationship_chains(
    limit: int = 20,
) -> List[ControlChain]:
    """Build transitive chains from sparta_relationships via /memory recall.

    Finds A->B and B->C relationships to form A->B->C chains for
    transitivity verification.
    """
    try:
        raw = _memory_cmd([
            "recall", "--q", "source_control_id:*",
            "--collections", "sparta_relationships",
        ], timeout=30)

        if not isinstance(raw, list):
            raw = raw.get("results", [])

        # Build lookup: source -> list of relationships
        by_source: Dict[str, List[Dict]] = {}
        for r in raw:
            src = r.get("source_control_id", "")
            if src:
                by_source.setdefault(src, []).append(r)

        # Find A->B->C chains
        chains = []
        for r1 in raw:
            a = r1.get("source_control_id", "")
            b = r1.get("target_control_id", "")
            if not a or not b:
                continue

            for r2 in by_source.get(b, []):
                c = r2.get("target_control_id", "")
                if not c or c == a:
                    continue

                chain = ControlChain(
                    controls=[a, b, c],
                    relationships=[
                        ControlRelationship(
                            source_control_id=a,
                            target_control_id=b,
                            combined_score=r1.get("combined_score", 0.0),
                            method=r1.get("method", ""),
                        ),
                        ControlRelationship(
                            source_control_id=b,
                            target_control_id=c,
                            combined_score=r2.get("combined_score", 0.0),
                            method=r2.get("method", ""),
                        ),
                    ],
                )
                chains.append(chain)
                if len(chains) >= limit:
                    return chains

        return chains
    except (RuntimeError, json.JSONDecodeError) as e:
        logger.error(f"Failed to fetch relationship chains: {e}")
        return []
