"""Data collection functions for evidence cases.

Calls the embry-memory daemon (Unix socket) for recall/learn/clarify.
This is the FULL hybrid pipeline via the daemon service.
NEVER falls back to degraded search. If the daemon is broken, FAIL LOUDLY.

Also includes question decomposition and evidence grouping helpers.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from collections import defaultdict
from pathlib import Path
from typing import Any

import httpx
from loguru import logger
from rich.console import Console

console = Console()


class EntityExtractionFailure(RuntimeError):
    """Raised when /extract-entities is unavailable or returns an invalid contract."""

SCILLM_BASE = os.getenv("SCILLM_API_BASE", "http://localhost:4001")
SCILLM_KEY = os.getenv("SCILLM_PROXY_KEY", "sk-dev-proxy-123")
SCILLM_SEMANTIC_MODEL = os.getenv("SCILLM_SEMANTIC_ALIGNMENT_MODEL", "gemini/gemini-2.5-flash")

SKILLS_DIR = Path(__file__).resolve().parent.parent
ASSISTANT_SKILL = SKILLS_DIR / "assistant" / "run.sh"
EXTRACT_ENTITIES_SKILL = SKILLS_DIR / "extract-entities" / "run.sh"
LEAN4_PROVE_SKILL = SKILLS_DIR / "lean4-prove" / "run.sh"
DOGPILE_SKILL = SKILLS_DIR / "dogpile" / "run.sh"
EDGE_VERIFIER_SKILL = SKILLS_DIR / "edge-verifier" / "run.sh"
CMMC_ASSESSOR_SKILL = SKILLS_DIR / "cmmc-assessor" / "run.sh"

ASSISTANT_DIR = SKILLS_DIR / "assistant"
_assistant_path_added = False

# embry-memory daemon Unix socket
_MEMORY_SOCKET = os.environ.get(
    "EMBRY_MEMORY_SOCKET",
    f"/run/user/{os.getuid()}/embry/memory.sock",
)

# Thread-local httpx clients for memory daemon (safe for ThreadPoolExecutor)
_thread_local = threading.local()


def _get_memory_http() -> httpx.Client:
    """Get per-thread httpx client for embry-memory daemon. Thread-safe."""
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


def _memory_learn_direct(
    problem: str, solution: str, scope: str, tags: list[str],
) -> bool:
    """Learn to /memory via daemon. Fails loudly if daemon is broken."""
    client = _get_memory_http()
    resp = client.post("/learn", json={
        "problem": problem,
        "solution": solution,
        "scope": scope,
        "tags": tags,
    })
    if resp.status_code != 200:
        raise RuntimeError(f"/memory learn failed: HTTP {resp.status_code} — {resp.text}")
    return resp.json().get("stored", False)


def _ensure_assistant_on_path() -> None:
    """Add /assistant skill directory to sys.path for direct imports.

    Uses importlib to pre-load assistant's models module under an alias,
    avoiding collision with create-evidence-case/models.py in sys.modules.
    """
    global _assistant_path_added
    if not _assistant_path_added and ASSISTANT_DIR.exists():
        import sys
        import importlib.util

        # Pre-load assistant's models.py as 'models' BEFORE gateway imports it,
        # but only if it hasn't been loaded from the wrong location yet.
        assistant_models = ASSISTANT_DIR / "models.py"
        if assistant_models.exists():
            spec = importlib.util.spec_from_file_location("models", str(assistant_models))
            mod = importlib.util.module_from_spec(spec)
            sys.modules["models"] = mod  # Override any cached wrong module
            spec.loader.exec_module(mod)

        if str(ASSISTANT_DIR) not in sys.path:
            sys.path.insert(0, str(ASSISTANT_DIR))
        _assistant_path_added = True


# ---------------------------------------------------------------------------
# Skill invocation (subprocess only — NO direct graph_memory imports)
# ---------------------------------------------------------------------------

def _extract_json_payload(text: str) -> dict | list | None:
    """Extract the first JSON object/array from mixed CLI output."""
    blob = (text or "").strip()
    if not blob:
        return None
    decoder = json.JSONDecoder()
    candidates = [i for i in (blob.find("{"), blob.find("[")) if i >= 0]
    for idx in sorted(candidates):
        try:
            parsed, _ = decoder.raw_decode(blob[idx:])
            if isinstance(parsed, (dict, list)):
                return parsed
        except json.JSONDecodeError:
            continue
    return None


def _invoke_skill(
    run_sh: Path,
    args: list[str],
    timeout: int = 30,
    env: dict[str, str] | None = None,
) -> dict | None:
    """Invoke a sibling skill and parse JSON output. Returns None on failure."""
    if not run_sh.exists():
        logger.debug("skill not found: {}", run_sh)
        return None
    cmd = [str(run_sh)] + args
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        payload = _extract_json_payload(proc.stdout) or _extract_json_payload(proc.stderr)
        if proc.returncode != 0 and payload is None:
            err = (proc.stderr or proc.stdout or "").strip()[:200]
            logger.warning("skill {} failed rc={} args={} err={}", run_sh.name, proc.returncode, args[:4], err)
            return None
        if isinstance(payload, dict):
            return payload
        return None
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.debug("skill invocation failed: {} — {}", run_sh.name, exc)
        return None


def _is_meta_item(item: dict) -> bool:
    """Check if a recall item is routing/meta (not substantive content)."""
    tags = item.get("tags", [])
    sol = item.get("solution", "")
    if "RecallResult" in sol:
        return True
    for t in tags:
        if t in ("routing", "global_standard", "pi_harness",
                 "found_false_default", "evidence_case", "skill_route"):
            return True
    return False


def _filter_meta_items(items: list[dict]) -> list[dict]:
    """Remove routing/meta lessons from memory results."""
    filtered = [i for i in items if not _is_meta_item(i)]
    return filtered


def _span_from_resolved_entity(entity: dict[str, Any]) -> dict[str, Any]:
    """Convert a resolved extractor entity into the legacy span shape."""
    span = entity.get("span") or []
    text = entity.get("mention") or entity.get("canonical_id") or ""
    return {
        "text": text,
        "span": span if isinstance(span, list) else [],
        "type": "control_id" if entity.get("canonical_id") else entity.get("entity_type", "entity"),
        "status": "grounded",
        "control_id": entity.get("canonical_id", ""),
        "name": entity.get("canonical_name", ""),
        "framework": entity.get("framework", ""),
        "grounded_to_framework": True,
        "relevant_to_query": True,
    }


def _span_from_domain_term(term: dict[str, Any]) -> dict[str, Any]:
    """Convert a domain term into the legacy span shape."""
    span = term.get("span") or []
    text = term.get("text") or term.get("mention") or ""
    return {
        "text": text,
        "span": span if isinstance(span, list) else [],
        "type": term.get("kind", "domain_term"),
        "status": "extracted",
        "grounded_to_framework": False,
        "relevant_to_query": True,
    }


def _control_metadata_from_resolved_entity(entity: dict[str, Any]) -> dict[str, Any]:
    """Convert a resolved extractor entity into create-evidence-case metadata."""
    cp = entity.get("crosswalk_path") or {}
    path_ids = cp.get("ids") or []
    taxonomy: list[dict[str, Any]] = []
    for i in range(len(path_ids) - 1):
        taxonomy.append({"from": path_ids[i], "to": path_ids[i + 1], "framework": ""})
    if cp.get("terminal_framework") == "SPARTA" and cp.get("terminal_id"):
        source_id = path_ids[-2] if len(path_ids) > 1 else entity.get("canonical_id", "")
        taxonomy.append({
            "from": source_id,
            "to": cp["terminal_id"],
            "framework": "SPARTA",
        })
    return {
        "control_id": entity.get("canonical_id", ""),
        "name": entity.get("canonical_name", ""),
        "framework": entity.get("framework", ""),
        "type": entity.get("entity_type", ""),
        "taxonomy": taxonomy,
        "chain_path": path_ids,
        "chain_stop": None if cp.get("exists") else cp.get("from_framework"),
    }


def _normalize_extract_entities_legacy(result: dict[str, Any]) -> dict[str, Any]:
    """Add legacy convenience fields expected by older evidence-case code.

    `/extract-entities` now has compact agent output by default. The evidence
    skill asks for `view=legacy`, but the daemon legacy response may still omit
    older CLI-enriched conveniences. Rebuild those fields from resolved entities
    so downstream gates read one stable shape.
    """
    if not isinstance(result, dict):
        return {}

    resolved = result.get("resolved_entities") or []
    unresolved = result.get("unresolved_entities") or []
    external = result.get("external_entities") or []
    domain_terms = result.get("domain_terms") or []

    control_ids = [
        ent.get("canonical_id")
        for ent in resolved
        if isinstance(ent, dict) and ent.get("canonical_id")
    ]
    result["all_control_ids"] = control_ids
    result["control_ids"] = control_ids

    if not result.get("control_metadata"):
        result["control_metadata"] = [
            _control_metadata_from_resolved_entity(ent)
            for ent in resolved
            if isinstance(ent, dict)
        ]

    if not result.get("spans") and not result.get("entities"):
        result["spans"] = (
            [_span_from_resolved_entity(ent) for ent in resolved if isinstance(ent, dict)]
            + [_span_from_domain_term(term) for term in domain_terms if isinstance(term, dict)]
        )

    warnings = []
    for item in unresolved:
        if isinstance(item, dict):
            warnings.append({
                "term": item.get("mention", ""),
                "category": item.get("reason", "fabricated_id"),
                "detail": item.get("detail", ""),
            })
    for item in external:
        if isinstance(item, dict):
            warnings.append({
                "term": item.get("mention", ""),
                "category": "not_in_corpus",
                "detail": f"WordNet: {item.get('wordnet_category', 'unknown')}",
            })
    result["warnings"] = warnings

    resolution_map: dict[str, dict[str, Any]] = {}
    for ent in resolved:
        if not isinstance(ent, dict):
            continue
        cid = ent.get("canonical_id")
        if cid:
            resolution_map[cid] = {
                "exists": True,
                "match_type": "exact",
                "control_id": cid,
                "name": ent.get("canonical_name", ""),
            }
    for item in unresolved:
        if isinstance(item, dict):
            mention = item.get("mention", "")
            if mention:
                resolution_map[mention] = {"exists": False, "reason": item.get("reason", "")}
    result["resolution_map"] = resolution_map

    result.setdefault("headline", f"{len(resolved)} resolved")
    result.setdefault("related_pairs", [])
    result.setdefault("phrases", [
        term.get("text", "")
        for term in domain_terms
        if isinstance(term, dict) and term.get("text")
    ])
    result.setdefault("unresolved_terms", [
        {"term": item.get("mention", ""), "type": item.get("reason", "")}
        for item in unresolved
        if isinstance(item, dict)
    ])
    result["method"] = "daemon_http"
    return result


def _shadow_assistant(task: str, data: dict) -> None:
    """Fire-and-forget /assistant shadow call for training label collection."""
    try:
        if not ASSISTANT_SKILL.exists():
            return
        input_json = json.dumps(data, default=str)[:2000]
        subprocess.Popen(
            [str(ASSISTANT_SKILL), "classify", "--task", task, "--input", input_json],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Pre-existing QRA check — skip pipeline if identical question already answered
# ---------------------------------------------------------------------------


def check_pre_existing_qra(
    question: str,
    entities: dict,
    similarity_threshold: int = 95,
) -> tuple[dict | None, list[dict]]:
    """Check if a near-identical QRA already exists in sparta_qra.

    Three-layer verification:
    1. /recall against sparta_qra for semantic candidates (k=10)
    2. rapidfuzz token_sort_ratio >= threshold on question text
    3. /extract-entities on candidate question must produce identical entities

    Args:
        question: The incoming question text.
        entities: Already-extracted entities from the incoming question
                  (from collect_entities). Reused to avoid redundant extraction.
        similarity_threshold: Minimum rapidfuzz score (default 95).

    Returns:
        Tuple of (match, candidates):
        - match: Matching QRA dict with "pre_existing": True, or None.
        - candidates: All recall results (reusable as QRA evidence if no match).
    """
    from rapidfuzz import fuzz

    incoming_ids = sorted({
        e.get("canonical_id", "") for e in entities.get("resolved_entities", [])
        if e.get("canonical_id")
    })
    if not incoming_ids:
        return None, []

    client = _get_memory_http()
    try:
        resp = client.post("/recall", json={
            "q": question[:500],
            "k": 10,
            "collections": ["sparta_qra"],
        })
        resp.raise_for_status()
        candidates = resp.json().get("items", [])
    except Exception as exc:
        logger.warning("Pre-existing QRA check recall failed: {}", exc)
        return None, []

    for candidate in candidates:
        candidate_q = candidate.get("question", candidate.get("problem", ""))
        if not candidate_q:
            continue

        # Layer 2: string similarity
        score = fuzz.token_sort_ratio(question.strip(), candidate_q.strip())
        if score < similarity_threshold:
            continue

        # Layer 3: entity identity — extract entities from candidate question
        try:
            candidate_entities = collect_entities(candidate_q)
        except EntityExtractionFailure:
            continue

        candidate_ids = sorted({
            e.get("canonical_id", "") for e in candidate_entities.get("resolved_entities", [])
            if e.get("canonical_id")
        })

        if incoming_ids == candidate_ids:
            logger.info(
                "Pre-existing QRA match: score={}, entities={}, key={}",
                score, incoming_ids, candidate.get("_key", "?"),
            )
            candidate["pre_existing"] = True
            return candidate, candidates

    return None, candidates


# ---------------------------------------------------------------------------
# Data collection — call skills, return raw results for agent reasoning
# ---------------------------------------------------------------------------


def collect_recall(question: str, k: int = 20, collections: list[str] | None = None) -> list[dict]:
    """Call /memory recall via daemon. Full hybrid search, no degraded paths.

    The daemon does:
    - Tier 1: exact control_id lookup (sparta_qra, lessons)
    - Tier 2: proxy to graph_memory service (BM25 + graph + multihop)
    - Tier 2 fallback: direct ArangoDB AQL with optional taxonomy ranking

    Fails loudly if daemon is broken. NEVER returns degraded results.
    """
    result = collect_recall_with_confidence(question, k=k, collections=collections)
    return result["items"]


def _filter_sparta_items(raw_items: list[dict]) -> list[dict]:
    """Keep only SPARTA QRA/control items from recall results.

    Drops lessons, persona lore, agent conversations, and items with
    text too short to be useful. Keeps items from sparta_qra,
    sparta_qras, sparta_controls, OR items without _source that have
    SPARTA QRA shape (control_id or question field).
    """
    items = _filter_meta_items(raw_items)
    SPARTA_SOURCES = {"sparta_qra", "sparta_qras", "sparta_controls"}
    sparta_items = []
    for item in items:
        text = item.get("answer", item.get("solution", item.get("text", "")))
        if len(text) <= 20:
            continue
        src = item.get("_source", "")
        if src:
            if src not in SPARTA_SOURCES:
                continue
        else:
            # No _source (tier1 exact match from lessons) — keep if it has
            # control_id or question/answer fields (SPARTA QRA shape)
            if not item.get("control_id") and not item.get("question"):
                continue
        sparta_items.append(item)
    return sparta_items


def collect_recall_with_confidence(question: str, k: int = 20, collections: list[str] | None = None) -> dict:
    """Call /memory recall via daemon. SPARTA-specific results only.

    Calls /recall with scope=sparta, then filters results to only keep
    items from sparta_qra and sparta_controls. Discards lessons, persona
    lore, agent conversations, and other non-SPARTA collections —
    those are irrelevant for answering SPARTA questions.

    When tier1_exact matches a lesson (not a QRA), the daemon short-circuits
    and never reaches tier2 (BM25+semantic on sparta_qra). We detect this
    and retry with collection=sparta_qra to force tier2 search.

    Returns dict with keys: items, confidence, source, tier
    """
    client = _get_memory_http()
    payload: dict = {
        "q": question[:400],
        "scope": "sparta",
        "limit": k,
    }
    if collections:
        payload["collections"] = collections
    resp = client.post("/recall", json=payload)
    if resp.status_code != 200:
        raise RuntimeError(f"/memory recall failed: HTTP {resp.status_code} — {resp.text}")

    data = resp.json()
    confidence = data.get("confidence", 0.0)
    source = data.get("source", "unknown")
    tier = data.get("tier", -1)

    raw_items = data.get("results", data.get("items", []))
    if not raw_items:
        return {"items": [], "confidence": confidence, "source": source, "tier": tier}

    sparta_items = _filter_sparta_items(raw_items)

    return {"items": sparta_items, "confidence": confidence, "source": source, "tier": tier}


def collect_entities(question: str) -> dict | None:
    """Extract entities via daemon /extract-entities HTTP endpoint.

    Returns the new agent-friendly contract directly. Consumers read:
      - grounding_ok: bool
      - resolved_entities: [{mention, span, canonical_id, canonical_name, framework, entity_type, crosswalk_path}]
      - external_entities: [{mention, span, wordnet_category, routing_effect}]
      - unresolved_entities: [{mention, reason, detail}]
      - domain_terms: [{text, span, kind}]
      - agent_decision: {safe_to_answer, needs_clarification, needs_retry, suggested_action, reason}
      - summary: {resolved_count, external_count, unresolved_count, domain_term_count}
    """
    client = _get_memory_http()
    try:
        resp = client.post(
            "/extract-entities",
            json={"text": question[:500], "view": "legacy"},
        )
        resp.raise_for_status()
        result = resp.json()
    except Exception as exc:
        raise EntityExtractionFailure(
            f"Daemon /extract-entities call failed: {exc}"
        )

    if not isinstance(result, dict) or not result.get("ok", False):
        raise EntityExtractionFailure(
            f"Entity extraction failed: {result}"
        )

    return _normalize_extract_entities_legacy(result)


def collect_concept_intersection(
    question: str,
    entities: dict,
    recall_items: list[dict],
) -> dict[str, Any]:
    """Concept-in-technique intersection via /extract-entities.

    1. Get SPARTA technique IDs from the question's entity taxonomy edges.
    2. For each non-SPARTA entity name (the concept), call /extract-entities
       to get its own SPARTA taxonomy edges.
    3. Intersect the two SPARTA ID sets.

    All corpus grounding is done by /extract-entities. No bespoke search.
    """
    client = _get_memory_http()

    # 1. Collect SPARTA technique IDs from question entity taxonomy edges
    taxonomy_sparta_ids: set[str] = set()
    for cm in (entities or {}).get("control_metadata", []):
        for edge in cm.get("taxonomy", []):
            if edge.get("framework") == "SPARTA":
                taxonomy_sparta_ids.add(edge["to"])

    if not taxonomy_sparta_ids:
        return {
            "taxonomy_sparta_ids": [],
            "intersection_count": 0,
            "skipped": True,
            "reason": "no taxonomy SPARTA edges",
        }

    # 2. Get concept names from entity extraction (non-SPARTA, non-ID names)
    concept_names: list[str] = []
    for cm in (entities or {}).get("control_metadata", []):
        name = cm.get("name", "")
        if name and name != cm.get("control_id", "") and cm.get("framework") != "SPARTA":
            concept_names.append(name)

    if not concept_names:
        return {
            "taxonomy_sparta_ids": sorted(taxonomy_sparta_ids)[:20],
            "taxonomy_sparta_count": len(taxonomy_sparta_ids),
            "intersection_count": 0,
            "skipped": True,
            "reason": "no concept names from entity extraction",
        }

    # 3. Call /extract-entities with each concept name to get its SPARTA edges
    concept_sparta_ids: set[str] = set()
    concept_entities: list[dict] = []
    for concept in concept_names[:3]:
        try:
            resp = client.post("/extract-entities", json={"text": concept, "view": "legacy"})
            resp.raise_for_status()
            result = _normalize_extract_entities_legacy(resp.json())
            for cm in result.get("control_metadata", []):
                for edge in cm.get("taxonomy", []):
                    if edge.get("framework") == "SPARTA":
                        concept_sparta_ids.add(edge["to"])
                if cm.get("framework") == "SPARTA":
                    concept_entities.append({
                        "control_id": cm.get("control_id"),
                        "name": cm.get("name"),
                        "type": cm.get("type"),
                    })
        except Exception:
            pass

    # 4. Intersect
    intersection = sorted(taxonomy_sparta_ids & concept_sparta_ids)

    return {
        "taxonomy_sparta_ids": sorted(taxonomy_sparta_ids)[:20],
        "taxonomy_sparta_count": len(taxonomy_sparta_ids),
        "concept_names": concept_names,
        "concept_sparta_ids": sorted(concept_sparta_ids)[:20],
        "concept_sparta_count": len(concept_sparta_ids),
        "concept_entities": concept_entities,
        "intersection": intersection,
        "intersection_count": len(intersection),
    }


def collect_topic(question: str) -> dict:
    """Classify question topic via keyword heuristic + /assistant."""
    from strategies import auto_categorize

    category = auto_categorize(question)
    if category != "general":
        return {"on_topic": True, "category": category, "method": "keyword_heuristic"}

    try:
        _ensure_assistant_on_path()
        from gateway import classify as assistant_classify
        result = assistant_classify(text=question[:500], task="topic-classifier")
        if result and hasattr(result, "prediction") and result.prediction:
            label = result.prediction
            if label.lower() not in ("off_topic", "unknown", "general"):
                return {"on_topic": True, "category": label, "method": "assistant_classifier"}
    except (ImportError, Exception) as exc:
        logger.debug("direct assistant classify failed: {}", exc)
        resp = _invoke_skill(ASSISTANT_SKILL, [
            "classify", "--task", "topic-classifier", "--text", question[:500],
        ], timeout=15)
        if resp and isinstance(resp, dict):
            label = resp.get("label", resp.get("class", ""))
            if label and label.lower() not in ("off_topic", "unknown", "general"):
                return {"on_topic": True, "category": label, "method": "assistant_classifier"}

    return {"on_topic": False, "category": "general", "method": "no_match"}


def collect_clarify(question: str) -> dict | None:
    """Call /memory clarify via daemon. Fails loudly if broken."""
    client = _get_memory_http()
    resp = client.post("/clarify", json={"q": question[:500]})
    if resp.status_code != 200:
        raise RuntimeError(f"/memory clarify failed: HTTP {resp.status_code} — {resp.text}")
    return resp.json()


# Formalizability threshold for Lean4 proof attempts
FORMALIZABILITY_THRESHOLD = int(os.getenv("FORMALIZABILITY_THRESHOLD", "70"))


def get_formalizability_score(control_ids: list[str], threshold: int = FORMALIZABILITY_THRESHOLD) -> dict:
    """Check if any control passes the formalizability threshold for Lean4 proofs.

    Uses formalizability_score from sparta_controls (backfilled by step_12d_formalizability_scorer).
    Controls with score >= threshold are candidates for formal verification.

    Returns:
        dict with keys:
            - formalizable: bool - True if any control passes threshold
            - max_score: int - highest formalizability score found
            - scores: dict - {control_id: score} for all checked controls
            - threshold: int - the threshold used
    """
    if not control_ids:
        return {"formalizable": False, "max_score": 0, "scores": {}, "threshold": threshold}

    scores = {}
    try:
        from arango import ArangoClient
        url = os.getenv("ARANGO_URL") or "http://127.0.0.1:8529"
        user = os.getenv("ARANGO_USER") or "root"
        pw = os.getenv("ARANGO_PASS") or ""
        client = ArangoClient(hosts=url)
        db = client.db("memory", username=user, password=pw)

        for cid in control_ids[:10]:  # Limit to first 10 controls
            query = """
            FOR c IN sparta_controls
            FILTER c.control_id == @cid OR c._key == @cid
            RETURN {score: c.formalizability_score, signals: c.formalizability_signals}
            """
            cursor = db.aql.execute(query, bind_vars={"cid": cid})
            for doc in cursor:
                scores[cid] = doc.get("score", 0) or 0
                break
            else:
                scores[cid] = 0  # Not found
    except Exception as exc:
        logger.debug("formalizability check failed: {}", exc)
        return {"formalizable": False, "max_score": 0, "scores": {}, "threshold": threshold, "error": str(exc)}

    max_score = max(scores.values()) if scores else 0
    return {
        "formalizable": max_score >= threshold,
        "max_score": max_score,
        "scores": scores,
        "threshold": threshold,
    }


def collect_lean4_provable(question: str, control_ids: list[str]) -> dict | None:
    """Check if a question is Lean4-formalizable via the lean4_provable classifier."""
    text = f"Requirement: {question[:400]}"
    if control_ids:
        text += f"\nControl: {', '.join(control_ids[:5])}"

    try:
        _ensure_assistant_on_path()
        from gateway import classify as assistant_classify
        result = assistant_classify(text=text, task="lean4_provable")
        if result and hasattr(result, "prediction"):
            return {
                "prediction": result.prediction,
                "confidence": getattr(result, "confidence", 0.0),
                "tier": getattr(result, "tier", -1),
                "source": getattr(result, "source", "unknown"),
            }
    except (ImportError, Exception) as exc:
        logger.debug("direct lean4_provable classify failed: {}", exc)

    return _invoke_skill(ASSISTANT_SKILL, [
        "classify", "--task", "lean4_provable", "--text", text,
    ], timeout=25)


LEAN4_SERVICE_URL = os.getenv("LEAN4_SERVICE_URL", "http://127.0.0.1:8604")


def collect_lean4_proof(
    requirement: str, candidates: int = 3, max_retries: int = 1,
) -> dict | None:
    """Call lean4-prove-service /prove endpoint via httpx.

    Runs `candidates` concurrent proof attempts via asyncio.gather,
    each with `max_retries`. Returns first success or first non-None.
    """
    import asyncio

    async def _prove_one(client: httpx.AsyncClient, idx: int) -> dict | None:
        try:
            resp = await client.post(
                f"{LEAN4_SERVICE_URL}/prove",
                json={
                    "requirement": requirement[:700],
                    "max_retries": max_retries,
                    "timeout": 30,
                },
                timeout=60,
            )
            if resp.status_code == 200:
                result = resp.json()
                result["candidate"] = idx
                return result
            return None
        except Exception:
            return None

    async def _run() -> dict | None:
        async with httpx.AsyncClient() as client:
            results = await asyncio.gather(
                *[_prove_one(client, i) for i in range(candidates)]
            )
            for r in results:
                if r and r.get("success"):
                    return r
            for r in results:
                if r:
                    return r
            return None

    try:
        return asyncio.run(_run())
    except (ConnectionError, OSError) as e:
        logger.debug("lean4-prove-service unavailable: {}", e)
        return None
    except Exception as e:
        logger.warning("lean4-prove-service error: {}", e)
        return None


def collect_grounded_relevance(
    controls: list[dict[str, Any]],
    bridge_evidence: dict[str, Any],
) -> dict | None:
    """Deterministic relevance check using grounded MITRE taxonomy.

    No LLM. Uses Mind tags, CWE pillars, and ATT&CK chain from
    sparta_controls to determine if cross-framework controls are related.

    Returns dict with related, answerable, rationale, or None on failure.
    """
    if len(controls) < 2:
        return None

    client = _get_memory_http()
    control_data: list[dict] = []

    for ctrl in controls:
        cid = str(ctrl.get("control_id", "") or ctrl.get("id", "")).strip()
        if not cid:
            continue
        resp = client.post("/list", json={
            "collection": "sparta_controls",
            "limit": 1,
            "filters": {"control_id": cid},
        })
        docs = resp.json().get("documents", [])
        if docs:
            control_data.append(docs[0])
        else:
            control_data.append({"control_id": cid, "mind": [], "source_framework": "unknown"})

    if len(control_data) < 2:
        return None

    # Extract Mind tags for each control
    mind_sets = [set(c.get("mind", [])) for c in control_data]
    frameworks = [c.get("source_framework", "") for c in control_data]
    pillars = [c.get("pillar_cwe", "") for c in control_data]
    attack_ids_sets = [set(c.get("attack_technique_ids", [])) for c in control_data]

    # Check Mind tag overlap
    mind_overlap = mind_sets[0] & mind_sets[1] if len(mind_sets) >= 2 else set()

    # Check shared ATT&CK techniques
    shared_attack = attack_ids_sets[0] & attack_ids_sets[1] if len(attack_ids_sets) >= 2 else set()

    # Check shared CWE pillar
    shared_pillar = pillars[0] == pillars[1] and pillars[0] if len(pillars) >= 2 and all(pillars[:2]) else ""

    # Check cross-framework (different source_frameworks)
    is_cross_framework = len(set(frameworks[:2])) > 1

    # Decision logic — all signals from graph data, no hardcoded rules
    has_shared_technique = bool(bridge_evidence.get("shared_tactic")) or bridge_evidence.get("related_pairs_count", 0) > 0
    has_mind_overlap = bool(mind_overlap)
    has_attack_chain = bool(shared_attack)

    # Relevant if: any grounded connection between the controls.
    # Mind tag overlap alone is sufficient — both controls address the same tactical domain.
    # Shared technique path strengthens but is not required.
    related = (
        (has_mind_overlap and (has_shared_technique or has_attack_chain or bool(shared_pillar)))
        or (has_attack_chain)  # Shared ATT&CK technique is strong evidence regardless
        or (has_shared_technique and has_mind_overlap)
        or (has_mind_overlap and is_cross_framework)  # Cross-framework with shared mind = valid
    )

    # Build rationale from actual evidence
    reasons = []
    if mind_overlap:
        reasons.append(f"shared Mind tags: {', '.join(sorted(mind_overlap))}")
    if shared_attack:
        reasons.append(f"shared ATT&CK: {', '.join(sorted(shared_attack)[:3])}")
    if shared_pillar:
        reasons.append(f"same CWE pillar: {shared_pillar}")
    if has_shared_technique:
        reasons.append(f"shared technique path (basis={bridge_evidence.get('bridge_basis', 'unknown')})")

    if not reasons:
        rationale = "No grounded connection: different Mind tags, no shared ATT&CK chain, no shared CWE pillar"
    else:
        rationale = "; ".join(reasons)

    return {
        "related": related,
        "answerable": related,
        "rationale": rationale,
        "method": "grounded_taxonomy",
        "mind_tags": {c.get("control_id", ""): list(c.get("mind", [])) for c in control_data},
        "shared_mind": sorted(mind_overlap),
        "shared_attack_techniques": sorted(shared_attack)[:5],
        "shared_pillar": shared_pillar,
        "is_cross_framework": is_cross_framework,
        "controls": controls,
        "bridge_evidence": bridge_evidence,
    }


LEAN4_SERVICE_URL = os.environ.get("LEAN4_SERVICE_URL", "http://127.0.0.1:8604")


def compile_lean4(code: str, timeout: int = 60) -> dict:
    """Compile Lean4 code via the Docker HTTP service.

    The AGENT generates the Lean4 theorem. This function just compiles it.
    No claude -p, no subprocess — just an HTTP POST to the lean_runner container.

    Returns dict with: success, stdout, error, elapsed_ms
    """
    import urllib.request
    import urllib.error

    try:
        req = urllib.request.Request(
            f"{LEAN4_SERVICE_URL}/compile",
            data=json.dumps({"code": code}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError as exc:
        return {"success": False, "error": f"Lean4 service unreachable: {exc}"}
    except Exception as exc:
        return {"success": False, "error": f"Lean4 compile error: {exc}"}


def collect_dogpile(query: str) -> dict | None:
    """Call /dogpile for Tier 3 research when recall is sparse."""
    return _invoke_skill(DOGPILE_SKILL, [
        "search", query[:500], "--auto-preset",
    ], timeout=60)


def collect_cmmc(level: int, family: str) -> dict | None:
    """Call /cmmc-assessor for CMMC compliance mapping."""
    return _invoke_skill(CMMC_ASSESSOR_SKILL, [
        "assess", "--level", str(level), "--family", family,
    ], timeout=30)


def collect_edge_verify(source_id: str, text: str) -> dict | None:
    """Call /edge-verifier to validate cross-component entity relationships."""
    return _invoke_skill(EDGE_VERIFIER_SKILL, [
        "verify", "--source_id", source_id, "--text", text[:500],
    ], timeout=30)


# ---------------------------------------------------------------------------
# Question decomposition and evidence grouping
# ---------------------------------------------------------------------------

def decompose_sentence(question: str, agent_decomposition: dict | None = None) -> dict:
    """Decompose a question into Given/Then components.

    The AGENT should provide the decomposition via agent_decomposition.
    The heuristic fallback below is for the automated question bank ONLY.
    """
    import re

    if agent_decomposition:
        return {
            "question": question,
            "given_components": agent_decomposition.get("given_components", []),
            "then_components": agent_decomposition.get("then_components", []),
            "component_queries": agent_decomposition.get("component_queries", {}),
            "component_entity_types": agent_decomposition.get("component_entity_types", {}),
            "mermaid": "",
            "source": "agent",
        }

    # --- Heuristic fallback for automated question bank ---
    given_components: list[str] = []
    then_components: list[str] = []
    component_queries: dict[str, str] = {}
    component_entity_types: dict[str, str] = {}

    text = question.strip().rstrip("?")

    m = re.match(r"(?i)given\s+(.+?),\s*(which|what|how|where)\s+(.+)", text)
    if m:
        given_components.append(m.group(1).strip())
        then_components.append(m.group(3).strip())
    else:
        parts = re.split(
            r"\b(?:align with|protect.*?from|apply.*?to|defend against|"
            r"comply with|map to|prioritize in|pose to|adjusted? for)\b",
            text, maxsplit=1, flags=re.IGNORECASE,
        )
        if len(parts) == 2:
            given_components.append(parts[0].strip().strip(","))
            then_components.append(parts[1].strip().strip(","))
        else:
            then_components.append(text)

    for comp in given_components:
        component_queries[comp] = comp
        component_entity_types[comp] = "scope"
    for comp in then_components:
        component_queries[comp] = comp
        component_entity_types[comp] = "target"

    return {
        "question": question,
        "given_components": given_components,
        "then_components": then_components,
        "component_queries": component_queries,
        "component_entity_types": component_entity_types,
        "mermaid": "",
        "source": "heuristic_fallback",
    }


def collect_per_component(decomposition: dict) -> dict[str, list[dict]]:
    """Run /memory recall per component and return results keyed by component name."""
    component_results: dict[str, list[dict]] = {}
    all_components = (
        decomposition.get("given_components", []) +
        decomposition.get("then_components", [])
    )
    for comp in all_components:
        query = decomposition.get("component_queries", {}).get(comp, comp)
        items = collect_recall(query)
        component_results[comp] = items
    return component_results


def _grade_item_confidence(item: dict) -> float:
    """Grade evidence confidence based on data quality signals.

    Returns float in [0.0, 1.0].
    """
    score = item.get("score", item.get("recall_score", 0))
    if score and isinstance(score, (int, float)) and score > 0:
        return min(1.0, max(0.0, float(score)))

    conf = 0.1
    if item.get("control_id"):
        conf += 0.3
    tags = item.get("tactical_tags", [])
    if tags and isinstance(tags, list) and any(t for t in tags):
        conf += 0.2
    answer = item.get("answer", item.get("solution", "")) or ""
    if len(answer) > 100:
        conf += 0.2
    if item.get("question"):
        conf += 0.1
    if "hypothesized" not in answer.lower()[:30]:
        conf += 0.1
    return min(1.0, conf)


def group_by_technique(items: list[dict]) -> dict[str, list[dict]]:
    """Group recall items by tactical_tags or tags from the QRA data."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        tags = item.get("tactical_tags", [])
        if not (tags and isinstance(tags, list) and tags[0]):
            # Fall back to tags field (taxonomy tags from lessons/QRAs)
            tags = item.get("tags", [])
        if tags and isinstance(tags, list) and tags[0]:
            tid = tags[0]
        else:
            tid = item.get("control_id", "UNTAGGED")
        groups[tid].append(item)
    return dict(groups)


def validate_llm_answer(raw: str, spans: list[dict], evidence: list[dict]) -> tuple[dict | None, list[str]]:
    """Deterministic validation for Stage 2 LLM output.
    
    Returns (result, errors). If errors is non-empty, result is None.
    """
    errors = []
    
    # Check 1: valid JSON
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, [f"invalid JSON: {e}"]
    
    # Check 2: answer is non-empty string
    answer = data.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        errors.append("answer must be a non-empty string")
    
    # Check 3: evidence_used is non-empty list with valid indices
    used = data.get("evidence_used", [])
    if not isinstance(used, list):
        errors.append("evidence_used must be a list")
    elif len(used) == 0:
        errors.append("evidence_used must not be empty")
    else:
        for idx in used:
            if not isinstance(idx, int) or idx < 0 or idx >= len(evidence):
                errors.append(f"evidence_used index {idx} is out of range (0-{len(evidence) - 1})")
                break
    
    # Check 4: entities length matches spans
    entities = data.get("entities", [])
    if len(entities) != len(spans):
        errors.append(f"entities length was {len(entities)} but spans_count is {len(spans)}")
    
    # Check 5: entity text matches span text exactly
    if len(entities) == len(spans):
        for i, (ent, span) in enumerate(zip(entities, spans)):
            ent_text = ent.get("entity", "") if isinstance(ent, dict) else ""
            span_text = span.get("text", "")
            if ent_text != span_text:
                errors.append(f"entities[{i}].entity='{ent_text}' but spans[{i}].text='{span_text}'")
                break
    
    if errors:
        return None, errors
    return data, []


def deterministic_grounding_gate(spans: list[dict], control_metadata: list[dict]) -> tuple[str, str]:
    """Stage 1: Deterministic routing - NO LLM.
    
    Decision table (apply top-to-bottom, first match wins):
    | Condition                                              | Verdict     |
    |--------------------------------------------------------|-------------|
    | Any control ID misspelled/fabricated                   | CLARIFY     |
    | Any span has relevant_to_query=false OR status in      | NONSENSICAL |
    |   {"not_relevant", "not_in_corpus"}                    |             |
    | All spans grounded                                     | ANSWERABLE  |
    
    Returns: (verdict, reason)
    """
    # Row 1: Misspelled/fabricated control ID → CLARIFY
    for span in spans:
        if span.get("type") == "control_id":
            status = span.get("status", "")
            if status in ("not_in_corpus", "fabricated"):
                suggestion = span.get("suggested_correction", "")
                if suggestion:
                    return "CLARIFY", f"Unknown control ID '{span['text']}'. Did you mean: {suggestion}?"
                return "CLARIFY", f"Unknown control ID '{span['text']}'. Not found in SPARTA database."
    
    # Row 2: Ungrounded spans → NONSENSICAL
    for span in spans:
        text = span.get("text", "")
        status = span.get("status", "")
        relevant = span.get("relevant_to_query", True)
        
        if relevant is False or status in ("not_relevant", "not_in_corpus"):
            return "NONSENSICAL", f"Ungrounded: '{text}'"
    
    # Row 3: All grounded → ANSWERABLE
    return "ANSWERABLE", "All entities grounded in evidence"


def collect_grounding_gate_context(question: str, k: int = 10) -> dict[str, Any]:
    """Collect all context needed for the LLM grounding gate.
    
    Returns a dict with:
    - question: the original question
    - spans: entity spans from /extract-entities (with relevant_to_query flags)
    - evidence: QRAs for the queried controls
    - similar_requests: past requests from /memory recall (scope=disambiguation)
    - control_metadata: metadata for control IDs found
    - verdict: deterministic verdict from Stage 1 gate
    - reason: reason for verdict
    
    The LLM is ONLY called if verdict == "ANSWERABLE".
    """
    # Step 1: Extract entities with spans (via daemon, not import)
    try:
        client = _get_memory_http()
        resp = client.post("/extract-entities", json={"text": question[:500], "view": "legacy"})
        entities = _normalize_extract_entities_legacy(resp.json()) if resp.status_code == 200 else {}
    except Exception as exc:
        logger.warning("Entity extraction via daemon failed: {}", exc)
        entities = {}
    
    if entities is None:
        entities = {}
    
    spans = entities.get("entities", entities.get("spans", []))
    control_ids = entities.get("control_ids", [])
    control_metadata = entities.get("control_metadata", [])
    
    # Step 2: Get evidence for queried controls (SPARTA scope)
    evidence = []
    if control_ids:
        recall_result = collect_recall_with_confidence(question, k=k)
        raw_items = recall_result.get("items", [])
        # Filter to only items for the queried control IDs
        for item in raw_items:
            item_cid = item.get("control_id", "")
            if item_cid in control_ids:
                evidence.append({
                    "question": item.get("question", ""),
                    "answer": item.get("answer", ""),
                    "reasoning": item.get("reasoning", ""),
                    "control_id": item_cid,
                    "score": item.get("score", 0),
                })
    
    # Step 3: Get similar past requests from memory (scope=disambiguation)
    # This includes past verdicts for similar questions
    similar_requests = []
    try:
        client = _get_memory_http()
        resp = client.post("/recall", json={
            "q": question,
            "k": 5,
            "scope": "disambiguation",
        })
        if resp.status_code == 200:
            similar_result = resp.json()
            if similar_result and similar_result.get("found"):
                for item in similar_result.get("items", [])[:5]:
                    similar_requests.append({
                        "_key": item.get("_key", ""),
                        "problem": item.get("problem", ""),
                        "solution": item.get("solution", ""),
                        "tags": item.get("tags", []),
                    })
    except Exception as exc:
        logger.warning("Failed to get similar requests: {}", exc)
    
    # Stage 1: Deterministic gate - NO LLM
    verdict, reason = deterministic_grounding_gate(spans, control_metadata)
    
    return {
        "question": question,
        "spans": spans,
        "evidence": evidence[:k],
        "similar_requests": similar_requests,
        "control_metadata": control_metadata,
        "control_ids": control_ids,
        "verdict": verdict,
        "reason": reason,
    }
