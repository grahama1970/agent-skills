"""Core orchestration for skill chain recommendation.

Gather-and-rank strategy: collects candidates from all tiers,
ranks by bond_strength * elegance. NO reimplementation — every
component delegates to existing functions.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SKILLS_ROOT = Path(__file__).resolve().parents[2]
SKILL_LAB_SCRIPTS = SKILLS_ROOT / "skill-lab" / "scripts"
COMMON_DIR = SKILLS_ROOT / "common"
ASSISTANT_DIR = SKILLS_ROOT / "assistant"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Ensure data dir exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

RECOMMENDATIONS_LOG = DATA_DIR / "recommendations.jsonl"
SHADOW_LOG = DATA_DIR / "shadow.jsonl"

# ---------------------------------------------------------------------------
# Lazy imports with graceful fallback
# ---------------------------------------------------------------------------
_scan_soup = None
_predict_chain = None
_detect_gaps = None
_predict_chain_success = None
_compute_chain_energy = None
_compute_elegance = None
_assistant_classify = None
_assistant_validate = None
_CascadeRunner = None


def _ensure_imports():
    """Import skill-lab and assistant modules via sys.path injection."""
    global _scan_soup, _predict_chain, _detect_gaps
    global _predict_chain_success, _compute_chain_energy, _compute_elegance
    global _assistant_classify, _assistant_validate, _CascadeRunner

    if _scan_soup is not None:
        return  # Already imported

    # Add skill-lab scripts to path
    for p in [str(SKILL_LAB_SCRIPTS), str(COMMON_DIR), str(ASSISTANT_DIR), str(SKILLS_ROOT)]:
        if p not in sys.path:
            sys.path.insert(0, p)

    try:
        from scan_soup import scan_soup
        _scan_soup = scan_soup
    except ImportError:
        logger.warning("scan_soup unavailable")

    try:
        from transition_matrix import predict_chain
        _predict_chain = predict_chain
    except ImportError:
        logger.warning("transition_matrix unavailable")

    try:
        from gap_detector import detect_gaps
        _detect_gaps = detect_gaps
    except ImportError:
        logger.warning("gap_detector unavailable")

    try:
        from bond_predictor import predict_chain_success
        _predict_chain_success = predict_chain_success
    except ImportError:
        logger.warning("bond_predictor unavailable")

    try:
        from energy_model import compute_chain_energy, compute_elegance
        _compute_chain_energy = compute_chain_energy
        _compute_elegance = compute_elegance
    except ImportError:
        logger.warning("energy_model unavailable")

    try:
        from assistant import classify as assistant_classify
        from assistant import validate as assistant_validate
        _assistant_classify = assistant_classify
        _assistant_validate = assistant_validate
    except ImportError:
        logger.warning("assistant unavailable")

    try:
        from common.cascade import CascadeRunner
        _CascadeRunner = CascadeRunner
    except ImportError:
        try:
            from cascade import CascadeRunner
            _CascadeRunner = CascadeRunner
        except ImportError:
            logger.warning("CascadeRunner unavailable")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class ChainCandidate:
    chain: list[str]
    confidence: float = 0.0
    tier: str = "unknown"
    reason: str = ""
    source_data: dict = field(default_factory=dict)


@dataclass
class RankedRecommendation:
    rank: int
    chain: list[str]
    orchestrator: str | None
    confidence: float
    tier: str
    elegance: str
    energy_atp: float
    reason: str
    bridge_tags: list[str]


# ---------------------------------------------------------------------------
# Graph cache
# ---------------------------------------------------------------------------
_graph_cache: dict | None = None
_graph_ts: float = 0.0
GRAPH_TTL = 300  # 5 min cache


def _get_graph() -> dict | None:
    global _graph_cache, _graph_ts
    _ensure_imports()
    if _scan_soup is None:
        return None
    now = time.time()
    if _graph_cache is None or (now - _graph_ts) > GRAPH_TTL:
        try:
            _graph_cache = _scan_soup(SKILLS_ROOT)
            _graph_ts = now
        except Exception as e:
            logger.error(f"scan_soup failed: {e}")
            return _graph_cache  # Return stale if available
    return _graph_cache


# ---------------------------------------------------------------------------
# Phase 1: Memory recall
# ---------------------------------------------------------------------------
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

def _recall_memory(task: str) -> list[ChainCandidate]:
    """Query memory for prior successful chains matching this task."""
    candidates = []
    try:
        result = _memory_cmd([
            "recall", "--q", f"skill chain for: {task}",
            "--k", "5", "--scope", "skill-chains",
        ])
        for r in result.get("items", result.get("results", [])):
            if isinstance(r, dict) and "chain" in r:
                candidates.append(ChainCandidate(
                    chain=r["chain"],
                    confidence=r.get("confidence", 0.6),
                    tier="memory",
                    reason=f"Prior successful chain: {r.get('task', 'unknown')}",
                ))
    except Exception as e:
        logger.debug(f"Memory recall not available: {e}")
    return candidates


# Phase 1b: checkpoint_recall.py
try:
    from .checkpoint_recall import recall_successful_checkpoints as _recall_cp
except ImportError:
    from checkpoint_recall import recall_successful_checkpoints as _recall_cp


def _recall_successful_checkpoints(task: str) -> list[ChainCandidate]:
    return [ChainCandidate(**r) for r in _recall_cp(task, _memory_cmd)]


# ---------------------------------------------------------------------------
# Phase 2: Tier 0 — heuristic (transition matrix + gap detector)
# ---------------------------------------------------------------------------
def _tier0_heuristic(task: str) -> list[ChainCandidate]:
    """Use transition matrix and gap detector for heuristic chain prediction."""
    _ensure_imports()
    candidates = []

    # Transition matrix prediction
    if _predict_chain is not None:
        try:
            result = _predict_chain(task=task)
            if result and result.get("chain"):
                # Cap confidence for cold_start/low predictions — chain_probability
                # defaults to 1.0 when no transition data exists, which would
                # dominate the ranking over the trained classifier.
                raw_prob = result.get("chain_probability", 0.0)
                conf_level = result.get("confidence", "cold_start")
                if conf_level in ("cold_start", "low"):
                    raw_prob = min(raw_prob, 0.15)
                elif conf_level == "medium":
                    raw_prob = min(raw_prob, 0.5)
                candidates.append(ChainCandidate(
                    chain=result["chain"],
                    confidence=raw_prob,
                    tier="heuristic",
                    reason=f"Markov chain prediction (confidence: {conf_level})",
                    source_data=result,
                ))
        except Exception as e:
            logger.warning(f"predict_chain failed: {e}")

    # Gap detector — find required capabilities and map to skills
    graph = _get_graph()
    if _detect_gaps is not None and graph is not None:
        try:
            gaps = _detect_gaps(task=task, graph=graph)
            if gaps and gaps.get("have"):
                chain = [h["skill"] for h in gaps["have"] if "skill" in h]
                if chain:
                    candidates.append(ChainCandidate(
                        chain=chain,
                        confidence=gaps.get("coverage", 0.0),
                        tier="heuristic",
                        reason=f"Gap analysis: {gaps.get('coverage', 0):.0%} capability coverage",
                        source_data=gaps,
                    ))
        except Exception as e:
            logger.warning(f"detect_gaps failed: {e}")

    # Trigger matching from graph
    if graph and "skills" in graph:
        trigger_matches = []
        task_lower = task.lower()
        for skill_name, skill_info in graph["skills"].items():
            triggers = skill_info.get("triggers", [])
            for trigger in triggers:
                if trigger.lower() in task_lower or task_lower in trigger.lower():
                    trigger_matches.append(skill_name)
                    break
        if trigger_matches:
            candidates.append(ChainCandidate(
                chain=trigger_matches,
                confidence=0.5,
                tier="heuristic",
                reason=f"Trigger match: {', '.join(trigger_matches)}",
            ))

    return candidates


# ---------------------------------------------------------------------------
# Phase 3: Tier 0.5 — two-level classifier (category + retrieval)
# ---------------------------------------------------------------------------
_category_clf = None
_retrieval_index = None
_models_loaded = False


def _load_classifier_models():
    """Lazy-load category classifier and retrieval index."""
    global _category_clf, _retrieval_index, _models_loaded
    if _models_loaded:
        return
    _models_loaded = True

    import os
    try:
        import joblib
    except ImportError:
        logger.warning("joblib not available for classifier")
        return

    cat_path = os.path.expanduser(
        "~/.pi/models/classifiers/skill_category_classifier.joblib"
    )
    if os.path.exists(cat_path):
        try:
            _category_clf = joblib.load(cat_path)
        except Exception as e:
            logger.warning(f"Failed to load category classifier: {e}")

    idx_path = os.path.expanduser(
        "~/.pi/models/classifiers/skill_retrieval_index.joblib"
    )
    if os.path.exists(idx_path):
        try:
            _retrieval_index = joblib.load(idx_path)
        except Exception as e:
            logger.warning(f"Failed to load retrieval index: {e}")


def _tier05_classifier(task: str) -> list[ChainCandidate]:
    """Classify via /assistant cascade, then refine with TF-IDF retrieval.

    Routes through assistant.classify(task="skill-chain-router") which uses
    CascadeRunner with shadow_mode=true from model_registry.json. This enables
    automatic shadow comparison (classifier vs teacher) — the self-improvement
    loop that was previously broken by direct joblib loading.

    The cascade result gives a category/chain prediction. We then refine it
    with TF-IDF cosine similarity retrieval against SKILL.md descriptions.

    These are RECOMMENDATIONS for the agent to /assess — guidance, not routing.
    """
    _ensure_imports()
    _load_classifier_models()
    candidates = []

    # Level 1: Cascade classification via /assistant
    # This goes through CascadeRunner: heuristic → classifier → GPT → teacher
    # Shadow mode logs classifier vs teacher comparison automatically
    cascade_prediction = None
    cascade_conf = 0.0

    if _assistant_classify is not None:
        try:
            import signal

            def _cascade_timeout(signum, frame):
                raise TimeoutError("Cascade classify timed out")

            old_handler = signal.signal(signal.SIGALRM, _cascade_timeout)
            signal.alarm(3)  # 3s max — classifier ~5ms, GPT ~200ms; teacher ~2-5s when available
            try:
                result = _assistant_classify(
                    text=task,
                    task="skill-chain-router",
                )
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)

            if result and result.confidence > 0:
                cascade_prediction = result.prediction
                # Filter out error results the cascade may return
                if isinstance(cascade_prediction, str) and "error" in cascade_prediction.lower():
                    logger.debug(f"Cascade returned error result: {cascade_prediction}")
                    cascade_prediction = None
                else:
                    cascade_conf = result.confidence
                    chain = _parse_chain_prediction(cascade_prediction)
                    if chain:
                        candidates.append(ChainCandidate(
                            chain=chain,
                            confidence=round(cascade_conf, 3),
                            tier=f"classifier/{result.tier}" if hasattr(result, "tier") else "classifier",
                            reason=f"Cascade: {result.source if hasattr(result, 'source') else 'unknown'} → {cascade_prediction}",
                            source_data={
                                "cascade_tier": getattr(result, "tier", None),
                                "cascade_source": getattr(result, "source", None),
                                "prediction": cascade_prediction,
                            },
                        ))
        except TimeoutError:
            logger.warning("assistant.classify timed out after 3s — falling back to retrieval")
        except Exception as e:
            logger.warning(f"assistant.classify failed: {e}")

    # Level 2: TF-IDF retrieval to refine/supplement cascade output
    if _retrieval_index is not None:
        try:
            from sklearn.metrics.pairwise import cosine_similarity

            vectorizer = _retrieval_index["tfidf_vectorizer"]
            skill_vectors = _retrieval_index["skill_vectors"]
            skill_names = _retrieval_index["skill_names"]
            skill_categories = _retrieval_index.get("skill_categories", {})

            q_vec = vectorizer.transform([task])
            sims = cosine_similarity(q_vec, skill_vectors).flatten()

            # Boost skills matching cascade prediction
            if cascade_prediction:
                predicted_skills = set(_parse_chain_prediction(cascade_prediction))
                for i, name in enumerate(skill_names):
                    if name in predicted_skills:
                        sims[i] *= 2.0  # Double score for cascade-predicted skills

            # Get top-5 skills by similarity
            top_idx = sims.argsort()[-5:][::-1]
            top_skills = [
                (skill_names[i], float(sims[i]), skill_categories.get(skill_names[i], ""))
                for i in top_idx if sims[i] > 0.05
            ]

            if top_skills:
                best_name, best_sim, best_cat = top_skills[0]
                retrieval_conf = min(0.85, best_sim * 1.2)
                candidates.append(ChainCandidate(
                    chain=[best_name],
                    confidence=round(retrieval_conf, 3),
                    tier="retrieval",
                    reason=f"TF-IDF retrieval: {best_name} (sim={best_sim:.2f})",
                    source_data={
                        "retrieved_skills": [
                            {"skill": n, "similarity": round(s, 3), "category": c}
                            for n, s, c in top_skills
                        ],
                    },
                ))

                # Multi-skill chain from strong retrieval matches
                strong_matches = [(n, s, c) for n, s, c in top_skills[1:4] if s > 0.10]
                if strong_matches:
                    chain = [best_name] + [n for n, _, _ in strong_matches]
                    candidates.append(ChainCandidate(
                        chain=chain,
                        confidence=round(retrieval_conf * 0.8, 3),
                        tier="retrieval",
                        reason=f"Multi-skill retrieval chain",
                        source_data={
                            "chain_skills": [
                                {"skill": n, "similarity": round(s, 3)}
                                for n, s, _ in [(best_name, best_sim, best_cat)] + strong_matches
                            ],
                        },
                    ))
        except Exception as e:
            logger.warning(f"TF-IDF retrieval failed: {e}")

    # Fallback: if cascade and retrieval both failed, try direct joblib
    if not candidates:
        _load_classifier_models()
        if _category_clf is not None:
            try:
                category = _category_clf.predict([task])[0]
                proba = _category_clf.predict_proba([task])[0]
                category_conf = float(max(proba))
                candidates.append(ChainCandidate(
                    chain=[category],
                    confidence=round(category_conf, 3),
                    tier="classifier/fallback",
                    reason=f"Direct classifier fallback (cascade unavailable): {category}",
                    source_data={"category": category, "confidence": round(category_conf, 3)},
                ))
            except Exception as e:
                logger.warning(f"Fallback classifier failed: {e}")

    return candidates


def _parse_chain_prediction(prediction: str) -> list[str]:
    """Parse a classifier prediction into a skill chain list."""
    if not prediction:
        return []
    # Predictions may be comma-separated, arrow-separated, or JSON
    if prediction.startswith("["):
        try:
            return json.loads(prediction)
        except json.JSONDecodeError:
            pass
    for sep in ["→", "->", ",", " | "]:
        if sep in prediction:
            return [s.strip() for s in prediction.split(sep) if s.strip()]
    return [prediction.strip()] if prediction.strip() else []


# ---------------------------------------------------------------------------
# Phase 4: Tier 2 — teacher (scillm, only if max confidence < 0.7)
# ---------------------------------------------------------------------------
def _tier2_teacher(task: str, max_confidence: float) -> list[ChainCandidate]:
    """Escalate to scillm teacher if confidence is below threshold."""
    _ensure_imports()
    candidates = []

    if max_confidence >= 0.7:
        logger.debug(f"Skipping teacher: max confidence {max_confidence:.2f} >= 0.7")
        return candidates

    if _assistant_validate is not None:
        try:
            import signal

            def _timeout_handler(signum, frame):
                raise TimeoutError("Teacher validation timed out")

            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(10)  # 10s timeout for teacher call
            try:
                result = _assistant_validate(
                    input_data={"task": task, "query": f"What skill chain should handle: {task}"},
                    task="chain-rationale",
                    confidence_threshold=0.7,
                )
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
            if result and result.confidence > 0:
                prediction = result.prediction if hasattr(result, "prediction") else ""
                chain = _parse_chain_prediction(prediction)
                # Also check result dict for structured chain
                if not chain and hasattr(result, "result") and isinstance(result.result, dict):
                    chain = result.result.get("chain", [])
                if chain:
                    candidates.append(ChainCandidate(
                        chain=chain,
                        confidence=result.confidence,
                        tier="teacher",
                        reason=f"scillm teacher validation (tier {result.tier})",
                        source_data=result.to_dict() if hasattr(result, "to_dict") else {},
                    ))
        except Exception as e:
            logger.warning(f"Teacher validation failed: {e}")

    return candidates


# ---------------------------------------------------------------------------
# Phase 5: Rank — delegated to ranking.py
# ---------------------------------------------------------------------------
try:
    from .ranking import detect_orchestrator as _detect_orchestrator
    from .ranking import log_recommendation as _log_recommendation_impl
    from .ranking import log_shadow_comparison as _log_shadow_comparison_impl
    from .ranking import rank_candidates as _rank_candidates_impl
except ImportError:
    from ranking import detect_orchestrator as _detect_orchestrator
    from ranking import log_recommendation as _log_recommendation_impl
    from ranking import log_shadow_comparison as _log_shadow_comparison_impl
    from ranking import rank_candidates as _rank_candidates_impl
import httpx


def _rank_candidates(
    candidates: list[ChainCandidate],
    task: str,
) -> list[RankedRecommendation]:
    """Score and rank candidates using bond predictor + energy model."""
    _ensure_imports()
    return _rank_candidates_impl(
        candidates, task,
        graph=_get_graph(),
        predict_chain_success=_predict_chain_success,
        compute_chain_energy=_compute_chain_energy,
        compute_elegance=_compute_elegance,
    )


def _log_recommendation(task: str, recommendations: list[RankedRecommendation], model: str | None = None):
    _log_recommendation_impl(task, recommendations, RECOMMENDATIONS_LOG, model=model)


def _log_shadow_comparison(task: str, candidates: list[ChainCandidate]):
    _log_shadow_comparison_impl(task, candidates, SHADOW_LOG)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def recommend(task: str, limit: int = 5, model: str | None = None) -> dict:
    """Main entry point: recommend skill chains for a task.

    Returns dict with task, recommendations, and shadow status.
    """
    _ensure_imports()
    all_candidates: list[ChainCandidate] = []

    # Phase 1: Memory recall
    all_candidates.extend(_recall_memory(task))

    # Phase 1b: Successful checkpoint chains (proven to work)
    all_candidates.extend(_recall_successful_checkpoints(task))

    # Phase 2: Tier 0 heuristic
    all_candidates.extend(_tier0_heuristic(task))

    # Phase 3: Cascade classifier (routes through /assistant with shadow mode)
    # CascadeRunner handles tier escalation + teacher automatically
    all_candidates.extend(_tier05_classifier(task))

    # Phase 4: Tier 1.5 chain-rationale GPT (shadow mode)
    # Calls assistant.validate(task="chain-rationale") — local GGUF, $0 cost
    # Only fires when classifier confidence < 0.7 (avoids redundant calls)
    max_conf = max((c.confidence for c in all_candidates), default=0.0)
    all_candidates.extend(_tier2_teacher(task, max_conf))

    # Phase 5: Rank
    ranked = _rank_candidates(all_candidates, task)[:limit]

    # Log
    _log_recommendation(task, ranked, model=model)
    _log_shadow_comparison(task, all_candidates)

    # Shadow status
    shadow = get_shadow_status()

    return {
        "task": task,
        "recommendations": [
            {
                "rank": r.rank,
                "chain": r.chain,
                "orchestrator": r.orchestrator,
                "confidence": r.confidence,
                "tier": r.tier,
                "elegance": r.elegance,
                "energy_atp": r.energy_atp,
                "reason": r.reason,
                "bridge_tags": r.bridge_tags,
            }
            for r in ranked
        ],
        "shadow": shadow,
    }


def evaluate(skills: list[str]) -> dict:
    """Evaluate a specific skill chain's bond strength and elegance."""
    _ensure_imports()
    graph = _get_graph()
    result: dict[str, Any] = {"chain": skills}

    if _predict_chain_success is not None:
        try:
            bond_result = _predict_chain_success(skills=skills, graph=graph)
            result["success_probability"] = bond_result.get("success_probability", 0.0)
            result["bonds"] = bond_result.get("bonds", [])
            result["weakest_bond"] = bond_result.get("weakest_bond")
            result["energy"] = bond_result.get("energy", {})
            result["elegance"] = bond_result.get("elegance", {})
        except Exception as e:
            result["error"] = f"Bond prediction failed: {e}"
    else:
        # Fallback: compute energy/elegance directly
        if _compute_chain_energy is not None:
            try:
                energy = _compute_chain_energy(skills=skills, graph=graph)
                result["energy"] = energy
                if _compute_elegance is not None:
                    elegance = _compute_elegance(chain_energy=energy, success_probability=0.5)
                    result["elegance"] = elegance
            except Exception as e:
                result["error"] = f"Energy computation failed: {e}"

    result["orchestrator"] = _detect_orchestrator(skills, graph)
    return result


def get_known_chains() -> list[dict]:
    """Return known chains from recommendations log and training data."""
    chains: list[dict] = []

    # From recommendations log
    if RECOMMENDATIONS_LOG.exists():
        try:
            for line in RECOMMENDATIONS_LOG.read_text().strip().split("\n"):
                if not line:
                    continue
                entry = json.loads(line)
                for rec in entry.get("recommendations", []):
                    if rec.get("rank") == 1:
                        chains.append({
                            "task": entry["task"],
                            "chain": rec["chain"],
                            "confidence": rec.get("confidence", 0),
                            "source": "recommendation_log",
                        })
        except Exception as e:
            logger.debug(f"Failed to read recommendations log: {e}")

    # From chain_miner training data
    training_data = SKILL_LAB_SCRIPTS / "data" / "chains.jsonl"
    if training_data.exists():
        try:
            for line in training_data.read_text().strip().split("\n"):
                if not line:
                    continue
                entry = json.loads(line)
                chains.append({
                    "task": entry.get("request", ""),
                    "chain": entry.get("skills", []),
                    "confidence": 1.0,
                    "source": "training_data",
                })
        except Exception as e:
            logger.debug(f"Failed to read training data: {e}")

    return chains


def get_shadow_status() -> dict:
    """Return shadow-LEGO agreement statistics from cascade shadow log.

    Reads from ~/.pi/assistant/shadow.jsonl (the canonical shadow log
    written by CascadeRunner) filtered to skill-chain-router task.
    Falls back to local shadow.jsonl for backward compatibility.
    """
    entries = []

    # Primary: cascade shadow log (the real one)
    cascade_shadow = Path.home() / ".pi" / "assistant" / "shadow.jsonl"
    if cascade_shadow.exists():
        try:
            for line in cascade_shadow.read_text().strip().split("\n"):
                if not line:
                    continue
                entry = json.loads(line)
                if entry.get("task") == "skill-chain-router":
                    entries.append(entry)
        except Exception as e:
            logger.debug(f"Failed to read cascade shadow log: {e}")

    # Fallback: local shadow log
    if not entries and SHADOW_LOG.exists():
        try:
            for line in SHADOW_LOG.read_text().strip().split("\n"):
                if line:
                    entries.append(json.loads(line))
        except Exception as e:
            logger.debug(f"Failed to read local shadow log: {e}")

    if not entries:
        return {"agreement_rate": None, "status": "no_data", "total": 0}

    total = len(entries)
    agreed = sum(1 for e in entries if e.get("agreed", e.get("agreement", False)))
    rate = round(agreed / total, 3) if total > 0 else 0.0

    status = "CONFIDENT" if rate >= 0.9 else "LEARNING" if rate >= 0.7 else "DIVERGENT"
    return {"agreement_rate": rate, "status": status, "total": total}


def get_status() -> dict:
    """Health check: report which components are available."""
    _ensure_imports()
    components = {
        "scan_soup": _scan_soup is not None,
        "predict_chain": _predict_chain is not None,
        "detect_gaps": _detect_gaps is not None,
        "predict_chain_success": _predict_chain_success is not None,
        "compute_chain_energy": _compute_chain_energy is not None,
        "compute_elegance": _compute_elegance is not None,
        "assistant_classify": _assistant_classify is not None,
        "assistant_validate": _assistant_validate is not None,
        "cascade_runner": _CascadeRunner is not None,
    }
    available = sum(1 for v in components.values() if v)
    total = len(components)

    return {
        "healthy": available >= 3,
        "components": components,
        "available": available,
        "total": total,
        "data_dir": str(DATA_DIR),
        "recommendations_count": _count_lines(RECOMMENDATIONS_LOG),
        "shadow_count": _count_lines(SHADOW_LOG),
    }


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        return sum(1 for line in path.read_text().strip().split("\n") if line)
    except Exception:
        return 0
