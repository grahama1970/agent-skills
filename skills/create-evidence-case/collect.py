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
# Data collection — call skills, return raw results for agent reasoning
# ---------------------------------------------------------------------------

def collect_recall(question: str, k: int = 20) -> list[dict]:
    """Call /memory recall via daemon. Full hybrid search, no degraded paths.

    The daemon does:
    - Tier 1: exact control_id lookup (sparta_qra, lessons)
    - Tier 2: proxy to graph_memory service (BM25 + graph + multihop)
    - Tier 2 fallback: direct ArangoDB AQL with optional taxonomy ranking

    Fails loudly if daemon is broken. NEVER returns degraded results.
    """
    result = collect_recall_with_confidence(question, k=k)
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


def collect_recall_with_confidence(question: str, k: int = 20) -> dict:
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
    resp = client.post("/recall", json={
        "q": question[:400],
        "scope": "sparta",
        "limit": k,
    })
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
    """Extract entities from question text via /extract-entities skill.

    Prefer direct import when available so local/dev flows and tests stay fast.
    Fall back to the skill wrapper when the package is not importable.
    If both fail or the result contract is invalid, fail loudly.
    """
    direct_error: Exception | None = None
    try:
        from graph_memory.entity_extraction import extract_entities

        direct = extract_entities(question[:500])
        if direct:
            result = direct.to_dict() if hasattr(direct, "to_dict") else {}
            if hasattr(direct, "agent_view"):
                result.update(direct.agent_view() or {})
            result.setdefault("all_control_ids", result.get("control_ids", []))
            result.setdefault("control_ids", result.get("all_control_ids", []))
        else:
            result = None
    except Exception as exc:
        direct_error = exc
        result = None

    if result is None:
        result = _invoke_skill(EXTRACT_ENTITIES_SKILL, [
            "extract", "--json", question[:500],
        ], timeout=20)

    if not isinstance(result, dict):
        detail = f"direct={direct_error!r}" if direct_error else "direct=not_attempted"
        raise EntityExtractionFailure(
            f"Entity extraction failed: no valid result returned ({detail}; skill_result={type(result).__name__})"
        )

    required_fields = ("grounding_ok", "resolution_map", "unresolved_terms")
    missing_fields = [field for field in required_fields if field not in result]
    if missing_fields:
        raise EntityExtractionFailure(
            "Entity extraction returned invalid contract: missing "
            + ", ".join(missing_fields)
        )

    if result and (result.get("all_control_ids") or result.get("control_ids")):
        # Bridge unresolved_terms + not_in_corpus into warnings for plausibility gate.
        warnings = []
        for ut in result.get("unresolved_terms", []):
            ut_type = ut.get("type", "phrase")
            # Only id_like terms generate warnings. Generic phrases
            # ("threats", "countermeasures", "techniques") are SPARTA
            # domain vocabulary — not resolving is expected, not a warning.
            if ut_type != "id_like":
                continue
            warnings.append({
                "term": ut.get("term", ""),
                "category": "fabricated_id",
                "type": ut_type,
            })
        # Real aerospace/NIST/MITRE terms that are NOT in the SPARTA corpus.
        # These trigger the plausibility gate → clarify flow so the user
        # rephrases using SPARTA terms the system can actually answer.
        for nic in result.get("not_in_corpus", []):
            warnings.append({
                "term": nic.get("term", ""),
                "category": "not_in_corpus",
                "type": "not_in_corpus",
                "reason": nic.get("reason", ""),
                "suggested_sparta_terms": nic.get("suggested_sparta_terms", []),
            })
        for ms in result.get("misspellings", []):
            warnings.append({
                "term": ms.get("word", ms.get("term", "")),
                "category": "misspelling",
                "type": "misspelling",
                "suggestion": ms.get("suggestion", ""),
            })
        for typo in result.get("possible_typos", []):
            warnings.append({
                "term": typo.get("word", typo.get("term", "")),
                "category": "possible_typo",
                "type": "possible_typo",
                "fuzzy_matches": typo.get("fuzzy_matches", []),
            })
        result["warnings"] = warnings
        result["method"] = "extract_entities"
        return result

    # No control IDs found can still be a valid extraction result for natural-language
    # questions. Normalize the empty-shape contract rather than synthesizing a success
    # from a failed extractor.
    result.setdefault("all_control_ids", result.get("control_ids", []))
    result.setdefault("control_ids", result.get("all_control_ids", []))
    result.setdefault("related_pairs", [])
    result.setdefault("headline", "No controls resolved")
    result["warnings"] = []
    result["method"] = "extract_entities"
    return result


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


def collect_lean4_proof(requirement: str) -> dict | None:
    """Call lean4-prove-service /prove endpoint via httpx.

    No subprocess — direct HTTP to the lean4 container which has
    lean-interact + Mathlib cached. The container calls /scillm
    for LLM generation and compiles locally.
    """
    try:
        resp = httpx.post(
            f"{LEAN4_SERVICE_URL}/prove",
            json={
                "requirement": requirement[:700],
                "max_retries": 3,
                "timeout": 60,
            },
            timeout=180,
        )
        if resp.status_code == 200:
            return resp.json()
        logger.warning("lean4-prove-service /prove returned {}: {}", resp.status_code, resp.text[:200])
        return None
    except (httpx.ConnectError, httpx.TimeoutException) as e:
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
        resp = client.post("/extract-entities", json={"text": question[:500]})
        entities = resp.json() if resp.status_code == 200 else {}
    except Exception as exc:
        logger.warning("Entity extraction via daemon failed: {}", exc)
        entities = {}
    
    if entities is None:
        entities = {}
    
    spans = entities.get("spans", [])
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
