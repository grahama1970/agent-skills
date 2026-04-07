#!/usr/bin/env python3
"""
Taxonomy - Extract Federated Taxonomy tags from text.

Classifier extracts Mind/Heart tags; collection vocabularies provide domain tags.
Multi-hop graph traversal uses grounded MITRE taxonomy (CWE pillars, CAPEC,
ATT&CK techniques) instead of LLM-generated bridge attributes.

Heart/Mind Architecture (2026-03-14):
- `mind` and `heart` are ORTHOGONAL dimensions — every call emits BOTH keys.
- `mind` = tactical dimension (Detect, Evade, Exploit, Harden, Isolate, Model,
  Persist, Restore). Applies to ANY text discussing security/defense topics.
- `heart` = emotional dimension (anger, fear, joy, sadness, trust).
  Applies to ANY text with persona/interpersonal content.
- The TEXT content determines which tags apply, NOT the scope.
- Both can be empty lists if the text doesn't match that dimension.

Multi-hop traversal (2026-03-21):
- Bridge attributes (Precision/Resilience/Fragility/Corruption/Loyalty/Stealth)
  REMOVED — they were ungrounded LLM opinions.
- SPARTA scope: traversal uses CWE pillar hierarchy, CIA consequences,
  CAPEC→ATT&CK→SPARTA edges in sparta_relationships.
- Non-SPARTA scope: traversal uses Mind/Heart tag overlap, collection tags,
  and BM25+cosine similarity via /recall.
- `bridge_tags` key kept as empty list for backward compatibility.

Example: a Brandon Bailey lesson about GPS spoofing defence gets:
  mind: ["Detect"]   — he is describing a tactical detection method
  heart: ["trust"]  — his collaborative posture toward the problem
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

import httpx
from loguru import logger

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
            resp = client.post("/list", json={"collection": coll, "limit": 0})
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

try:
    import typer
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "typer", "-q"],
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )
    import typer


# Bridge Attributes — REMOVED (2026-03-21).
# Were ungrounded LLM opinions. Multi-hop traversal now uses grounded MITRE
# taxonomy (CWE pillars, CAPEC→ATT&CK chains, Mind/Heart tag overlap).
# Constant kept as empty set for backward compatibility.
BRIDGE_TAGS: set[str] = set()

# Collection-specific vocabularies
COLLECTION_VOCABULARIES = {
    "lore": {
        "function": {"Catalyst", "Subversion", "Preservation", "Revelation", "Confrontation"},
        "domain": {"Legion", "Imperium", "Chaos", "Primarch", "World"},
        "thematic_weight": {"Betrayal", "Tragedy", "Honor", "Despair"},
        "perspective": {"Frontline", "Political", "Psychological", "Cosmic"},
    },
    "operational": {
        "function": {"Fix", "Optimization", "Refactor", "Hardening", "Debug"},
        "domain": {"Middleware", "Frontend", "Database", "Deployment", "Infrastructure"},
        "thematic_weight": {"Critical", "Technical_Debt", "Security", "Performance"},
        "perspective": {"Architectural", "Operational", "Strategic", "Internal"},
    },
    "sparta": {
        "function": {"Attack", "Defend", "Detect", "Mitigate", "Exploit", "Command", "Navigate", "Telemetry"},
        "domain": {"Network", "Endpoint", "Identity", "Cloud", "Application",
                   "Spacecraft", "Ground_Station", "Uplink", "Downlink", "Payload", "Link_Budget"},
        "thematic_weight": {"Critical", "High", "Medium", "Low"},
        "perspective": {"Offensive", "Defensive", "Compliance", "Risk", "Space_Segment", "Ground_Segment"},
        # Space-specific CWE categories for multi-hop traversal
        "cwe_category": {"MemorySafety", "Cryptography", "SpaceSystems", "ResourceManagement",
                         "Authentication", "InputValidation"},
    },
    "behavioral": {
        "function": {"Mechanism", "Adaptation", "Regulation", "Development", "Pathology"},
        "domain": {"Neuroscience", "Endocrine", "Evolution", "Social", "Clinical"},
        "thematic_weight": {"Aggression", "Stress", "Cooperation", "Cognition", "Emotion"},
        "perspective": {"Biological", "Evolutionary", "Cultural", "Individual", "Population"},
        # Emotional intensity for persona journals - affects weight in multi-hop traversal
        "emotional_intensity": {"Low", "Moderate", "High", "Extreme"},
    },
}

# Bridge keywords — REMOVED (2026-03-21). Were loaded from taxonomy_vocabulary
# for keyword-based bridge attribute extraction. No longer needed.
BRIDGE_KEYWORDS: dict[str, list[str]] = {}

# Tactical tags (SPARTA 8-class taxonomy for Tier 0.5 tactical classification)
# These are the "Mind" tags (Heart/Mind architecture) — apply to ANY text
# discussing security/defense topics, regardless of scope.
TACTICAL_TAGS = {"Detect", "Evade", "Exploit", "Harden", "Isolate", "Model", "Persist", "Restore"}
# Canonical alias — prefer MIND_TAGS in new code
MIND_TAGS = TACTICAL_TAGS

# Control ID → mind tags cache (populated on first lookup per ID)
_control_mind_cache: dict[str, list[str]] = {}

# Memory daemon socket path — shared with /extract-entities and other skills
_MEMORY_SOCKET = os.environ.get(
    "MEMORY_SOCKET",
    f"/run/user/{os.getuid()}/embry/memory.sock",
)


def _parse_mind_field(mind) -> list[str]:
    """Parse mind field from ArangoDB document. Handles list or JSON string."""
    if isinstance(mind, list):
        return [str(t) for t in mind if t]
    if isinstance(mind, str) and mind.startswith("["):
        import ast
        try:
            return [str(t) for t in ast.literal_eval(mind) if t]
        except Exception:
            pass
    return []


def derive_mind_from_control_ids(control_ids: list[str]) -> list[str]:
    """Tier 0: Derive mind tags from pre-extracted control IDs.

    Accepts control IDs already extracted by /extract-entities (flashtext +
    ArangoDB). Looks up each control in sparta_controls via /memory daemon
    to retrieve stored mind tags. Works for all framework types with
    populated mind tags.

    NO regex. Entity extraction is /extract-entities' job, not ours.
    We just look up the mind tags for whatever IDs we're given.
    """
    if not control_ids:
        return []

    # Deduplicate and normalize
    clean_ids = sorted({cid.strip() for cid in control_ids if cid and cid.strip()})
    if not clean_ids:
        return []

    tags: set[str] = set()

    # Check cache first, collect uncached IDs
    uncached: list[str] = []
    for cid in clean_ids:
        if cid in _control_mind_cache:
            tags.update(_control_mind_cache[cid])
        else:
            uncached.append(cid)

    if not uncached:
        return sorted(tags)

    # Batch lookup uncached IDs via /memory daemon
    try:
        transport = httpx.HTTPTransport(uds=_MEMORY_SOCKET)
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=15) as client:
            for cid in uncached:
                resp = client.post("/list", json={
                    "collection": "sparta_controls",
                    "limit": 1,
                    "filters": {"control_id": cid},
                    "return_fields": ["control_id", "mind"],
                })
                resp.raise_for_status()
                docs = resp.json().get("documents", [])
                mind = _parse_mind_field(docs[0].get("mind", [])) if docs else []
                _control_mind_cache[cid] = mind
                tags.update(mind)
    except Exception as e:
        logger.warning("Control ID mind lookup failed: {}", e)

    return sorted(tags)


# Heart tags for BDI/emotional dimension — apply to ANY text with
# persona/interpersonal content, regardless of scope.
HEART_TAGS = {"anger", "fear", "joy", "sadness", "trust"}

# ---------------------------------------------------------------------------
# Tier 0.5 Classifier (DistilBERT multi-label tactical/mind)
# ---------------------------------------------------------------------------
_tactical_classifier = None


def _load_classifier(model_path: str) -> tuple:
    """Load a DistilBERT multi-label classifier + thresholds.

    Returns (pipeline, thresholds_dict) or (None, None) on failure.
    """
    from pathlib import Path as _P
    model_dir = _P(model_path).expanduser()
    if not model_dir.exists():
        logger.debug(f"Classifier model not found at {model_dir}")
        return None, None
    thresholds_file = model_dir / "thresholds.json"
    thresholds = {}
    if thresholds_file.exists():
        thresholds = json.loads(thresholds_file.read_text())
    try:
        from transformers import pipeline as hf_pipeline
        pipe = hf_pipeline("text-classification", model=str(model_dir), top_k=None)
        return pipe, thresholds
    except Exception as e:
        logger.debug(f"Failed to load classifier from {model_dir}: {e}")
        return None, None


def _classify_multilabel(pipe, text: str, thresholds: dict, default_thresh: float = 0.5) -> tuple:
    """Run multi-label classification. Returns (tags, probabilities, max_proba)."""
    results = pipe(text[:512])
    tags, probabilities = [], {}
    for item in results:
        label, score = item["label"], item["score"]
        probabilities[label] = round(score, 4)
        if score >= thresholds.get(label, default_thresh):
            tags.append(label)
    max_proba = max(probabilities.values()) if probabilities else 0.0
    return tags, probabilities, max_proba


def extract_classifier(text: str) -> dict[str, Any] | None:
    """Tier 0.5: Use trained DistilBERT classifier for Mind/tactical tags.

    Returns dict with tactical_tags, confidence, method,
    or None if classifier unavailable.
    """
    global _tactical_classifier

    tactical_model_path = os.environ.get("TAXONOMY_TACTICAL_MODEL_PATH", "")

    if not tactical_model_path:
        return None

    result = {"bridge_tags": [], "tactical_tags": [], "confidence": 0.0, "method": "classifier"}

    if _tactical_classifier is None:
        _tactical_classifier = _load_classifier(tactical_model_path)
    pipe, thresholds = _tactical_classifier
    if pipe is None:
        return None

    tags, probs, max_p = _classify_multilabel(pipe, text, thresholds)
    result["tactical_tags"] = [t for t in tags if t in TACTICAL_TAGS]
    result["tactical_probabilities"] = probs
    result["confidence"] = round(max_p, 4)
    return result


# LLM prompt template
EXTRACTION_PROMPT = """Extract taxonomy tags from this text.

COLLECTION: {collection}
COLLECTION TAGS (pick best match per dimension, or null):
{vocab}

TEXT:
{text}

Return JSON only:
{{"collection_tags": {{"function": "...", "domain": "..."}}, "confidence": 0.8}}"""


def validate_tags(raw: dict[str, Any], collection: str) -> dict[str, Any]:
    """Filter LLM output to known vocabulary - prevents hallucinated tags."""
    vocab = COLLECTION_VOCABULARIES.get(collection, COLLECTION_VOCABULARIES["operational"])
    col_tags = {}
    raw_col = raw.get("collection_tags", {})
    if isinstance(raw_col, dict):
        for dim, allowed in vocab.items():
            val = raw_col.get(dim)
            if isinstance(val, str) and val in allowed:
                col_tags[dim] = val

    return {
        "bridge_tags": [],  # Backward compat — always empty
        "collection_tags": col_tags,
        "confidence": min(1.0, max(0.0, raw.get("confidence", 0.5))),
    }


def extract_llm(text: str, collection: str) -> dict[str, Any]:
    """Use LLM to extract tags via scillm HTTP service, then validate."""
    raw_vocab = COLLECTION_VOCABULARIES.get(collection, {})
    vocab_serializable = {k: list(v) if isinstance(v, set) else v for k, v in raw_vocab.items()}
    vocab_str = json.dumps(vocab_serializable, indent=2)
    prompt = EXTRACTION_PROMPT.format(
        text=text[:3000],
        collection=collection,
        vocab=vocab_str
    )

    scillm_url = os.environ.get("SCILLM_API_BASE", "http://127.0.0.1:4010")
    scillm_key = os.environ.get("SCILLM_PROXY_KEY", os.environ.get("LITELLM_MASTER_KEY", "sk-dev-proxy-123"))
    model = os.environ.get("SCILLM_TAXONOMY_MODEL", "local-text")

    try:
        import httpx
        resp = httpx.post(
            f"{scillm_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {scillm_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 256,
                "temperature": 0.1,
            },
            timeout=30,
        )
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"]
            # Strip markdown code fences if present
            import re
            fenced = re.search(r'```(?:json)?\s*\n?(.*?)```', content, re.DOTALL)
            if fenced:
                content = fenced.group(1).strip()
            # Extract JSON from response
            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('{'):
                    try:
                        raw = json.loads(line)
                        validated = validate_tags(raw, collection)
                        validated["method"] = "llm"
                        return validated
                    except json.JSONDecodeError:
                        continue
            # Try parsing entire content as JSON
            try:
                raw = json.loads(content)
                validated = validate_tags(raw, collection)
                validated["method"] = "llm"
                return validated
            except json.JSONDecodeError:
                pass
    except ImportError:
        pass  # httpx not available
    except Exception as e:
        print(f"LLM extraction failed: {e}", file=sys.stderr)

    # Fallback — no bridge tags, just empty result
    return {
        "bridge_tags": [],
        "collection_tags": {},
        "confidence": 0.3,
        "method": "llm_fallback"
    }


def _extract_heart_tags(text: str) -> list[str]:
    """Keyword-scan the text for heart (BDI/emotional) tags.

    Applies to any text — the content, not the scope, determines relevance.
    Returns a subset of HEART_TAGS that match the text.
    """
    text_lower = text.lower()
    # Simple keyword mapping for each heart tag — deterministic, no LLM needed.
    # Domain knowledge stays minimal here; detailed synonym lists live in ArangoDB.
    _HEART_KEYWORDS: dict[str, list[str]] = {
        "anger":   ["frustrated", "angry", "anger", "resentful", "hostile", "irritated",
                     "bitter", "rage", "blame", "defiant", "furious", "outraged"],
        "fear":    ["anxious", "worried", "uncertain", "threatened", "threat", "cautious",
                     "overwhelmed", "vulnerable", "afraid", "alarming", "alarm", "fear",
                     "danger", "panic", "dread", "terrif"],
        "joy":     ["satisfied", "excited", "proud", "hopeful", "relieved",
                     "happy", "pleased", "confident", "grateful", "joy", "joyful", "delight",
                     "celebrat", "triumph", "elated"],
        "sadness": ["disappointed", "resigned", "exhausted", "regretful",
                     "burned", "fatigued", "loss", "gave up", "sad", "sadness", "grief"],
        "trust":   ["collaborative", "trusting", "trust", "loyal", "respectful", "allied",
                     "rapport", "bonding", "cooperative", "team", "partner", "together",
                     "rely", "reliable", "depend", "faithful"],
    }
    matched = []
    for tag, keywords in _HEART_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            matched.append(tag)
    return matched


def extract_taxonomy(
    text: str,
    collection: str = "operational",
    fast: bool = False,
    control_ids: list[str] | None = None,
) -> dict[str, Any]:
    """
    Extract taxonomy tags from text.

    Args:
        text: Content to analyze
        collection: Target collection (lore, operational, sparta, sparta_qra, behavioral)
        fast: Use keyword extraction only (no LLM)
        control_ids: Pre-extracted control IDs from /extract-entities (flashtext).
            When provided, Tier 0 looks up mind tags for these IDs directly.
            When None, Tier 0 is skipped (no bespoke regex — entity extraction
            is /extract-entities' job).

    Returns:
        dict with bridge_tags, collection_tags, confidence, worth_remembering,
        mind (list), heart (list).

        ``mind`` and ``heart`` are ALWAYS present as independent dimensions:
        - ``mind``: tactical tags (Detect, Evade, …) — from classifier/LLM
        - ``heart``: BDI/emotional tags — from keyword scan of text content
        Both can be empty lists; neither is gated on scope.
        The legacy ``tactical_tags`` key is kept as a backward-compat alias.
    """
    # Tier 0: Look up mind tags for pre-extracted control IDs (~5ms)
    # Control IDs come from /extract-entities (flashtext + ArangoDB).
    # We do NOT re-extract entities here — no regex.
    ref_mind = derive_mind_from_control_ids(control_ids or [])

    if fast or os.environ.get("TAXONOMY_FAST_MODE") == "1":
        result = {
            "bridge_tags": [],
            "collection_tags": {},
            "confidence": 0.3,
            "method": "fast"
        }
        if ref_mind:
            result["mind"] = ref_mind
            result["method"] = "fast+refs"
    else:

        # Tier 0.5: Try trained Mind/tactical classifier (~3ms, free)
        # Sensai Cascade: classifier only contributes when near-certain (≥0.95).
        # Below that, the system is either deterministic (T0 control ID lookup)
        # or grey zone (T2 LLM decides).
        clf_min_confidence = max(
            0.95,
            float(os.environ.get("TAXONOMY_CLASSIFIER_THRESHOLD", "0.95")),
        )
        clf_result = None
        try:
            clf_result = extract_classifier(text)
        except Exception as e:
            logger.debug(f"Tier 0.5 classifier failed: {e}")

        if clf_result and clf_result["confidence"] >= clf_min_confidence:
            result = {
                "bridge_tags": [],
                "collection_tags": {},
                "confidence": clf_result["confidence"],
                "method": "classifier",
            }
            if clf_result.get("tactical_tags"):
                _tactical = clf_result["tactical_tags"]
                # Merge: union of deterministic refs + classifier output
                if ref_mind:
                    _tactical = sorted(set(_tactical) | set(ref_mind))
                    result["method"] = "refs+classifier"
                result["mind"] = _tactical
                result["tactical_tags"] = _tactical
            elif ref_mind:
                result["mind"] = ref_mind
                result["tactical_tags"] = ref_mind
                result["method"] = "refs"
        else:
            # Fall through to Tier 2: LLM for grey zone.
            # Classifier below threshold is IGNORED — Sensai Cascade policy.
            result = extract_llm(text, collection)
            # Only merge T0 deterministic refs (never low-confidence classifier)
            if ref_mind:
                result["mind"] = ref_mind
                result["tactical_tags"] = ref_mind
                result["method"] = result.get("method", "llm") + "+refs"

    # `mind` key: always present; empty list if no tactical tags found.
    # If Tier 0 refs found tags but they weren't merged yet, apply them now.
    if "mind" not in result:
        result["mind"] = ref_mind if ref_mind else result.get("tactical_tags", [])
    elif ref_mind and not set(ref_mind).issubset(set(result.get("mind", []))):
        result["mind"] = sorted(set(result["mind"]) | set(ref_mind))
    # Keep tactical_tags as compat alias pointing to the same list.
    result["tactical_tags"] = result["mind"]

    # `heart` key: always present; derived from text content, not scope.
    # Even if a classifier is trained for heart tags in the future, the
    # keyword scan provides a baseline that is always populated.
    result["heart"] = _extract_heart_tags(text)

    # Document is worth remembering if it has meaningful tags in any dimension
    result["worth_remembering"] = (
        len(result.get("collection_tags", {})) > 0 or
        len(result["mind"]) > 0 or
        len(result["heart"]) > 0
    )

    return result


cli = typer.Typer(help="Taxonomy - Extract Federated Taxonomy tags for multi-hop graph traversal.")


@cli.command()
def extract(
    text: Optional[str] = typer.Option(None, "-t", "--text", help="Text to analyze"),
    file: Optional[Path] = typer.Option(None, "-f", "--file", help="File to read"),
    collection: str = typer.Option("operational", "-c", "--collection", help="Collection type: lore, operational, sparta, behavioral"),
    bridges_only: bool = typer.Option(False, "-b", "--bridges-only", help="Only output bridge tags"),
    fast: bool = typer.Option(False, "--fast", help="Use keyword extraction only (no LLM)"),
    control_ids_str: Optional[str] = typer.Option(None, "--control-ids", help="Comma-separated control IDs from /extract-entities"),
):
    """Extract taxonomy tags from text."""
    # Get text content
    if file:
        text = file.read_text()[:5000]
    elif not text:
        print('{"error": "No text provided"}', file=sys.stderr)
        raise SystemExit(1)

    # Parse control IDs if provided
    ids = [c.strip() for c in control_ids_str.split(",") if c.strip()] if control_ids_str else None

    # Extract
    result = extract_taxonomy(text, collection, fast, control_ids=ids)

    # Output
    if bridges_only:
        print(",".join(result["bridge_tags"]))
    else:
        print(json.dumps(result, indent=2))


@cli.command()
def validate(
    tags: Optional[str] = typer.Option(None, "-t", "--tags", help="JSON string with tags to validate"),
    file: Optional[Path] = typer.Option(None, "-f", "--file", help="JSON file with tags"),
    collection: str = typer.Option("operational", "-c", "--collection", help="Collection type: lore, operational, sparta, behavioral"),
):
    """Validate tags against known vocabulary."""
    if file:
        raw = json.loads(file.read_text())
    elif tags:
        raw = json.loads(tags)
    else:
        print('{"error": "No tags provided"}', file=sys.stderr)
        raise SystemExit(1)

    result = validate_tags(raw, collection)
    print(json.dumps(result, indent=2))


@cli.command()
def vocabulary():
    """Show all allowed vocabulary values."""
    output = {
        "bridge_tags": [],  # Removed — backward compat only
        "mind_tags": sorted(MIND_TAGS),
        "heart_tags": sorted(HEART_TAGS),
        "collections": {}
    }
    for coll, vocab in COLLECTION_VOCABULARIES.items():
        output["collections"][coll] = {k: list(v) for k, v in vocab.items()}

    print(json.dumps(output, indent=2))


@cli.command("validate-expansion")
def validate_expansion(
    proposal_key: Optional[str] = typer.Option(None, "-k", "--proposal-key", help="Specific proposal key to validate"),
    all_pending: bool = typer.Option(False, "--all-pending", help="Validate all pending proposals"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Check but don't apply"),
):
    """Cross-collection validation for vocabulary expansion proposals.

    Checks proposed terms against non-SPARTA collections to ensure they don't
    cause false positives. Auto-approves if false_positive_rate < 20%.
    """
    if not proposal_key and not all_pending:
        print('{"error": "Specify --proposal-key or --all-pending"}', file=sys.stderr)
        raise SystemExit(1)

    # Fetch proposals via /memory sample
    try:
        if proposal_key:
            data = _memory_cmd(["sample", "--collection", "taxonomy_vocabulary_proposals",
                                "--limit", "1", "--filter", f"doc._key == '{proposal_key}'"])
            proposals = data.get("items", [])
        else:
            data = _memory_cmd(["sample", "--collection", "taxonomy_vocabulary_proposals",
                                "--limit", "500", "--filter", "doc.status == 'pending'"])
            proposals = data.get("items", [])
    except RuntimeError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        raise SystemExit(1)

    if not proposals:
        print(json.dumps({"message": "No proposals to validate", "count": 0}))
        return

    # Sample non-SPARTA docs for cross-check
    try:
        sample_data = _memory_cmd(["sample", "--collection", "lessons", "--limit", "100",
                                    "--random", "--fields", "text,bridge_attributes,scope"])
        cross_docs = [d for d in sample_data.get("items", [])
                      if d.get("scope", "") not in ("sparta", "SPARTA")
                      and len(d.get("text", "")) > 50]
    except RuntimeError:
        cross_docs = []

    results = []
    for prop in proposals:
        proposed_terms = prop.get("proposed_additions", [])
        scope = prop.get("scope", "")
        vocab_type = prop.get("vocab_type", "")

        false_positives = 0
        total_checked = len(cross_docs)

        for doc in cross_docs:
            text = (doc.get("text", "") or "").lower()
            bridges = doc.get("bridge_attributes", []) or []
            for term in proposed_terms:
                if term in text:
                    if scope not in bridges:
                        false_positives += 1
                    break

        fp_rate = false_positives / max(total_checked, 1)
        evidence_count = prop.get("evidence", {}).get("warn_count", 0)

        if evidence_count >= 10 and fp_rate < 0.20:
            decision = "approved"
        elif evidence_count < 5 or fp_rate >= 0.20:
            decision = "rejected"
        else:
            decision = "deferred"

        result = {
            "proposal_key": prop.get("_key"),
            "vocab_type": vocab_type,
            "scope": scope,
            "proposed_terms": proposed_terms,
            "false_positive_rate": round(fp_rate, 3),
            "evidence_count": evidence_count,
            "total_checked": total_checked,
            "decision": decision,
        }
        results.append(result)

        # Apply approved proposals via /memory tag
        if not dry_run:
            import time as _time
            try:
                if decision == "approved":
                    # Fetch current vocabulary doc
                    vocab_key = f"{vocab_type}__{scope}"
                    try:
                        vocab_data = _memory_cmd(["sample", "--collection", "taxonomy_vocabulary",
                                                   "--limit", "1", "--filter", f"doc._key == '{vocab_key}'"])
                        vocab_doc = (vocab_data.get("items") or [None])[0]
                    except RuntimeError:
                        vocab_doc = None

                    if vocab_doc:
                        current_terms = set(vocab_doc.get("terms", []))
                        new_terms = [t for t in proposed_terms if t not in current_terms]
                        if new_terms:
                            updated_terms = list(current_terms | set(new_terms))
                            new_version = vocab_doc.get("version", 1) + 1
                            _memory_cmd(["tag", "--collection", "taxonomy_vocabulary",
                                          "--key", vocab_key, "--field", "terms",
                                          "--tags", json.dumps(updated_terms), "--mode", "replace"])
                            version_file = Path("/tmp/taxonomy_vocab_version.txt")
                            version_file.write_text(str(new_version))
                            result["applied_terms"] = new_terms

                # Update proposal status
                _memory_cmd(["tag", "--collection", "taxonomy_vocabulary_proposals",
                              "--key", prop["_key"], "--field", "status",
                              "--tags", json.dumps([decision]), "--mode", "replace"])
            except Exception as e:
                result["apply_error"] = str(e)

    print(json.dumps({"results": results, "total": len(results)}, indent=2))


if __name__ == "__main__":
    cli()
