"""Tier 0 probes: Heuristic taxonomy quality checks.

P01: null-tag-gc    — Find docs with null/empty `mind` (sparta_qra) or `heart` (lessons)
P02: vocabulary-violation — `mind`/`heart` tags not in their respective valid sets
P03: text-tag-coherence   — Keyword overlap score for `mind`/`heart` tags
P04: collection-tag-violation — collection_tags not in vocabularies
P05: stale-taxonomy — Documents with old taxonomy_updated_at

Heart/Mind vocabulary:
- `mind` on sparta_qra  → MIND_TAGS (8 SPARTA tactical tags)
- `heart` on lessons    → HEART_TAGS (5 BDI tags)

All T0 probes are instant, deterministic, and some are auto-fixable.
"""
from __future__ import annotations
import os

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from loguru import logger

# Add parent for config import
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from probes import ProbeResult, ProbeStatus, register_probe

# Import vocabulary
SKILLS_DIR = Path(__file__).resolve().parents[2]
if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))

try:
    from taxonomy.taxonomy import MIND_TAGS, HEART_TAGS, BRIDGE_KEYWORDS, COLLECTION_VOCABULARIES
    # Legacy alias — probes use MIND_TAGS / HEART_TAGS directly
    BRIDGE_TAGS = MIND_TAGS | HEART_TAGS
except ImportError:
    MIND_TAGS = {"Detect", "Evade", "Exploit", "Harden", "Isolate", "Model", "Persist", "Restore"}
    HEART_TAGS = {"anger", "fear", "joy", "sadness", "trust"}
    BRIDGE_TAGS = MIND_TAGS | HEART_TAGS
    BRIDGE_KEYWORDS = {}
    COLLECTION_VOCABULARIES = {}

# Removed: memory accessed via httpx to Unix socket (see _memory_cmd)
# Cache for memory-loaded keywords (loaded once at probe startup)
_cached_bridge_keywords: dict | None = None


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
            resp = client.post("/query", json={"aql": f"RETURN LENGTH({coll})", "bind_vars": {}})
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

def _load_bridge_keywords_from_memory() -> dict:
    """Load BRIDGE_KEYWORDS from memory taxonomy_vocabulary, fallback to hardcoded."""
    global _cached_bridge_keywords
    if _cached_bridge_keywords is not None:
        return _cached_bridge_keywords

    try:
        results = _memory_cmd([
            "sample", "--collection", "taxonomy_vocabulary",
            "--filter", "vocab_type=bridge_keywords",
            "--limit", "50",
        ])
        docs = results if isinstance(results, list) else results.get("results", [])
        loaded = {}
        for doc in docs:
            scope = doc.get("scope")
            terms = doc.get("terms", [])
            if scope and terms:
                loaded[scope] = terms
        if loaded:
            _cached_bridge_keywords = loaded
            logger.info(f"Loaded {len(loaded)} bridge_keywords from memory")
            return loaded
    except Exception as e:
        logger.debug(f"Memory bridge_keywords load unavailable: {e}")

    _cached_bridge_keywords = BRIDGE_KEYWORDS
    return BRIDGE_KEYWORDS


def _get_effective_bridge_keywords() -> dict:
    """Get bridge keywords (memory first, fallback to hardcoded)."""
    return _load_bridge_keywords_from_memory()


@register_probe("P01", "null-tag-gc", tier=1, auto_fixable=True)
def probe_null_tag_gc(autofix: bool = False) -> ProbeResult:
    """Find docs with null/empty taxonomy tags.

    - sparta_qra: checks the `mind` field (8 SPARTA tactical tags)
    - lessons:    checks the `heart` field (5 BDI tags)
    """
    try:
        # Check `mind` on sparta_qra
        qra_results = _memory_cmd([
            "sample", "--collection", "sparta_qra",
            "--filter", "mind=null",
            "--limit", "500",
        ])
        qra_null = qra_results if isinstance(qra_results, list) else qra_results.get("results", [])
        qra_null = [d for d in qra_null if len(d.get("text", d.get("question", ""))) > 50]

        # Check `heart` on lessons
        lesson_results = _memory_cmd([
            "sample", "--collection", "lessons",
            "--filter", "heart=null",
            "--limit", "500",
        ])
        lesson_null = lesson_results if isinstance(lesson_results, list) else lesson_results.get("results", [])
        lesson_null = [d for d in lesson_null if len(d.get("text", "")) > 50]

        total = len(qra_null) + len(lesson_null)

        if total == 0:
            return ProbeResult(
                probe_id="P01", name="null-tag-gc", tier=1,
                status=ProbeStatus.PASS,
                message="No docs with missing `mind` (QRAs) or `heart` (lessons) tags",
            )

        if autofix and total > 0:
            fixed_qra = _autofix_null_tags(qra_null[:25], collection="sparta_qra", field="mind")
            fixed_lessons = _autofix_null_tags(lesson_null[:25], collection="lessons", field="heart")
            fixed = fixed_qra + fixed_lessons
            return ProbeResult(
                probe_id="P01", name="null-tag-gc", tier=1,
                status=ProbeStatus.FIXED,
                message=f"Fixed {fixed}/{total} docs (QRA mind:{fixed_qra}, lessons heart:{fixed_lessons})",
                details={"qra_null": len(qra_null), "lesson_null": len(lesson_null), "fixed": fixed},
                auto_fixable=True, fix_applied=True,
            )

        return ProbeResult(
            probe_id="P01", name="null-tag-gc", tier=1,
            status=ProbeStatus.WARN,
            message=f"{total} docs with null tags (QRA `mind`:{len(qra_null)}, lessons `heart`:{len(lesson_null)})",
            details={"qra_null_mind": len(qra_null), "lesson_null_heart": len(lesson_null), "total": total},
            auto_fixable=True,
        )
    except Exception as e:
        return ProbeResult(
            probe_id="P01", name="null-tag-gc", tier=1,
            status=ProbeStatus.FAIL, message=f"Query failed: {e}",
        )


def _autofix_null_tags(docs: list[dict], collection: str, field: str) -> int:
    """Fix null mind/heart tags using keyword extraction via /memory."""
    try:
        from taxonomy.taxonomy import extract_keywords
    except ImportError:
        return 0

    fixed = 0
    for doc in docs:
        try:
            text = doc.get("text", doc.get("question", ""))
            if not text:
                continue
            tags = extract_keywords(text)
            if tags:
                _memory_cmd([
                    "update", "--collection", collection,
                    "--key", doc["_key"],
                    "--data", json.dumps({
                        field: tags,
                        "taxonomy_method": "keyword_autofix",
                        "taxonomy_updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    }),
                ])
                fixed += 1
        except Exception as e:
            logger.debug("Failed to fix {} {}: {}", collection, doc.get("_key", "?"), e)
    return fixed


@register_probe("P02", "vocabulary-violation", tier=1, auto_fixable=True)
def probe_vocabulary_violation(autofix: bool = False) -> ProbeResult:
    """Check `mind` (sparta_qra) and `heart` (lessons) tags against their vocabularies.

    - MIND_TAGS: Detect, Evade, Exploit, Harden, Isolate, Model, Persist, Restore
    - HEART_TAGS: anger, fear, joy, sadness, trust
    """
    try:
        violations: list[dict] = []

        # --- QRAs: check `mind` field ---
        qra_results = _memory_cmd([
            "sample", "--collection", "sparta_qra",
            "--filter", "mind!=null",
            "--limit", "500",
        ])
        qra_docs = qra_results if isinstance(qra_results, list) else qra_results.get("results", [])
        for doc in qra_docs:
            tags = doc.get("mind", [])
            if not tags:
                continue
            invalid = [t for t in tags if t not in MIND_TAGS]
            if invalid:
                violations.append({
                    "_key": doc["_key"],
                    "collection": "sparta_qra",
                    "field": "mind",
                    "tags": tags,
                    "invalid": invalid,
                })

        # --- Lessons: check `heart` field ---
        lesson_results = _memory_cmd([
            "sample", "--collection", "lessons",
            "--filter", "heart!=null",
            "--limit", "500",
        ])
        lesson_docs = lesson_results if isinstance(lesson_results, list) else lesson_results.get("results", [])
        for doc in lesson_docs:
            tags = doc.get("heart", [])
            if not tags:
                continue
            invalid = [t for t in tags if t not in HEART_TAGS]
            if invalid:
                violations.append({
                    "_key": doc["_key"],
                    "collection": "lessons",
                    "field": "heart",
                    "tags": tags,
                    "invalid": invalid,
                })

        count = len(violations)
        if count == 0:
            return ProbeResult(
                probe_id="P02", name="vocabulary-violation", tier=1,
                status=ProbeStatus.PASS,
                message="All `mind` (QRAs) and `heart` (lessons) tags are valid vocabulary",
            )

        all_invalid = set()
        for v in violations:
            all_invalid.update(v.get("invalid", []))

        if autofix:
            fixed = _autofix_vocab_violations(violations)
            return ProbeResult(
                probe_id="P02", name="vocabulary-violation", tier=1,
                status=ProbeStatus.FIXED,
                message=f"Removed invalid terms from {fixed}/{count} documents: {all_invalid}",
                details={"total": count, "fixed": fixed, "invalid_terms": list(all_invalid)},
                auto_fixable=True, fix_applied=True,
            )

        return ProbeResult(
            probe_id="P02", name="vocabulary-violation", tier=1,
            status=ProbeStatus.WARN,
            message=f"{count} docs with invalid tags: {sorted(all_invalid)}",
            details={"count": count, "invalid_terms": list(all_invalid),
                     "violations": violations[:20]},
            auto_fixable=True,
        )
    except Exception as e:
        return ProbeResult(
            probe_id="P02", name="vocabulary-violation", tier=1,
            status=ProbeStatus.FAIL, message=f"Query failed: {e}",
        )


def _autofix_vocab_violations(violations: list[dict]) -> int:
    """Remove invalid mind/heart tags, keeping only valid ones via /memory."""
    fixed = 0
    for doc in violations:
        try:
            field = doc["field"]
            valid_vocab = MIND_TAGS if field == "mind" else HEART_TAGS
            valid = [t for t in doc["tags"] if t in valid_vocab]
            _memory_cmd([
                "update", "--collection", doc["collection"],
                "--key", doc["_key"],
                "--data", json.dumps({
                    field: valid,
                    "taxonomy_updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                }),
            ])
            fixed += 1
        except Exception as e:
            logger.debug("Failed to fix vocab for {}: {}", doc.get("_key", "?"), e)
    return fixed


@register_probe("P03", "text-tag-coherence", tier=1)
def probe_text_tag_coherence(autofix: bool = False) -> ProbeResult:
    """Check keyword overlap between text and mind/heart tags.

    Samples both sparta_qra (`mind`) and lessons (`heart`).
    """
    effective_keywords = _get_effective_bridge_keywords()
    if not effective_keywords:
        return ProbeResult(
            probe_id="P03", name="text-tag-coherence", tier=1,
            status=ProbeStatus.SKIP, message="BRIDGE_KEYWORDS not available",
        )

    try:
        # Collect docs from both collections
        half = max(config.SAMPLE_SIZE // 2, 10)
        all_docs: list[dict] = []

        for collection, field in [("sparta_qra", "mind"), ("lessons", "heart")]:
            results = _memory_cmd([
                "sample", "--collection", collection,
                "--filter", f"{field}!=null",
                "--random", "--limit", str(half),
            ])
            raw = results if isinstance(results, list) else results.get("results", [])
            for d in raw:
                text = d.get("text", d.get("question", ""))
                if len(text) > 50 and d.get(field):
                    all_docs.append({"_key": d["_key"], "text": text,
                                     "tags": d[field], "field": field,
                                     "collection": collection})

        if not all_docs:
            return ProbeResult(
                probe_id="P03", name="text-tag-coherence", tier=1,
                status=ProbeStatus.PASS, message="No documents to check",
            )

        low_coherence = []
        scores = []
        for doc in all_docs:
            text_lower = doc["text"].lower()
            tags = doc["tags"]
            hits = 0
            for tag in tags:
                patterns = effective_keywords.get(tag, [])
                if any(p in text_lower for p in patterns):
                    hits += 1
            score = hits / len(tags) if tags else 0.0
            scores.append(score)
            if score < config.COHERENCE_THRESHOLD:
                low_coherence.append({
                    "_key": doc["_key"],
                    "collection": doc["collection"],
                    "field": doc["field"],
                    "tags": tags,
                    "coherence": round(score, 3),
                })

        avg_score = sum(scores) / len(scores) if scores else 0.0
        low_pct = len(low_coherence) / len(all_docs) * 100 if all_docs else 0.0

        if low_pct < 5:
            status = ProbeStatus.PASS
        elif low_pct < 20:
            status = ProbeStatus.WARN
        else:
            status = ProbeStatus.FAIL

        return ProbeResult(
            probe_id="P03", name="text-tag-coherence", tier=1,
            status=status,
            message=(
                f"Avg coherence {avg_score:.2f}, "
                f"{len(low_coherence)}/{len(all_docs)} below threshold ({low_pct:.1f}%)"
            ),
            details={
                "avg_coherence": round(avg_score, 3),
                "low_coherence_count": len(low_coherence),
                "sample_size": len(all_docs),
                "low_coherence_pct": round(low_pct, 1),
                "flagged_keys": [d["_key"] for d in low_coherence[:20]],
            },
        )
    except Exception as e:
        return ProbeResult(
            probe_id="P03", name="text-tag-coherence", tier=1,
            status=ProbeStatus.FAIL, message=f"Query failed: {e}",
        )


@register_probe("P04", "collection-tag-violation", tier=1, auto_fixable=True)
def probe_collection_tag_violation(autofix: bool = False) -> ProbeResult:
    """Check collection_tags against COLLECTION_VOCABULARIES."""
    if not COLLECTION_VOCABULARIES:
        return ProbeResult(
            probe_id="P04", name="collection-tag-violation", tier=1,
            status=ProbeStatus.SKIP, message="COLLECTION_VOCABULARIES not available",
        )

    try:
        all_valid_values: set[str] = set()
        for coll_vocab in COLLECTION_VOCABULARIES.values():
            for dim_values in coll_vocab.values():
                all_valid_values.update(dim_values)

        results = _memory_cmd([
            "sample", "--collection", "lessons",
            "--filter", "collection_tags!=null",
            "--limit", "500",
        ])
        docs = results if isinstance(results, list) else results.get("results", [])

        violations = []
        for doc in docs:
            tags = doc.get("collection_tags", {})
            if not isinstance(tags, dict) or not tags:
                continue
            invalid = {}
            for dim, val in tags.items():
                if isinstance(val, str) and val not in all_valid_values:
                    invalid[dim] = val
            if invalid:
                violations.append({"_key": doc["_key"], "invalid": invalid, "collection_tags": tags})

        count = len(violations)
        if count == 0:
            return ProbeResult(
                probe_id="P04", name="collection-tag-violation", tier=1,
                status=ProbeStatus.PASS,
                message="All collection_tags are valid",
            )

        if autofix:
            fixed = _autofix_collection_violations(violations)
            return ProbeResult(
                probe_id="P04", name="collection-tag-violation", tier=1,
                status=ProbeStatus.FIXED,
                message=f"Removed invalid collection_tags from {fixed}/{count} docs",
                details={"total": count, "fixed": fixed},
                auto_fixable=True, fix_applied=True,
            )

        return ProbeResult(
            probe_id="P04", name="collection-tag-violation", tier=1,
            status=ProbeStatus.WARN,
            message=f"{count} docs with invalid collection_tags",
            details={"count": count, "samples": violations[:10]},
            auto_fixable=True,
        )
    except Exception as e:
        return ProbeResult(
            probe_id="P04", name="collection-tag-violation", tier=1,
            status=ProbeStatus.FAIL, message=f"Query failed: {e}",
        )


def _autofix_collection_violations(violations: list[dict]) -> int:
    """Remove invalid collection tag values via /memory."""
    all_valid: dict[str, set[str]] = {}
    for coll_vocab in COLLECTION_VOCABULARIES.values():
        for dim, values in coll_vocab.items():
            if dim not in all_valid:
                all_valid[dim] = set()
            all_valid[dim].update(values)

    fixed = 0
    for doc in violations:
        try:
            tags = doc.get("collection_tags", {})
            cleaned = {}
            for dim, val in tags.items():
                if dim in all_valid and val in all_valid[dim]:
                    cleaned[dim] = val
            _memory_cmd([
                "update", "--collection", "lessons",
                "--key", doc["_key"],
                "--data", json.dumps({
                    "collection_tags": cleaned,
                    "taxonomy_updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                }),
            ])
            fixed += 1
        except Exception as e:
            logger.debug("Failed to fix collection tags for {}: {}", doc.get("_key", "?"), e)
    return fixed


@register_probe("P06", "vocabulary-expansion-regression", tier=1)
def probe_vocabulary_expansion_regression(autofix: bool = False) -> ProbeResult:
    """Check if recent vocabulary expansions caused coherence regression."""
    try:
        # Check for recently applied proposals (last 24h)
        import time as _time
        try:
            recent_results = _memory_cmd([
                "sample", "--collection", "taxonomy_vocabulary_proposals",
                "--filter", "status=applied",
                "--limit", "50",
            ])
            recent_docs = recent_results if isinstance(recent_results, list) else recent_results.get("results", [])
            cutoff = _time.strftime("%Y-%m-%dT%H:%M:%S", _time.gmtime(_time.time() - 86400))
            recent = [p for p in recent_docs if p.get("applied_at", "") > cutoff]
        except Exception:
            return ProbeResult(
                probe_id="P06", name="vocabulary-expansion-regression", tier=1,
                status=ProbeStatus.PASS, message="No proposals collection or memory unavailable",
            )

        if not recent:
            return ProbeResult(
                probe_id="P06", name="vocabulary-expansion-regression", tier=1,
                status=ProbeStatus.PASS,
                message="No recent vocabulary expansions to check",
            )

        effective_keywords = _get_effective_bridge_keywords()
        if not effective_keywords:
            return ProbeResult(
                probe_id="P06", name="vocabulary-expansion-regression", tier=1,
                status=ProbeStatus.SKIP, message="No keywords available",
            )

        # Sample from both collections using mind/heart fields
        half = max(config.SAMPLE_SIZE // 2, 10)
        combined_docs: list[dict] = []
        for collection, field in [("lessons", "heart"), ("sparta_qra", "mind")]:
            _r = _memory_cmd([
                "sample", "--collection", collection,
                "--filter", f"{field}!=null",
                "--random", "--limit", str(half),
            ])
            for d in (_r if isinstance(_r, list) else _r.get("results", [])):
                text = d.get("text", d.get("question", ""))
                if len(text) > 50 and d.get(field):
                    combined_docs.append({"text": text, "tags": d[field]})

        docs = combined_docs

        if not docs:
            return ProbeResult(
                probe_id="P06", name="vocabulary-expansion-regression", tier=1,
                status=ProbeStatus.PASS, message="No documents to check",
            )

        scores = []
        for doc in docs:
            text_lower = doc["text"].lower()
            tags = doc["tags"]
            hits = 0
            for tag in tags:
                patterns = effective_keywords.get(tag, [])
                if any(p in text_lower for p in patterns):
                    hits += 1
            score = hits / len(tags) if tags else 0.0
            scores.append(score)

        avg_score = sum(scores) / len(scores) if scores else 0.0
        low_count = sum(1 for s in scores if s < config.COHERENCE_THRESHOLD)
        low_pct = low_count / len(docs) * 100

        # Compare to baseline (if state exists)
        state_file = config.STATE_DIR / "latest_report.json"
        baseline_coherence = None
        if state_file.exists():
            try:
                state = json.loads(state_file.read_text())
                for probe in state.get("probes", []):
                    if probe.get("probe_id") == "P03":
                        details = probe.get("details", {})
                        baseline_coherence = details.get("avg_coherence")
                        break
            except Exception as e:
                logger.debug("value lookup failed: {}", e)

        regression = False
        if baseline_coherence is not None and avg_score < baseline_coherence - 0.05:
            regression = True

        proposals_info = [
            {"key": p.get("_key"), "scope": p.get("scope"), "terms": p.get("proposed_additions", [])}
            for p in recent
        ]

        if regression:
            return ProbeResult(
                probe_id="P06", name="vocabulary-expansion-regression", tier=1,
                status=ProbeStatus.WARN,
                message=(
                    f"Coherence regression after expansion: {avg_score:.3f} "
                    f"(baseline {baseline_coherence:.3f}), {len(recent)} recent proposals"
                ),
                details={
                    "avg_coherence": round(avg_score, 3),
                    "baseline_coherence": baseline_coherence,
                    "low_coherence_pct": round(low_pct, 1),
                    "recent_proposals": proposals_info,
                    "regression": True,
                },
            )

        return ProbeResult(
            probe_id="P06", name="vocabulary-expansion-regression", tier=1,
            status=ProbeStatus.PASS,
            message=(
                f"No regression after {len(recent)} expansions "
                f"(coherence {avg_score:.3f}, {low_pct:.1f}% below threshold)"
            ),
            details={
                "avg_coherence": round(avg_score, 3),
                "baseline_coherence": baseline_coherence,
                "low_coherence_pct": round(low_pct, 1),
                "recent_proposals": proposals_info,
                "regression": False,
            },
        )
    except Exception as e:
        return ProbeResult(
            probe_id="P06", name="vocabulary-expansion-regression", tier=1,
            status=ProbeStatus.FAIL, message=f"Query failed: {e}",
        )


@register_probe("P05", "stale-taxonomy", tier=1)
def probe_stale_taxonomy(autofix: bool = False) -> ProbeResult:
    """Find documents with taxonomy_updated_at older than STALE_DAYS."""
    try:
        import time as _time
        cutoff_ts = _time.strftime(
            "%Y-%m-%dT%H:%M:%S",
            _time.gmtime(_time.time() - config.STALE_DAYS * 86400),
        )

        # Sample docs with taxonomy tags from both collections
        results = _memory_cmd([
            "sample", "--collection", "lessons",
            "--filter", "heart!=null",
            "--limit", "300",
        ])
        docs2 = _memory_cmd([
            "sample", "--collection", "sparta_qra",
            "--filter", "mind!=null",
            "--limit", "200",
        ])
        lesson_list = results if isinstance(results, list) else results.get("results", [])
        qra_list = docs2 if isinstance(docs2, list) else docs2.get("results", [])
        docs = lesson_list + qra_list

        stale_old = 0
        no_ts_count = 0
        for doc in docs:
            ts = doc.get("taxonomy_updated_at")
            if ts is None:
                no_ts_count += 1
            elif ts < cutoff_ts:
                stale_old += 1

        total_stale = stale_old + no_ts_count

        if total_stale == 0:
            return ProbeResult(
                probe_id="P05", name="stale-taxonomy", tier=1,
                status=ProbeStatus.PASS,
                message=f"No stale taxonomy (all within {config.STALE_DAYS} days)",
            )

        status = ProbeStatus.WARN if total_stale < 100 else ProbeStatus.FAIL
        return ProbeResult(
            probe_id="P05", name="stale-taxonomy", tier=1,
            status=status,
            message=f"{total_stale} docs with stale taxonomy ({stale_old} old + {no_ts_count} no timestamp)",
            details={"stale_old": stale_old, "stale_no_ts": no_ts_count, "total": total_stale},
        )
    except Exception as e:
        return ProbeResult(
            probe_id="P05", name="stale-taxonomy", tier=1,
            status=ProbeStatus.FAIL, message=f"Query failed: {e}",
        )
