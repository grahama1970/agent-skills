#!/usr/bin/env python3
"""Memory integration for inline PDF reviewer.

Split from inline_reviewer.py to stay under 800-line module limit.
Handles /memory storage, retrieval, cross-PDF graph edges, and taxonomy.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from loguru import logger

try:
    from json_repair import repair_json as _repair_json
    _HAS_JSON_REPAIR = True
except ImportError:
    _HAS_JSON_REPAIR = False


def _parse_json_safe(raw: str) -> Any:
    """Parse JSON from CLI output that may have warnings/text before the JSON.

    Uses json_repair as fallback (same pattern as extractor json_utils.parse_json).
    """
    if not raw or not raw.strip():
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = re.search(r"(\{.*\}|\[.*\])", raw, re.DOTALL)
    if match:
        extracted = match.group(1)
        try:
            return json.loads(extracted)
        except json.JSONDecodeError:
            pass
        if _HAS_JSON_REPAIR:
            try:
                repaired = _repair_json(extracted, return_objects=True)
                if isinstance(repaired, (dict, list)):
                    return repaired
            except Exception as e:
                logger.debug("extraction failed: {}", e)
    return None

# ---------------------------------------------------------------------------
# graph_memory for /memory integration
# RULE: NEVER use get_db() directly. Only MemoryClient, search(), add_edge().
# ---------------------------------------------------------------------------
try:
    from graph_memory.api import MemoryClient, add_edge, search

    HAS_MEMORY = True
except ImportError:
    HAS_MEMORY = False

_THIS_DIR = Path(__file__).resolve().parent
_SKILLS_DIR = _THIS_DIR.parent
# Removed: memory accessed via httpx to Unix socket (see _memory_cmd)

if not HAS_MEMORY:

    class _HttpxMemoryClient:
        """Memory client using httpx to embry-memory Unix socket."""

        def __init__(self, scope: str = ""):
            self.scope = scope

        def recall(self, query: str, k: int = 10):
            try:
                import httpx
                transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
                with httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0) as client:
                    body: dict = {"q": query, "k": k}
                    if self.scope:
                        body["scope"] = self.scope
                    resp = client.post("/recall", json=body)
                    return resp.json() if resp.status_code == 200 else {"found": False, "items": []}
            except Exception:
                return {"found": False, "items": []}

        def learn(self, problem: str = "", solution: str = "", tags=None):
            try:
                import httpx
                transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
                with httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0) as client:
                    body: dict = {"problem": problem, "solution": solution}
                    if self.scope:
                        body["scope"] = self.scope
                    if tags:
                        body["tags"] = list(tags)
                    resp = client.post("/learn", json=body)
                    return resp.json() if resp.status_code == 200 else {"meta": {"ok": False}}
            except Exception as exc:
                print(f"review_memory learn EXCEPTION {type(exc).__name__}: {exc}", flush=True)
                return {"meta": {"ok": False}}

    MemoryClient = _HttpxMemoryClient
    HAS_MEMORY = True

    def add_edge(*args, **kwargs):
        """Stub -- edge creation not supported via subprocess fallback."""
        return {"meta": {"ok": False}}

    def search(*args, **kwargs):
        """Stub -- search not supported via subprocess fallback."""
        return []

    print("review_memory using subprocess MemoryClient fallback", flush=True)

# ---------------------------------------------------------------------------
# Taxonomy for bridge_tags
# ---------------------------------------------------------------------------
try:
    from common.taxonomy import extract_taxonomy_features, ContentType

    HAS_TAXONOMY = True
except ImportError:
    HAS_TAXONOMY = False


def extract_review_taxonomy(review_text: str) -> Dict[str, Any]:
    """Extract taxonomy bridge_tags + collection_tags from review text."""
    if not HAS_TAXONOMY:
        return {"bridge_tags": [], "collection_tags": {}}

    try:
        bridge_context = (
            "precision accuracy fidelity verification integrity "
            "resilience robustness quality assurance "
        )
        features = extract_taxonomy_features(
            content_type=ContentType.OPERATIONAL,
            description=f"{bridge_context}{review_text[:1800]}",
            high_fidelity=False,
        )
        return {
            "bridge_tags": features.get("bridge_attributes", []),
            "collection_tags": features.get("collection_tags", {}),
        }
    except Exception:
        return {"bridge_tags": [], "collection_tags": {}}


MAX_RELATED_EDGES_PER_REVIEW = 5


def problem_to_title(problem: str) -> str:
    """Replicate graph_memory's title generation from problem text."""
    if len(problem) > 60:
        return problem[:60] + "..."
    return problem


def assessment_exists(pdf_hash: str) -> bool:
    """Check if a pdf_assessment already exists for this hash in /memory.

    Lightweight check used to skip inline reviews for PDFs that have
    already been assessed.  Returns False on any error so the review
    proceeds as a fallback.

    FAIL-verdict assessments are treated as non-existent so the document
    gets re-assessed (scoring improvements may upgrade the result).

    Uses MemoryClient.recall() instead of search() because search() is
    stubbed in the subprocess fallback path.
    """
    if not HAS_MEMORY or not pdf_hash:
        return False
    try:
        hash_prefix = pdf_hash[:8]
        client = MemoryClient(scope="extractor")
        result = client.recall(f"pdf_assessment {hash_prefix}", k=3)
        for item in result.get("items", []):
            tags = item.get("tags", [])
            if hash_prefix in tags and "pdf_assessment" in tags:
                if "FAIL" in tags:
                    return False
                return True
    except Exception as e:
        logger.debug("value lookup failed: {}", e)
    return False


def search_related_reviews(
    pdf_hash: str,
    sector: str,
    worst_dimension: str,
    max_results: int = 5,
) -> List[Dict[str, Any]]:
    """Search /memory for related past reviews of similar PDFs."""
    if not HAS_MEMORY:
        return []

    related = []
    try:
        hash_query = f"pdf_assessment {pdf_hash[:8]}"
        hash_result = search(q=hash_query, scope="extractor", k=max_results)
        for item in hash_result.get("items", []):
            tags = item.get("tags", [])
            if pdf_hash[:8] in tags and "pdf_assessment" in tags:
                related.append({
                    "_key": item.get("_key", ""),
                    "problem": item.get("problem", ""),
                    "solution": item.get("solution", ""),
                    "match_type": "same_pdf",
                })

        query = f"pdf extraction {sector} {worst_dimension} review"
        search_result = search(q=query, scope="extractor", k=max_results)
        for item in search_result.get("items", []):
            related.append({
                "_key": item.get("_key", ""),
                "problem": item.get("problem", ""),
                "solution": item.get("solution", ""),
                "match_type": "similar_issue",
            })
    except Exception as e:
        logger.debug("matching failed: {}", e)

    return related[:max_results]


def store_assessment(
    result: Dict[str, Any],
    run_id: str,
) -> tuple[Optional[str], str]:
    """Store structured assessment in /memory via MemoryClient.learn()."""
    if not HAS_MEMORY:
        return None, ""

    try:
        client = MemoryClient(scope="extractor")

        problem = (
            f"pdf_assessment {result['pdf_hash'][:8]} "
            f"{result.get('sector', 'unknown')} "
            f"score={result['overall_score']:.3f} grade={result['grade']} "
            f"verdict={result['verdict']} "
            f"margaret={result['margaret']['verdict']} "
            f"jennifer={result['jennifer']['verdict']} "
            f"reconciled={result['reconciled']['decision']} "
            f"path={Path(result['pdf_path']).name}"
        )

        taxonomy = extract_review_taxonomy(problem)

        solution_data = {
            "pdf_path": result["pdf_path"],
            "pdf_hash": result["pdf_hash"],
            "overall_score": result["overall_score"],
            "grade": result["grade"],
            "verdict": result["verdict"],
            "dimensions": result["dimensions"],
            "margaret_verdict": result["margaret"]["verdict"],
            "margaret_score": result["margaret"]["weighted_score"],
            "jennifer_verdict": result["jennifer"]["verdict"],
            "jennifer_score": result["jennifer"]["weighted_score"],
            "reconciled_decision": result["reconciled"]["decision"],
            "run_id": run_id,
            "timestamp": result["timestamp"],
            "bridge_tags": taxonomy["bridge_tags"],
            "taxonomy": taxonomy["collection_tags"],
        }
        solution = json.dumps(solution_data, default=str)

        tags = [
            "pdf_assessment",
            result.get("sector", "unknown"),
            result["grade"],
            result["verdict"],
            result["pdf_hash"][:8],
        ]
        tags.extend(taxonomy["bridge_tags"])

        learn_result = client.learn(
            problem=problem,
            solution=solution,
            tags=tags,
        )
        if learn_result.get("meta", {}).get("ok"):
            items = learn_result.get("items", [])
            key = items[0]["_key"] if items else "subprocess_ok"
            print(f"review_memory store_assessment OK key={key} tags_count={len(tags)}", flush=True)
            return key, problem
        print(f"review_memory store_assessment learn_result not ok: {learn_result}", flush=True)
        return None, problem
    except Exception as exc:
        print(f"review_memory store_assessment EXCEPTION: {type(exc).__name__}: {exc}", flush=True)
        return None, ""


def store_lesson_for_failure(
    result: Dict[str, Any],
    assessment_key: Optional[str],
    assessment_problem: str = "",
) -> Optional[str]:
    """For WARN/FAIL PDFs, store a lesson in /memory with remediation recommendation."""
    if not HAS_MEMORY:
        return None

    try:
        worst_dim = min(
            result["dimensions"].items(),
            key=lambda x: x[1]["score"],
        )
        problem = (
            f"PDF extraction {result['verdict']}: {result['pdf_path']} "
            f"(score={result['overall_score']:.3f}, grade={result['grade']}, "
            f"worst_dimension={worst_dim[0]}={worst_dim[1]['score']:.3f})"
        )
        recs = [i["recommendation"] for i in result.get("issues_dicts", [])[:3]]
        solution = "; ".join(recs) if recs else f"Review {worst_dim[0]} extraction"

        taxonomy = extract_review_taxonomy(problem)

        tags = [
            result.get("sector", "unknown"),
            result["grade"],
            result["verdict"],
            result["pdf_hash"][:8],
        ]
        tags.extend(taxonomy["bridge_tags"])

        client = MemoryClient(scope="extractor")
        learn_result = client.learn(
            problem=problem,
            solution=solution,
            tags=tags,
        )
        if learn_result.get("meta", {}).get("ok"):
            items = learn_result.get("items", [])
            key = items[0]["_key"] if items else "subprocess_ok"
            if assessment_key and assessment_problem:
                try:
                    add_edge(
                        from_title=problem_to_title(problem),
                        to_title=problem_to_title(assessment_problem),
                        type="depends_on",
                        from_scope="extractor",
                        to_scope="extractor",
                        weight=0.8,
                        rationale="Lesson derived from PDF assessment",
                    )
                except Exception as e:
                    logger.debug("extraction failed: {}", e)
            return key
        return None
    except Exception:
        return None


def create_cross_pdf_edges(
    assessment_key: str,
    related_reviews: List[Dict[str, Any]],
    result: Dict[str, Any],
    from_problem: str,
) -> List[str]:
    """Create graph edges between this assessment and related reviews."""
    if not HAS_MEMORY or not assessment_key:
        return []

    edge_ids = []
    from_title = problem_to_title(from_problem)
    related_count = 0

    for review in related_reviews:
        review_key = review.get("_key", "")
        if not review_key or review_key == assessment_key:
            continue

        match_type = review.get("match_type", "")
        edge_type = "supersedes" if match_type == "same_pdf" else "related"

        if edge_type == "related":
            if related_count >= MAX_RELATED_EDGES_PER_REVIEW:
                continue
            related_count += 1

        weight = 0.9 if match_type == "same_pdf" else 0.6
        to_title = problem_to_title(review.get("problem", ""))
        if not to_title:
            continue

        try:
            edge_result = add_edge(
                from_title=from_title,
                to_title=to_title,
                type=edge_type,
                from_scope="extractor",
                to_scope="extractor",
                weight=weight,
                rationale=f"{edge_type}: {result.get('sector', 'unknown')} {match_type}",
            )
            if edge_result.get("meta", {}).get("ok"):
                items = edge_result.get("items", [])
                for item in items:
                    edge_id = f"{item.get('from', '')}->{item.get('to', '')}"
                    if "->" != edge_id:
                        edge_ids.append(edge_id)
        except Exception as e:
            logger.debug("value lookup failed: {}", e)

    return [eid for eid in edge_ids if eid]


def find_related_reviews(
    pdf_hash: str = "",
    sector: str = "",
    dimension: str = "",
    verdict: str = "",
    max_results: int = 10,
) -> Dict[str, Any]:
    """Find related reviews using /memory search with multi-hop discovery."""
    if not HAS_MEMORY:
        return {"same_pdf": [], "same_sector": [], "similar_dimension": [], "total": 0}

    results: Dict[str, List[Dict[str, Any]]] = {
        "same_pdf": [],
        "same_sector": [],
        "similar_dimension": [],
    }

    client = MemoryClient(scope="extractor")

    try:
        if pdf_hash:
            hash_result = client.recall(
                f"pdf_assessment {pdf_hash[:8]}",
                k=max_results,
            )
            for item in hash_result.get("items", []):
                tags = item.get("tags", [])
                if pdf_hash[:8] in tags and "pdf_assessment" in tags:
                    results["same_pdf"].append(review_item(item))

        if sector and dimension:
            dim_result = client.recall(
                f"pdf_assessment {sector} {dimension} extraction quality",
                k=max_results,
            )
            for item in dim_result.get("items", []):
                tags = item.get("tags", [])
                if "pdf_assessment" in tags and sector in tags:
                    results["similar_dimension"].append(review_item(item))

        if sector:
            sector_result = client.recall(
                f"pdf_assessment {sector} extraction review",
                k=max_results,
            )
            for item in sector_result.get("items", []):
                tags = item.get("tags", [])
                if "pdf_assessment" in tags and sector in tags:
                    results["same_sector"].append(review_item(item))

    except Exception as e:
        logger.debug("value lookup failed: {}", e)

    seen_keys = set()
    for category in results:
        deduped = []
        for item in results[category]:
            if item["_key"] not in seen_keys:
                seen_keys.add(item["_key"])
                deduped.append(item)
        results[category] = deduped[:max_results]

    total = sum(len(v) for v in results.values())
    return {**results, "total": total}


def review_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Extract structured review data from a /memory search result."""
    solution = item.get("solution", "")
    try:
        data = json.loads(solution) if solution.startswith("{") else {}
    except (json.JSONDecodeError, TypeError):
        data = {}

    return {
        "_key": item.get("_key", ""),
        "problem": item.get("problem", ""),
        "score": data.get("overall_score"),
        "grade": data.get("grade"),
        "verdict": data.get("verdict"),
        "sector": data.get("sector") or next(
            (t for t in item.get("tags", []) if t not in ("pdf_assessment",)), ""
        ),
        "bridge_tags": data.get("bridge_tags", []),
        "timestamp": data.get("timestamp"),
    }


# ---------------------------------------------------------------------------
# Content ingestion — PASS/WARN docs get their extracted text/tables/figures
# stored to /memory so personas can query via BM25 + semantic + multi-hop.
# Uses ONLY MemoryClient.learn() + add_edge() — no bespoke ArangoDB.
# ---------------------------------------------------------------------------

_MAX_CONTENT_CHUNKS = 200  # safety cap per document


def _load_content_chunks(profile_path: Path) -> list[dict]:
    """Load extracted content from the best available artifact.

    Priority: 11_json_exporter/structural.json → 10_arangodb_exporter/.../10_flattened_data.json
    Returns list of dicts with at minimum: _key, object_type, text_content.
    """
    from verify.analysis import resolve_doc_inputs
import httpx

    inputs = resolve_doc_inputs(profile_path)

    # Try structural.json first (richest data)
    structural_path = inputs.get("structural_path")
    if structural_path and Path(structural_path).exists():
        try:
            data = json.loads(Path(structural_path).read_text())
            elements = data.get("elements", data.get("data", []))
            if isinstance(elements, list) and elements:
                return elements[:_MAX_CONTENT_CHUNKS]
        except (json.JSONDecodeError, KeyError):
            pass

    # Fall back to flattened_data.json
    flattened_path = inputs.get("flattened_path")
    if flattened_path and Path(flattened_path).exists():
        try:
            raw = json.loads(Path(flattened_path).read_text())
            if isinstance(raw, dict):
                raw = raw.get("data", raw.get("items", []))
            if isinstance(raw, list) and raw:
                return raw[:_MAX_CONTENT_CHUNKS]
        except (json.JSONDecodeError, KeyError):
            pass

    return []


def ingest_content_to_memory(
    profile_path: Path,
    pdf_hash: str,
    pdf_path: str,
    sector: str,
    assessment_key: str | None = None,
    extraction_grade: str = "",
    extraction_score: float = 0.0,
) -> dict:
    """Ingest extracted content chunks into /memory via learn() API.

    Each chunk becomes a lesson with:
      - problem: structured descriptor (asset_type, section, page, pdf_hash)
      - solution: the actual text content
      - tags: [extracted_content, asset_type, sector, pdf_hash prefix, bridge_tags...]

    This is what enables multi-hop graph traversal with taxonomy bridge_tags.
    The /memory service handles embeddings and taxonomy extraction internally.

    Returns: {"learned": int, "skipped": int, "edges": int, "errors": int}
    """
    if not HAS_MEMORY:
        return {"learned": 0, "skipped": 0, "edges": 0, "errors": 0, "reason": "no_memory"}

    chunks = _load_content_chunks(profile_path)
    if not chunks:
        return {"learned": 0, "skipped": 0, "edges": 0, "errors": 0, "reason": "no_content"}

    client = MemoryClient(scope="extractor")
    hash_prefix = pdf_hash[:8] if pdf_hash else "unknown"
    pdf_name = Path(pdf_path).stem if pdf_path else "unknown"

    learned = 0
    skipped = 0
    errors = 0
    edge_count = 0

    for chunk in chunks:
        text = chunk.get("text_content", "") or chunk.get("text", "")
        if not text or not text.strip() or len(text.strip()) < 20:
            skipped += 1
            continue

        asset_type = chunk.get("object_type", chunk.get("type", "text"))
        section_title = chunk.get("section_title", "") or ""
        section_id = chunk.get("section_id", "") or ""
        page_num = chunk.get("page_num", chunk.get("page", 0)) or 0
        chunk_key = chunk.get("_key", "")

        # Build structured problem descriptor for recall
        grade_tag = f" grade={extraction_grade}" if extraction_grade else ""
        problem = (
            f"extracted_content {hash_prefix} "
            f"type={asset_type} page={page_num} "
            f"section={section_title[:60] or section_id} "
            f"pdf={pdf_name}{grade_tag}"
        )

        # Tags enable targeted recall and multi-hop traversal
        tags = [
            "extracted_content",
            asset_type,
            sector,
            hash_prefix,
        ]
        if extraction_grade:
            tags.append(f"grade_{extraction_grade.lower().replace('+', 'plus')}")
        if section_title:
            # Add first significant word of section title for recall
            words = [w for w in section_title.split() if len(w) > 3]
            if words:
                tags.append(words[0].lower())

        try:
            result = client.learn(
                problem=problem,
                solution=text[:4000],  # /memory handles embedding + taxonomy
                tags=tags,
            )
            if result.get("meta", {}).get("ok"):
                learned += 1

                # Create edge from assessment to content chunk
                if assessment_key:
                    try:
                        add_edge(
                            from_title=problem_to_title(
                                f"pdf_assessment {hash_prefix} {sector}"
                            ),
                            to_title=problem_to_title(problem),
                            type="has_content",
                            from_scope="extractor",
                            to_scope="extractor",
                            weight=0.7,
                            rationale=f"Assessment contains {asset_type} chunk",
                        )
                        edge_count += 1
                    except Exception as e:
                        logger.debug("extraction failed: {}", e)
            else:
                errors += 1
        except Exception:
            errors += 1

    return {
        "learned": learned,
        "skipped": skipped,
        "edges": edge_count,
        "errors": errors,
        "total_chunks": len(chunks),
    }
