"""Cascade runner for taxonomy quality assessment.

Sets up the three-tier cascade: T0 heuristic → T1.5 classifier → T2 Brandon.
Each tier assesses whether taxonomy tags on a document are CORRECT.

Heart/Mind field conventions:
- `mind`  (8 SPARTA tactical tags: Detect, Evade, Exploit, Harden, Isolate,
           Model, Persist, Restore) lives on `sparta_qra` documents.
- `heart` (6 emotional tags: anger, fear, joy, neutral, sadness, trust)
           lives on `lessons` documents.

Input documents should supply the relevant field under the key that matches
their collection: pass `mind` for QRAs, `heart` for lessons. The cascade
reads whichever field is present.

Inputs: document dict with text, mind|heart list, collection_tags, _collection.
Outputs: grade (CORRECT/MISTAGGED/MISSING/HALLUCINATED) + action.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

import os
import subprocess

import config

# Add skills dir to path for imports
SKILLS_DIR = Path(__file__).resolve().parents[1]
if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))

# Removed: memory accessed via httpx to Unix socket (see _memory_cmd)
from common.cascade import CascadeRunner, TierDef, TierResult  # noqa: E402


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

_use_gateway = os.environ.get("TAXONOMY_USE_GATEWAY", "1") == "1"
_gateway_available = False
if _use_gateway:
    try:
        _assistant_dir = str(SKILLS_DIR / "assistant")
        if _assistant_dir not in sys.path:
            sys.path.insert(0, _assistant_dir)
        from assistant import validate as _gw_validate
        _gateway_available = True
    except ImportError:
        _gateway_available = False


# --- Constants ---

GRADES = {"CORRECT", "MISTAGGED", "MISSING", "HALLUCINATED"}
ACTIONS = {"keep", "re-extract", "remove", "flag"}

# Import vocabulary from taxonomy skill
try:
    from taxonomy.taxonomy import MIND_TAGS, HEART_TAGS, BRIDGE_KEYWORDS
    # BRIDGE_TAGS kept as legacy alias — callers should prefer MIND_TAGS/HEART_TAGS
    BRIDGE_TAGS = MIND_TAGS | HEART_TAGS
except ImportError:
    MIND_TAGS = {"Detect", "Evade", "Exploit", "Harden", "Isolate", "Model", "Persist", "Restore"}
    HEART_TAGS = {"anger", "fear", "joy", "sadness", "trust"}
    BRIDGE_TAGS = MIND_TAGS | HEART_TAGS
    BRIDGE_KEYWORDS = {}

# Cache for ArangoDB-loaded keywords
_arango_bridge_keywords: dict | None = None


def _resolve_tags_field(input_data: dict) -> tuple[list, str]:
    """Return (tags_list, field_name) from input, honouring Heart/Mind convention.

    Checks for `mind` (QRAs) then `heart` (lessons) then the legacy
    `bridge_attributes` key.  Returns the first non-empty value found,
    plus the field name that was used.
    """
    for field in ("mind", "heart", "bridge_attributes"):
        val = input_data.get(field)
        if val is not None:
            return (val if isinstance(val, list) else [val]), field
    return [], "mind"


def _valid_tags_for_field(field: str) -> set[str]:
    """Return the valid vocabulary set for the given field name."""
    if field == "heart":
        return HEART_TAGS
    # mind or legacy bridge_attributes → MIND_TAGS (SPARTA tactical)
    return MIND_TAGS


def _load_bridge_keywords() -> dict:
    """Load BRIDGE_KEYWORDS from /memory recall, fallback to hardcoded."""
    global _arango_bridge_keywords
    if _arango_bridge_keywords is not None:
        return _arango_bridge_keywords

    try:
        result = _memory_cmd([
            "recall", "--q", "taxonomy_vocabulary bridge_keywords",
            "--scope", "operational", "--k", "20",
        ])
        items = result.get("items", result.get("results", []))
        loaded = {}
        for doc in items:
            scope = doc.get("scope")
            terms = doc.get("terms", doc.get("solution", "").split(","))
            if scope and terms:
                loaded[scope] = terms if isinstance(terms, list) else [t.strip() for t in terms]
        if loaded:
            _arango_bridge_keywords = loaded
            logger.info(f"Cascade: loaded {len(loaded)} bridge_keywords from /memory")
            return loaded
    except Exception as e:
        logger.debug(f"Memory bridge_keywords unavailable in cascade: {e}")

    _arango_bridge_keywords = BRIDGE_KEYWORDS
    return BRIDGE_KEYWORDS


def _keyword_overlap_score(text: str, bridges: list[str]) -> float:
    """Compute keyword overlap between document text and bridge indicator words.

    Returns fraction of assigned bridges that have keyword evidence in text.
    Score of 0.0 means no keywords found for any assigned bridge.
    """
    if not bridges or not text:
        return 0.0

    effective_kw = _load_bridge_keywords()
    if not effective_kw:
        return 0.5  # Can't assess without keywords

    text_lower = text.lower()
    hits = 0
    for bridge in bridges:
        patterns = effective_kw.get(bridge, [])
        if any(p in text_lower for p in patterns):
            hits += 1

    return hits / len(bridges)


def tier0_heuristic(input_data: Dict[str, Any], **kw) -> Optional[TierResult]:
    """T0: Vocabulary check + keyword coherence score.

    Fast, deterministic. Catches obvious errors:
    - Invalid tags not in the correct vocabulary (MIND_TAGS for QRAs, HEART_TAGS
      for lessons, determined by whichever field — `mind` or `heart` — is present)
    - No keyword evidence for assigned tags (coherence < threshold)
    - Missing tags when keywords clearly present
    """
    text = input_data.get("text", "")
    tags, field_used = _resolve_tags_field(input_data)
    valid_vocab = _valid_tags_for_field(field_used)

    if not tags and not text:
        return TierResult(
            result={"grade": "MISSING", "action": "flag",
                    "field": field_used, "reason": f"no text or {field_used} tags"},
            confidence=0.95,
            source="heuristic",
        )

    # Check vocabulary violations
    invalid = [t for t in tags if t not in valid_vocab]
    if invalid:
        return TierResult(
            result={
                "grade": "HALLUCINATED",
                "action": "remove",
                "field": field_used,
                "invalid_tags": invalid,
                "reason": f"Invalid {field_used} terms (not in {sorted(valid_vocab)}): {invalid}",
            },
            confidence=0.99,
            source="heuristic",
        )

    if not tags and text:
        # Check if keywords suggest tags should exist
        effective_kw = _load_bridge_keywords()
        keyword_tags = []
        text_lower = text.lower()
        for tag, patterns in effective_kw.items():
            if tag in valid_vocab and any(p in text_lower for p in patterns):
                keyword_tags.append(tag)
        if keyword_tags:
            return TierResult(
                result={
                    "grade": "MISSING",
                    "action": "re-extract",
                    "field": field_used,
                    "suggested_tags": keyword_tags,
                    "reason": f"Keywords suggest {field_used}: {keyword_tags}",
                },
                confidence=0.70,
                source="heuristic",
            )
        return TierResult(
            result={"grade": "CORRECT", "action": "keep",
                    "field": field_used, "reason": f"no {field_used} tags, no keywords"},
            confidence=0.85,
            source="heuristic",
        )

    # Coherence check
    score = _keyword_overlap_score(text, tags)
    if score >= config.COHERENCE_THRESHOLD:
        return TierResult(
            result={
                "grade": "CORRECT",
                "action": "keep",
                "field": field_used,
                "coherence_score": round(score, 3),
            },
            confidence=min(0.60 + score * 0.35, 0.95),
            source="heuristic",
        )

    # Low coherence — likely mistagged
    return TierResult(
        result={
            "grade": "MISTAGGED",
            "action": "flag",
            "field": field_used,
            "coherence_score": round(score, 3),
            "reason": f"Low keyword coherence for {field_used} ({score:.2f})",
        },
        confidence=0.50,
        source="heuristic",
    )


def _find_model_dir() -> Optional[Path]:
    """Find trained taxonomy-assessor model (create-gpt or local state)."""
    candidates = [
        SKILLS_DIR / "create-gpt" / "models" / "taxonomy-assessor" / "gguf",
        SKILLS_DIR / "create-gpt" / "models" / "taxonomy-assessor" / "sft",
        config.STATE_DIR / "models" / "taxonomy-assessor",
    ]
    for path in candidates:
        if path.exists() and any(path.iterdir()):
            return path
    return None


def tier15_classifier(input_data: Dict[str, Any], **kw) -> Optional[TierResult]:
    """T1.5: Trained classifier/GPT inference.

    Returns None if no trained model is available (skips tier).
    Uses create-gpt's infer module when a GGUF or SFT model exists.
    """
    model_dir = _find_model_dir()
    if not model_dir:
        return None

    text = input_data.get("text", "")[:3000]
    tags, field_used = _resolve_tags_field(input_data)
    collection_tags = input_data.get("collection_tags", {})

    input_text = json.dumps({
        "text": text,
        field_used: tags,
        "collection_tags": collection_tags,
    })

    try:
        infer_script = SKILLS_DIR / "create-gpt" / "scripts" / "infer.py"
        if not infer_script.exists():
            logger.debug("create-gpt infer.py not found at {}", infer_script)
            return None

        # Use create-gpt's infer module
        import importlib.util
        spec = importlib.util.spec_from_file_location("infer", infer_script)
        infer_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(infer_mod)

        # Determine mode from model dir
        if model_dir.name == "gguf":
            result = infer_mod.infer_gguf("taxonomy-assessor", input_text)
        else:
            result = infer_mod.infer_hf("taxonomy-assessor", input_text)

        output = result.get("output", {})
        grade = output.get("grade", "CORRECT")
        if grade not in GRADES:
            grade = "CORRECT"
        confidence = result.get("confidence", 0.5)

        return TierResult(
            result={
                "grade": grade,
                "correct_tags": output.get("correct_tags", output.get("correct_bridges", tags)),
                "field": field_used,
                "action": output.get("action", "keep"),
                "reasoning": output.get("reasoning", ""),
            },
            confidence=confidence,
            source="classifier",
        )

    except Exception as e:
        logger.debug("Classifier inference failed: {}", e)
        return None


def tier2_brandon_teacher(input_data: Dict[str, Any], **kw) -> Optional[TierResult]:
    """T2: Brandon via scillm. Authoritative teacher assessment.

    Stores every judgment to training_labels.jsonl for future classifier training.
    """
    text = input_data.get("text", "")[:3000]
    tags, field_used = _resolve_tags_field(input_data)
    valid_vocab = _valid_tags_for_field(field_used)
    doc_key = input_data.get("_key", input_data.get("doc_key", "unknown"))
    collection_tags = input_data.get("collection_tags", {})

    prompt = f"""You are Brandon Bailey, a taxonomy quality assessor. Evaluate whether
the `{field_used}` tags assigned to this document are CORRECT.

VALID TAGS FOR `{field_used}`: {', '.join(sorted(valid_vocab))}

DOCUMENT TEXT (excerpt):
{text}

ASSIGNED `{field_used}` TAGS: {tags}
ASSIGNED COLLECTION TAGS: {json.dumps(collection_tags)}

Assess the taxonomy quality. Return JSON only:
{{
    "grade": "CORRECT" | "MISTAGGED" | "MISSING" | "HALLUCINATED",
    "correct_tags": ["list of what `{field_used}` tags SHOULD be assigned"],
    "reasoning": "brief explanation",
    "confidence": 0.0-1.0,
    "action": "keep" | "re-extract" | "remove" | "flag"
}}"""

    # --- Gateway path: try cascade first ---
    if _gateway_available:
        try:
            gw_result = _gw_validate(
                input_data={"text": text, field_used: tags},
                task="taxonomy-assessor",
            )
            if gw_result and gw_result.result:
                gw_grade = gw_result.result.get("grade", "CORRECT")
                if gw_grade in GRADES:
                    gw_action = gw_result.result.get("action", "keep")
                    if gw_action not in ACTIONS:
                        gw_action = "keep"
                    label = {
                        "doc_key": doc_key,
                        "field": field_used,
                        "existing_tags": tags,
                        "grade": gw_grade,
                        "correct_tags": gw_result.result.get("correct_tags",
                                        gw_result.result.get("correct_bridges", tags)),
                        "reasoning": gw_result.result.get("reasoning", ""),
                        "confidence": gw_result.confidence,
                        "action": gw_action,
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    }
                    _store_training_label(label)
                    return TierResult(result=label, confidence=gw_result.confidence, source="gateway_cascade")
        except Exception as e:
            logger.debug("Gateway cascade failed, falling back to direct scillm: {}", e)

    # --- Direct scillm path (fallback) ---
    try:
        from scillm.batch import quick_completion
        raw = quick_completion(
            prompt=prompt,
            json_mode=True,
            max_tokens=512,
            temperature=0.1,
            system="You are Brandon Bailey, an expert taxonomy quality assessor. Be precise and critical.",
        )

        # Parse response
        result = json.loads(raw)
        grade = result.get("grade", "CORRECT")
        if grade not in GRADES:
            grade = "CORRECT"
        action = result.get("action", "keep")
        if action not in ACTIONS:
            action = "keep"

        # Store training label
        label = {
            "doc_key": doc_key,
            "field": field_used,
            "existing_tags": tags,
            "grade": grade,
            "correct_tags": result.get("correct_tags", result.get("correct_bridges", tags)),
            "reasoning": result.get("reasoning", ""),
            "confidence": result.get("confidence", 0.9),
            "action": action,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        _store_training_label(label)

        return TierResult(
            result=label,
            confidence=result.get("confidence", 0.9),
            source="brandon_teacher",
        )

    except ImportError:
        logger.warning("scillm not available for Brandon teacher assessment")
        return None
    except json.JSONDecodeError as e:
        logger.error("Failed to parse Brandon response: {}", e)
        return None
    except Exception as e:
        logger.error("Brandon teacher failed: {}", e)
        return None


def _store_training_label(label: Dict[str, Any]) -> None:
    """Append a training label to training_labels.jsonl."""
    try:
        config.TRAINING_LABELS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(config.TRAINING_LABELS_FILE, "a") as f:
            f.write(json.dumps(label, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error("Failed to store training label: {}", e)


def build_taxonomy_cascade() -> CascadeRunner:
    """Build the T0 → T1.5 → T2 cascade for taxonomy quality assessment."""
    return CascadeRunner(
        tiers=[
            TierDef(
                tier=0,
                name="heuristic",
                fn=tier0_heuristic,
                threshold=config.T0_CONFIDENCE_THRESHOLD,
            ),
            TierDef(
                tier=1.5,
                name="classifier",
                fn=tier15_classifier,
                threshold=config.T15_CONFIDENCE_THRESHOLD,
                shadow_mode=True,  # Always compare with teacher when available
            ),
            TierDef(
                tier=2,
                name="brandon_teacher",
                fn=tier2_brandon_teacher,
                is_teacher=True,
            ),
        ],
        shadow_file=config.SHADOW_FILE,
        metrics_file=config.METRICS_FILE,
    )


def assess_document_taxonomy(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Main entry: run document through cascade, return grade + action.

    Args:
        doc: dict with keys: text, _key, collection_tags, and ONE of:
             - `mind`  (list of SPARTA tactical tags) for `sparta_qra` docs
             - `heart` (list of BDI tags) for `lessons` docs
             The legacy key `bridge_attributes` is accepted as a fallback.

    Returns:
        dict with grade, action, confidence, tier_used, field (mind|heart), etc.
    """
    cascade = build_taxonomy_cascade()
    result = cascade.run(
        input_data=doc,
        task="taxonomy-assessor",
        scope="brandon_bailey",
    )

    return {
        "grade": result.result.get("grade", "CORRECT"),
        "action": result.result.get("action", "keep"),
        "confidence": result.confidence,
        "tier_used": result.tier,
        "source": result.source,
        "details": result.result,
    }
