#!/usr/bin/env python3
"""ArangoDB maintenance: embeddings, duplicates, orphans, integrity, stats."""
import typer
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

try:
    from arango import ArangoClient
except ImportError:
    print("ERROR: python-arango required. Install with: pip install python-arango", file=sys.stderr)
    sys.exit(1)


@dataclass
class MaintenanceReport:
    """Aggregated maintenance report."""
    status: str = "healthy"
    checks: dict = field(default_factory=dict)
    recommendations: list = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps({
            "status": self.status,
            "checks": self.checks,
            "recommendations": self.recommendations,
        }, indent=2)


def get_db():
    """Connect to ArangoDB."""
    url = os.environ.get("ARANGO_URL", "http://127.0.0.1:8529")
    db_name = os.environ.get("ARANGO_DB", "memory")
    user = os.environ.get("ARANGO_USER", "root")
    password = os.environ.get("ARANGO_PASS", "")

    client = ArangoClient(hosts=url)
    return client.db(db_name, username=user, password=password)


def check_embeddings(
    db,
    fix: bool = False,
    embedding_service: Optional[str] = None,
    scope: Optional[str] = None,
) -> dict:
    """Find documents that VIOLATE the vector contract by holding embedding arrays.

    Operator ruling (2026-07-31): ArangoDB must NEVER store embeddings — Qdrant
    is the only vector store. Arango documents carry pointer metadata only
    (qdrant_collection, qdrant_point_id, embedding_model, text_hash,
    semantic_sync_state). A doc WITH an `embedding` array is the defect.

    Args:
        db: ArangoDB database connection
        fix: Refused. Migration to Qdrant is owned by the memory repo
             (scripts/migrate_arango_embeddings_to_qdrant.py), not this check.
        embedding_service: Unused; kept for CLI signature compatibility.
        scope: Filter collections by prefix (e.g., "sparta" for sparta_*)
    """
    results = {
        "contract": "arango-never-stores-embeddings",
        "violations": [],
        "violation_count": 0,
        "total": 0,
        "fixed": 0,
        "remediation": (
            "run the memory repo's scripts/migrate_arango_embeddings_to_qdrant.py "
            "to move vectors to Qdrant and strip the Arango field"
        ),
    }
    if fix:
        # Stripping 100K+ embedding fields is a migration, not a health-check
        # side effect; the memory repo owns it. Fail loudly instead of mutating.
        print(
            "ERROR: 'embeddings --fix' is refused: Arango never stores embeddings; "
            "use the memory repo's migrate_arango_embeddings_to_qdrant.py",
            file=sys.stderr,
        )
        results["fix_refused"] = True
        return results

    embedding_collections = {
        "lessons": "problem",
        "episodes": "content",
        "sparta_qra": "question",
        "sparta_controls": "name",
        "sparta_url_knowledge": "topic",
    }
    if scope:
        embedding_collections = {
            k: v for k, v in embedding_collections.items()
            if k.startswith(scope)
        }

    for coll_name, preview_field in embedding_collections.items():
        if not db.has_collection(coll_name):
            continue

        coll = db.collection(coll_name)

        # Count server-side; never pull full documents for a report (a full
        # RETURN doc scan blew the 60s client timeout on 233K+ collections).
        count_query = """
        FOR doc IN @@collection
            FILTER HAS(doc, "embedding") AND doc.embedding != null
            COLLECT WITH COUNT INTO violation_count
            RETURN violation_count
        """
        violation_count = next(
            db.aql.execute(count_query, bind_vars={"@collection": coll_name})
        )
        results["violation_count"] += violation_count

        results["total"] += coll.count()
        if violation_count:
            sample_query = """
            FOR doc IN @@collection
                FILTER HAS(doc, "embedding") AND doc.embedding != null
                LIMIT @sample
                RETURN {_key: doc._key, preview: doc.@preview_field}
            """
            for doc in db.aql.execute(sample_query, bind_vars={
                "@collection": coll_name,
                "sample": 25,
                "preview_field": preview_field or "_key",
            }):
                results["violations"].append({
                    "collection": coll_name,
                    "_key": doc["_key"],
                    "preview": str(doc.get("preview") or "")[:50],
                })

    return results


def check_duplicates(db, report_only: bool = True) -> dict:
    """Detect duplicate lessons by title similarity."""
    results = {"found": 0, "clusters": []}

    if not db.has_collection("lessons"):
        return results

    # Find exact title duplicates first
    query = """
    FOR doc IN lessons
        COLLECT title = doc.title INTO group
        FILTER LENGTH(group) > 1
        RETURN {
            title: title,
            count: LENGTH(group),
            keys: group[*].doc._key
        }
    """
    cursor = db.aql.execute(query)
    clusters = list(cursor)

    results["found"] = sum(c["count"] for c in clusters)
    results["clusters"] = clusters

    return results


def check_orphans(db, fix: bool = False) -> dict:
    """Find edges pointing to deleted documents."""
    results = {"orphaned_edges": [], "fixed": 0}

    # Edge collections in memory graph
    edge_collections = ["verifies", "contradicts", "related_to", "supersedes"]

    for edge_coll in edge_collections:
        if not db.has_collection(edge_coll):
            continue

        coll = db.collection(edge_coll)

        # Find edges with missing _from or _to
        query = """
        FOR edge IN @@collection
            LET from_exists = DOCUMENT(edge._from) != null
            LET to_exists = DOCUMENT(edge._to) != null
            FILTER !from_exists OR !to_exists
            RETURN {
                _key: edge._key,
                _from: edge._from,
                _to: edge._to,
                from_missing: !from_exists,
                to_missing: !to_exists
            }
        """
        cursor = db.aql.execute(query, bind_vars={"@collection": edge_coll})
        orphans = list(cursor)

        for orphan in orphans:
            orphan["collection"] = edge_coll
            results["orphaned_edges"].append(orphan)

            if fix:
                try:
                    coll.delete(orphan["_key"])
                    results["fixed"] += 1
                except Exception as e:
                    print(f"[warn] Failed to delete {edge_coll}/{orphan['_key']}: {e}", file=sys.stderr)

    return results


def check_integrity(db) -> dict:
    """Verify referential integrity across collections."""
    results = {"errors": [], "checked": 0}

    # Check lessons reference valid sources
    if db.has_collection("lessons"):
        query = """
        FOR lesson IN lessons
            FILTER lesson.source_episode != null
            LET episode = DOCUMENT(CONCAT("episodes/", lesson.source_episode))
            FILTER episode == null
            RETURN {type: "missing_episode", lesson: lesson._key, source: lesson.source_episode}
        """
        cursor = db.aql.execute(query)
        results["errors"].extend(list(cursor))
        results["checked"] += db.collection("lessons").count()

    # Check graph edges form valid paths
    if db.has_graph("memory_graph"):
        graph = db.graph("memory_graph")
        for edge_def in graph.edge_definitions():
            edge_coll = edge_def["edge_collection"]
            if db.has_collection(edge_coll):
                results["checked"] += db.collection(edge_coll).count()

    return results


def get_stats(db) -> dict:
    """Get collection statistics."""
    stats = {"collections": {}, "total_documents": 0, "total_size_bytes": 0}

    for coll in db.collections():
        if coll["system"]:
            continue
        name = coll["name"]
        coll_obj = db.collection(name)
        try:
            props = coll_obj.statistics()
            count = coll_obj.count()
            stats["collections"][name] = {
                "count": count,
                "size_bytes": props.get("documentSize", 0),
            }
            stats["total_documents"] += count
            stats["total_size_bytes"] += props.get("documentSize", 0)
        except Exception:
            stats["collections"][name] = {"count": 0, "error": "failed to get stats"}

    return stats


def sparta_health_check(db) -> dict:
    """Comprehensive SPARTA data integrity validation.

    Returns a structured report with all checks organized by category.
    Every finding is backed by a deterministic AQL query.
    """
    report = {
        "status": "healthy",
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "summary": {"passed": 0, "warnings": 0, "failed": 0},
        "categories": {},
    }

    def add_check(category: str, name: str, passed: bool, count: int,
                  expected: str, query_hint: str = "", details: list = None):
        """Add a check result to the report."""
        if category not in report["categories"]:
            report["categories"][category] = {"checks": [], "status": "passed"}

        status = "passed" if passed else ("warning" if count < 100 else "failed")
        check = {
            "name": name,
            "status": status,
            "count": count,
            "expected": expected,
            "query_hint": query_hint,
        }
        if details:
            if isinstance(details, list):
                check["details"] = details[:10]  # Limit to 10 examples
            else:
                check["details"] = details  # dict or other structure

        report["categories"][category]["checks"].append(check)
        report["summary"]["passed" if passed else ("warnings" if status == "warning" else "failed")] += 1

        if status == "failed":
            report["categories"][category]["status"] = "failed"
            report["status"] = "critical"
        elif status == "warning" and report["categories"][category]["status"] != "failed":
            report["categories"][category]["status"] = "warning"
            if report["status"] == "healthy":
                report["status"] = "warning"

    # ═══════════════════════════════════════════════════════════════════════════
    # 1. QRA SCHEMA VALIDATION
    # ═══════════════════════════════════════════════════════════════════════════

    if db.has_collection("sparta_qra"):
        total_qras = db.collection("sparta_qra").count()

        # Check: QRAs with null/empty question
        cursor = db.aql.execute("""
            FOR d IN sparta_qra
                FILTER d.question == null OR LENGTH(d.question) < 5
                RETURN d._key
        """)
        bad = list(cursor)
        add_check("qra_schema", "question_valid", len(bad) == 0, len(bad),
                  "0 QRAs with null/empty question",
                  "FILTER d.question == null OR LENGTH(d.question) < 5", bad)

        # Check: QRAs with null/short reasoning
        cursor = db.aql.execute("""
            FOR d IN sparta_qra
                FILTER d.reasoning == null OR LENGTH(TOKENS(d.reasoning, 'text_en')) < 5
                LIMIT 1000
                RETURN d._key
        """)
        bad = list(cursor)
        add_check("qra_schema", "reasoning_valid", len(bad) == 0, len(bad),
                  "0 QRAs with <5 word reasoning",
                  "FILTER LENGTH(TOKENS(d.reasoning, 'text_en')) < 5", bad)

        # Check: native QRAs with empty evidence_quotes (sparta_context uses evidence_case instead)
        cursor = db.aql.execute("""
            FOR d IN sparta_qra
                FILTER d.category != "sparta_context"
                FILTER !IS_ARRAY(d.evidence_quotes) OR LENGTH(d.evidence_quotes) == 0
                RETURN d._key
        """)
        bad = list(cursor)
        add_check("qra_schema", "evidence_quotes_present", len(bad) == 0, len(bad),
                  "0 native QRAs with empty evidence_quotes (sparta_context excluded)",
                  "FILTER category != 'sparta_context' AND LENGTH(evidence_quotes) == 0", bad)

        # Check: QRAs missing source_control_id AND control_id
        cursor = db.aql.execute("""
            FOR d IN sparta_qra
                FILTER (d.source_control_id == null OR d.source_control_id == "")
                   AND (d.control_id == null OR d.control_id == "")
                RETURN d._key
        """)
        bad = list(cursor)
        add_check("qra_schema", "control_id_present", len(bad) == 0, len(bad),
                  "0 QRAs missing both source_control_id and control_id",
                  "FILTER d.source_control_id == null AND d.control_id == null", bad)

        # Check: QRAs with invalid category
        valid_cats = ["sparta_context", "cwe_native", "capec_native", "attack_native",
                      "nist_native", "sparta_native", "d3fend_native", "esa_native",
                      "cve_native", "nasa_native", "iso_native"]
        cursor = db.aql.execute("""
            FOR d IN sparta_qra
                FILTER d.category == null OR d.category NOT IN @valid
                RETURN {key: d._key, cat: d.category}
        """, bind_vars={"valid": valid_cats})
        bad = list(cursor)
        add_check("qra_schema", "category_valid", len(bad) == 0, len(bad),
                  "0 QRAs with invalid category",
                  "FILTER d.category NOT IN [valid categories]",
                  [b["cat"] for b in bad[:10]])

        # Check: QRAs with invalid verdict
        cursor = db.aql.execute("""
            FOR d IN sparta_qra
                FILTER d.verdict != null AND d.verdict NOT IN ["SATISFIED", "NEEDS_REVIEW", "REJECTED"]
                RETURN {key: d._key, verdict: d.verdict}
        """)
        bad = list(cursor)
        add_check("qra_schema", "verdict_valid", len(bad) == 0, len(bad),
                  "0 QRAs with invalid verdict enum",
                  "FILTER d.verdict NOT IN ['SATISFIED', 'NEEDS_REVIEW', 'REJECTED']", bad)

        # Check: QRAs with missing/wrong-dim embedding
        cursor = db.aql.execute("""
            FOR d IN sparta_qra
                FILTER d.embedding == null OR !IS_ARRAY(d.embedding) OR LENGTH(d.embedding) != 384
                RETURN d._key
        """)
        bad = list(cursor)
        add_check("qra_schema", "embedding_384dim", len(bad) == 0, len(bad),
                  "0 QRAs with missing/invalid 384-dim embedding",
                  "FILTER LENGTH(d.embedding) != 384", bad)

    # ═══════════════════════════════════════════════════════════════════════════
    # 2. EVIDENCE CASE SCHEMA VALIDATION (for relationship QRAs)
    # ═══════════════════════════════════════════════════════════════════════════

    if db.has_collection("sparta_qra"):
        # Check: sparta_context QRAs should have evidence_case
        cursor = db.aql.execute("""
            FOR d IN sparta_qra
                FILTER d.category == "sparta_context"
                FILTER d.evidence_case == null OR !IS_OBJECT(d.evidence_case)
                RETURN d._key
        """)
        bad = list(cursor)
        add_check("evidence_case", "present_for_context", len(bad) == 0, len(bad),
                  "0 sparta_context QRAs missing evidence_case object",
                  "FILTER d.category == 'sparta_context' AND d.evidence_case == null", bad)

        # Check: evidence_case has required fields
        cursor = db.aql.execute("""
            FOR d IN sparta_qra
                FILTER d.category == "sparta_context" AND d.evidence_case != null
                FILTER d.evidence_case.resolved_entities == null
                    OR d.evidence_case.glossary == null
                    OR d.evidence_case.crosswalk_chains == null
                LIMIT 500
                RETURN d._key
        """)
        bad = list(cursor)
        add_check("evidence_case", "required_fields", len(bad) == 0, len(bad),
                  "0 evidence_cases missing resolved_entities/glossary/crosswalk_chains",
                  "FILTER d.evidence_case.resolved_entities == null", bad)

        # Check: evidence_case.crosswalk_chains non-empty
        cursor = db.aql.execute("""
            FOR d IN sparta_qra
                FILTER d.category == "sparta_context" AND d.evidence_case != null
                FILTER !IS_ARRAY(d.evidence_case.crosswalk_chains)
                    OR LENGTH(d.evidence_case.crosswalk_chains) == 0
                LIMIT 500
                RETURN d._key
        """)
        bad = list(cursor)
        add_check("evidence_case", "crosswalk_chains_populated", len(bad) == 0, len(bad),
                  "0 evidence_cases with empty crosswalk_chains",
                  "FILTER LENGTH(d.evidence_case.crosswalk_chains) == 0", bad)

        # Check: evidence_case.review_status valid
        cursor = db.aql.execute("""
            FOR d IN sparta_qra
                FILTER d.evidence_case != null AND d.evidence_case.review_status != null
                FILTER d.evidence_case.review_status NOT IN ["NEEDS_VERIFICATION", "VERIFIED", "REJECTED"]
                RETURN {key: d._key, status: d.evidence_case.review_status}
        """)
        bad = list(cursor)
        add_check("evidence_case", "review_status_valid", len(bad) == 0, len(bad),
                  "0 evidence_cases with invalid review_status",
                  "FILTER d.evidence_case.review_status NOT IN [valid values]", bad)

    # ═══════════════════════════════════════════════════════════════════════════
    # 3. CONTROL SCHEMA VALIDATION
    # ═══════════════════════════════════════════════════════════════════════════

    if db.has_collection("sparta_controls"):
        # Check: controls with empty description
        cursor = db.aql.execute("""
            FOR d IN sparta_controls
                FILTER d.description == null OR LENGTH(d.description) < 10
                RETURN {id: d.control_id, fw: d.source_framework}
        """)
        bad = list(cursor)
        add_check("control_schema", "description_present", len(bad) == 0, len(bad),
                  "0 controls with empty/short description",
                  "FILTER LENGTH(d.description) < 10", bad)

        # Check: controls missing source_framework
        cursor = db.aql.execute("""
            FOR d IN sparta_controls
                FILTER d.source_framework == null OR d.source_framework == ""
                RETURN d.control_id
        """)
        bad = list(cursor)
        add_check("control_schema", "source_framework_present", len(bad) == 0, len(bad),
                  "0 controls missing source_framework",
                  "FILTER d.source_framework == null", bad)

        # Check: duplicate control_ids
        cursor = db.aql.execute("""
            FOR d IN sparta_controls
                COLLECT cid = d.control_id WITH COUNT INTO cnt
                FILTER cnt > 1
                RETURN {control_id: cid, count: cnt}
        """)
        bad = list(cursor)
        add_check("control_schema", "unique_control_ids", len(bad) == 0, len(bad),
                  "0 duplicate control_ids",
                  "COLLECT ... FILTER cnt > 1", bad)

    # ═══════════════════════════════════════════════════════════════════════════
    # 4. EDGE/RELATIONSHIP VALIDATION
    # ═══════════════════════════════════════════════════════════════════════════

    if db.has_collection("sparta_relationships"):
        # Check: collection is edge type (type 3)
        coll = db.collection("sparta_relationships")
        props = coll.properties()
        is_edge = props.get("type") == 3
        add_check("edge_integrity", "is_edge_collection", is_edge,
                  0 if is_edge else 1,
                  "sparta_relationships is edge collection (type 3)",
                  f"collection.properties().type = {props.get('type')}",
                  [{"type": props.get("type"), "edge": props.get("edge")}])

        # Check: edges with null _from/_to (should be 0 for edge collection)
        cursor = db.aql.execute("""
            FOR e IN sparta_relationships
                FILTER e._from == null OR e._to == null
                RETURN e._key
        """)
        bad = list(cursor)
        add_check("edge_integrity", "no_null_endpoints", len(bad) == 0, len(bad),
                  "0 edges with null _from or _to",
                  "FILTER e._from == null OR e._to == null", bad)

        # Check: dangling _from references
        cursor = db.aql.execute("""
            FOR e IN sparta_relationships
                FILTER e._from != null
                LET doc = DOCUMENT(e._from)
                FILTER doc == null
                LIMIT 100
                RETURN {key: e._key, from: e._from}
        """)
        bad = list(cursor)
        add_check("edge_integrity", "no_dangling_from", len(bad) == 0, len(bad),
                  "0 edges with dangling _from reference",
                  "FILTER DOCUMENT(e._from) == null", bad)

        # Check: dangling _to references
        cursor = db.aql.execute("""
            FOR e IN sparta_relationships
                FILTER e._to != null
                LET doc = DOCUMENT(e._to)
                FILTER doc == null
                LIMIT 100
                RETURN {key: e._key, to: e._to}
        """)
        bad = list(cursor)
        add_check("edge_integrity", "no_dangling_to", len(bad) == 0, len(bad),
                  "0 edges with dangling _to reference",
                  "FILTER DOCUMENT(e._to) == null", bad)

        # Check: duplicate edges (same from/to/type)
        cursor = db.aql.execute("""
            FOR e IN sparta_relationships
                COLLECT f = e._from, t = e._to, rt = e.relationship_type WITH COUNT INTO cnt
                FILTER cnt > 1
                LIMIT 50
                RETURN {from: f, to: t, type: rt, count: cnt}
        """)
        bad = list(cursor)
        add_check("edge_integrity", "no_duplicate_edges", len(bad) == 0, len(bad),
                  "0 duplicate edges (same from/to/type)",
                  "COLLECT ... FILTER cnt > 1", bad)

    # ═══════════════════════════════════════════════════════════════════════════
    # 5. CROSS-REFERENCE INTEGRITY
    # ═══════════════════════════════════════════════════════════════════════════

    if db.has_collection("sparta_qra") and db.has_collection("sparta_controls"):
        # Check: QRAs referencing non-existent controls
        cursor = db.aql.execute("""
            LET control_ids = (FOR c IN sparta_controls RETURN c.control_id)
            FOR d IN sparta_qra
                LET cid = d.source_control_id != null ? d.source_control_id : d.control_id
                FILTER cid != null AND cid NOT IN control_ids
                // Exclude CVE IDs which are valid but may not be in controls
                FILTER !STARTS_WITH(cid, "CVE-")
                LIMIT 100
                RETURN {key: d._key, control_id: cid}
        """)
        bad = list(cursor)
        add_check("cross_reference", "qra_control_exists", len(bad) == 0, len(bad),
                  "0 QRAs referencing non-existent controls",
                  "FILTER source_control_id NOT IN control_ids", bad)

    # ═══════════════════════════════════════════════════════════════════════════
    # 6. ORPHAN DETECTION
    # ═══════════════════════════════════════════════════════════════════════════

    if db.has_collection("sparta_controls") and db.has_collection("sparta_qra"):
        # Check: controls with no QRAs (by framework)
        cursor = db.aql.execute("""
            LET qra_control_ids = (
                FOR d IN sparta_qra
                    LET cid = d.source_control_id != null ? d.source_control_id : d.control_id
                    RETURN DISTINCT cid
            )
            FOR c IN sparta_controls
                FILTER c.control_id NOT IN qra_control_ids
                COLLECT fw = c.source_framework WITH COUNT INTO cnt
                SORT cnt DESC
                RETURN {framework: fw, orphan_count: cnt}
        """)
        orphans_by_fw = list(cursor)
        total_orphans = sum(o["orphan_count"] for o in orphans_by_fw)
        add_check("orphan_detection", "controls_without_qras", True, total_orphans,
                  "Audit: controls without QRAs by framework",
                  "FILTER c.control_id NOT IN qra_control_ids", orphans_by_fw)

    # ═══════════════════════════════════════════════════════════════════════════
    # 7. INDEX & VIEW HEALTH
    # ═══════════════════════════════════════════════════════════════════════════

    if db.has_collection("sparta_qra"):
        # Check: vector index exists
        coll = db.collection("sparta_qra")
        indexes = coll.indexes()
        vector_idx = [i for i in indexes if i.get("type") == "vector"]
        has_vector = len(vector_idx) > 0
        add_check("index_health", "vector_index_exists", has_vector,
                  0 if has_vector else 1,
                  "Vector index exists on sparta_qra",
                  "collection.indexes() type='vector'",
                  [{"index": i.get("name"), "fields": i.get("fields")} for i in vector_idx])

        # Check: vector index dimension
        if vector_idx:
            params = vector_idx[0].get("params", {})
            dim = params.get("dimension", 0)
            correct_dim = dim == 384
            add_check("index_health", "vector_index_384dim", correct_dim,
                      0 if correct_dim else 1,
                      "Vector index dimension is 384",
                      f"params.dimension = {dim}",
                      [{"dimension": dim}])

    # Check: ArangoSearch views exist
    try:
        views = list(db.views())
        view_names = [v["name"] for v in views]
        has_unified = "sparta_unified_view" in view_names or "unified_search_view" in view_names
        add_check("index_health", "search_view_exists", has_unified,
                  0 if has_unified else 1,
                  "ArangoSearch view exists",
                  "db.views()",
                  view_names[:5])
    except Exception:
        add_check("index_health", "search_view_exists", False, 1,
                  "ArangoSearch view exists", "db.views() failed", [])

    # ═══════════════════════════════════════════════════════════════════════════
    # 8. COVERAGE ANALYSIS
    # ═══════════════════════════════════════════════════════════════════════════

    if db.has_collection("sparta_qra") and db.has_collection("sparta_controls"):
        # QRA coverage by framework
        cursor = db.aql.execute("""
            LET framework_controls = (
                FOR c IN sparta_controls
                    COLLECT fw = c.source_framework WITH COUNT INTO cnt
                    RETURN {framework: fw, controls: cnt}
            )
            LET framework_qras = (
                FOR d IN sparta_qra
                    LET cid = d.source_control_id != null ? d.source_control_id : d.control_id
                    COLLECT cat = d.category WITH COUNT INTO cnt
                    RETURN {category: cat, qras: cnt}
            )
            RETURN {controls: framework_controls, qras: framework_qras}
        """)
        coverage = list(cursor)[0]
        add_check("coverage", "framework_coverage", True, 0,
                  "QRA coverage by framework (audit)",
                  "COLLECT framework/category",
                  {"controls": coverage["controls"], "qras": coverage["qras"]})

    # ═══════════════════════════════════════════════════════════════════════════
    # 9. URL KNOWLEDGE VALIDATION
    # ═══════════════════════════════════════════════════════════════════════════

    if db.has_collection("sparta_url_knowledge"):
        # Check: URL knowledge with embeddings
        cursor = db.aql.execute("""
            LET total = LENGTH(sparta_url_knowledge)
            LET with_emb = LENGTH(FOR d IN sparta_url_knowledge FILTER d.embedding != null AND LENGTH(d.embedding) == 384 RETURN 1)
            RETURN {total: total, with_embedding: with_emb}
        """)
        result = list(cursor)[0]
        pct = round(result["with_embedding"] * 100 / result["total"], 1) if result["total"] > 0 else 0
        add_check("url_knowledge", "embeddings_complete", pct >= 99,
                  result["total"] - result["with_embedding"],
                  f"≥99% URL knowledge has embeddings ({pct}%)",
                  "FILTER LENGTH(d.embedding) == 384",
                  [{"total": result["total"], "with_embedding": result["with_embedding"], "pct": pct}])

    # ═══════════════════════════════════════════════════════════════════════════
    # 10. LESSONS COLLECTION VALIDATION
    # ═══════════════════════════════════════════════════════════════════════════

    if db.has_collection("lessons"):
        # Check: lessons with embeddings
        cursor = db.aql.execute("""
            LET total = LENGTH(lessons)
            LET with_emb = LENGTH(FOR d IN lessons FILTER d.embedding != null AND LENGTH(d.embedding) == 384 RETURN 1)
            RETURN {total: total, with_embedding: with_emb}
        """)
        result = list(cursor)[0]
        pct = round(result["with_embedding"] * 100 / result["total"], 1) if result["total"] > 0 else 0
        add_check("lessons", "embeddings_complete", pct >= 99,
                  result["total"] - result["with_embedding"],
                  f"≥99% lessons have embeddings ({pct}%)",
                  "FILTER LENGTH(d.embedding) == 384",
                  [{"total": result["total"], "with_embedding": result["with_embedding"], "pct": pct}])

    return report


app = typer.Typer(help="ArangoDB maintenance")

# Global state for --json flag
_json_output = False


@app.callback()
def main_callback(
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    global _json_output
    _json_output = as_json


@app.command()
def check():
    """Run all health checks."""
    db = get_db()
    report = MaintenanceReport()

    print("[ops-arango] Running health checks...")

    emb = check_embeddings(db)
    report.checks["embeddings"] = {
        "contract": "arango-never-stores-embeddings",
        "violations": emb["violation_count"],
        "total": emb["total"]
    }
    if emb["violation_count"]:
        report.status = "warning"
        report.recommendations.append(
            f"{emb['violation_count']} docs hold embedding arrays in Arango "
            "(contract: Qdrant is the only vector store); "
            "run memory repo's migrate_arango_embeddings_to_qdrant.py"
        )

    dups = check_duplicates(db)
    report.checks["duplicates"] = {
        "found": dups["found"],
        "clusters": len(dups["clusters"])
    }
    if dups["found"] > 0:
        report.status = "warning"
        report.recommendations.append(f"Review {len(dups['clusters'])} duplicate clusters")

    orphs = check_orphans(db)
    report.checks["orphans"] = {
        "edges": len(orphs["orphaned_edges"])
    }
    if orphs["orphaned_edges"]:
        report.status = "warning"
        report.recommendations.append(f"Run 'orphans --fix' to remove {len(orphs['orphaned_edges'])} orphaned edges")

    integ = check_integrity(db)
    report.checks["integrity"] = {
        "errors": len(integ["errors"]),
        "checked": integ["checked"]
    }
    if integ["errors"]:
        report.status = "critical"
        report.recommendations.append(f"Fix {len(integ['errors'])} integrity errors")

    stats = get_stats(db)
    report.checks["stats"] = {
        "total_documents": stats["total_documents"],
        "total_size_mb": round(stats["total_size_bytes"] / 1024 / 1024, 2)
    }

    if _json_output:
        print(report.to_json())
    else:
        print(f"\nStatus: {report.status.upper()}")
        print(f"Documents: {stats['total_documents']}")
        print(f"Size: {round(stats['total_size_bytes'] / 1024 / 1024, 2)} MB")
        print(f"Embedding-array contract violations: {emb['violation_count']}")
        print(f"Duplicate clusters: {len(dups['clusters'])}")
        print(f"Orphaned edges: {len(orphs['orphaned_edges'])}")
        print(f"Integrity errors: {len(integ['errors'])}")
        if report.recommendations:
            print("\nRecommendations:")
            for rec in report.recommendations:
                print(f"  - {rec}")


@app.command()
def embeddings(
    fix: bool = typer.Option(False, help="Refused: Qdrant is the only vector store; migration is owned by the memory repo"),
    scope: Optional[str] = typer.Option(None, help="Filter collections by prefix (e.g., 'sparta')"),
):
    """Report docs violating the contract by holding embedding arrays in Arango."""
    db = get_db()

    scope_msg = f" (scope: {scope})" if scope else ""
    print(f"[ops-arango] Checking embedding-array contract{scope_msg}...")
    result = check_embeddings(db, fix=fix, scope=scope)

    if _json_output:
        print(json.dumps(result, indent=2))
    else:
        print(f"Total documents: {result['total']}")
        print(f"Embedding-array contract violations: {result['violation_count']}")
        if result.get("fix_refused"):
            print("Fix refused: migration to Qdrant is owned by the memory repo")
        if result.get("violations"):
            print("\nViolations (sample):")
            for doc in result["violations"][:10]:
                print(f"  {doc['collection']}/{doc['_key']}: {doc.get('preview', '')[:50]}")
            if result["violation_count"] > 10:
                print(f"  ... {result['violation_count']} total")


@app.command()
def duplicates(
    merge: bool = typer.Option(False, help="Merge duplicates (not implemented)"),
):
    """Detect duplicate lessons."""
    db = get_db()

    print("[ops-arango] Checking duplicates...")
    result = check_duplicates(db, report_only=not merge)

    if _json_output:
        print(json.dumps(result, indent=2))
    else:
        print(f"Duplicate documents: {result['found']}")
        print(f"Clusters: {len(result['clusters'])}")
        if result["clusters"]:
            print("\nClusters:")
            for cluster in result["clusters"][:5]:
                print(f"  '{cluster['title'][:50]}': {cluster['count']} copies ({', '.join(cluster['keys'][:3])})")
            if len(result["clusters"]) > 5:
                print(f"  ... and {len(result['clusters']) - 5} more clusters")


@app.command()
def orphans(
    fix: bool = typer.Option(False, help="Delete orphaned edges"),
):
    """Find/fix orphaned edges."""
    db = get_db()

    print("[ops-arango] Checking orphaned edges...")
    result = check_orphans(db, fix=fix)

    if _json_output:
        print(json.dumps(result, indent=2))
    else:
        print(f"Orphaned edges: {len(result['orphaned_edges'])}")
        if fix:
            print(f"Fixed: {result['fixed']}")
        if result["orphaned_edges"] and not fix:
            print("\nOrphans:")
            for edge in result["orphaned_edges"][:10]:
                issue = "from missing" if edge["from_missing"] else "to missing"
                print(f"  {edge['collection']}/{edge['_key']}: {issue}")
            if len(result["orphaned_edges"]) > 10:
                print(f"  ... and {len(result['orphaned_edges']) - 10} more")


@app.command()
def integrity():
    """Verify referential integrity."""
    db = get_db()

    print("[ops-arango] Checking integrity...")
    result = check_integrity(db)

    if _json_output:
        print(json.dumps(result, indent=2))
    else:
        print(f"Documents checked: {result['checked']}")
        print(f"Errors: {len(result['errors'])}")
        if result["errors"]:
            print("\nErrors:")
            for err in result["errors"][:10]:
                print(f"  {err['type']}: {err}")
            if len(result["errors"]) > 10:
                print(f"  ... and {len(result['errors']) - 10} more")


@app.command()
def stats():
    """Show collection statistics."""
    db = get_db()

    print("[ops-arango] Gathering stats...")
    result = get_stats(db)

    if _json_output:
        print(json.dumps(result, indent=2))
    else:
        print(f"\nTotal documents: {result['total_documents']}")
        print(f"Total size: {round(result['total_size_bytes'] / 1024 / 1024, 2)} MB")
        print("\nCollections:")
        for name, coll_stats in sorted(result["collections"].items(), key=lambda x: x[1].get("count", 0), reverse=True):
            if "error" in coll_stats:
                print(f"  {name}: ERROR")
            else:
                print(f"  {name}: {coll_stats['count']} docs ({round(coll_stats['size_bytes'] / 1024, 1)} KB)")


@app.command()
def full(
    fix: bool = typer.Option(False, help="Apply fixes"),
):
    """Run full maintenance cycle."""
    db = get_db()
    embedding_service = os.environ.get("EMBEDDING_SERVICE_URL")
    dry_run = os.environ.get("DRY_RUN", "0") == "1"

    print("[ops-arango] Running full maintenance...")
    report = MaintenanceReport()

    print("\n[1/4] Orphaned edges...")
    orphs = check_orphans(db, fix=(fix and not dry_run))
    report.checks["orphans"] = {"edges": len(orphs["orphaned_edges"]), "fixed": orphs["fixed"]}

    print("[2/4] Embedding-array contract...")
    emb = check_embeddings(db)
    report.checks["embeddings"] = {"violations": emb["violation_count"], "fixed": 0}

    print("[3/4] Duplicates...")
    dups = check_duplicates(db)
    report.checks["duplicates"] = {"found": dups["found"], "clusters": len(dups["clusters"])}

    print("[4/4] Integrity...")
    integ = check_integrity(db)
    report.checks["integrity"] = {"errors": len(integ["errors"])}

    if integ["errors"]:
        report.status = "critical"
    elif orphs["orphaned_edges"] or emb["violation_count"] or dups["found"]:
        report.status = "warning"

    if _json_output:
        print(report.to_json())
    else:
        print(f"\n{'='*40}")
        print(f"Status: {report.status.upper()}")
        print(f"Orphans: {len(orphs['orphaned_edges'])} (fixed: {orphs['fixed']})")
        print(f"Embeddings: {len(emb['missing'])} missing (fixed: {emb['fixed']})")
        print(f"Duplicates: {dups['found']} in {len(dups['clusters'])} clusters")
        print(f"Integrity: {len(integ['errors'])} errors")


@app.command("url-coverage")
def url_coverage(
    output: str = typer.Option("", help="Path to save JSON output"),
):
    """Audit URL content coverage across SPARTA collections."""
    db = get_db()

    print("[ops-arango] Auditing URL content coverage...")

    # 1. Basic counts
    total_urls = db.collection("sparta_urls").count() if db.has_collection("sparta_urls") else 0

    fetched_ok = next(db.aql.execute(
        "FOR d IN sparta_url_content "
        "FILTER d.status_code == 200 "
        "COLLECT WITH COUNT INTO c RETURN c"
    )) if db.has_collection("sparta_url_content") else 0

    chunk_count_url_extract = next(db.aql.execute(
        "FOR d IN datalake_chunks "
        "FILTER d.content_type == 'url_extract' "
        "COLLECT WITH COUNT INTO c RETURN c"
    )) if db.has_collection("datalake_chunks") else 0

    # Distinct URLs with at least one datalake chunk
    has_chunks = next(db.aql.execute(
        "FOR d IN datalake_chunks "
        "FILTER d.content_type == 'url_extract' "
        "COLLECT uid = d.source_meta.url_id WITH COUNT INTO c "
        "COLLECT WITH COUNT INTO total RETURN total"
    )) if db.has_collection("datalake_chunks") else 0

    # 2. Per-framework URL coverage
    framework_rows = list(db.aql.execute("""
        FOR ctrl IN sparta_controls
            LET urls = (
                FOR cu IN sparta_control_urls
                    FILTER cu.control_id == ctrl.control_id
                    RETURN cu.url_id
            )
            LET ok_urls = (
                FOR uid IN urls
                    FOR uc IN sparta_url_content
                        FILTER uc.url_id == uid AND uc.status_code == 200
                        RETURN uid
            )
            LET chunked_urls = (
                FOR uid IN urls
                    FOR ch IN datalake_chunks
                        FILTER ch.content_type == 'url_extract'
                           AND ch.source_meta.url_id == uid
                        COLLECT u = uid WITH COUNT INTO n
                        RETURN u
            )
            COLLECT fw = ctrl.source_framework
            AGGREGATE
                total_controls   = SUM(1),
                controls_w_urls  = SUM(LENGTH(urls) > 0 ? 1 : 0),
                total_urls_agg   = SUM(LENGTH(urls)),
                fetched_ok_agg   = SUM(LENGTH(ok_urls)),
                has_chunks_agg   = SUM(LENGTH(chunked_urls) > 0 ? 1 : 0)
            RETURN {
                framework:          fw,
                total_controls:     total_controls,
                controls_with_urls: controls_w_urls,
                fetched_ok:         fetched_ok_agg,
                total_urls:         total_urls_agg,
                has_chunks:         has_chunks_agg,
                coverage_pct:       total_controls > 0
                    ? ROUND(controls_w_urls * 100.0 / total_controls * 100) / 100
                    : 0
            }
    """, ttl=600, batch_size=50))

    # 3. Techniques with vs without URL content
    tech_counts = list(db.aql.execute("""
        FOR ctrl IN sparta_controls
            LET has = (
                FOR cu IN sparta_control_urls
                    FILTER cu.control_id == ctrl.control_id
                    FOR uc IN sparta_url_content
                        FILTER uc.url_id == cu.url_id AND uc.status_code == 200
                        LIMIT 1
                        RETURN 1
            )
            COLLECT has_content = LENGTH(has) > 0 WITH COUNT INTO c
            RETURN {has_content, c}
    """, ttl=600))

    techniques_with = 0
    techniques_without = 0
    for row in tech_counts:
        if row["has_content"]:
            techniques_with = row["c"]
        else:
            techniques_without = row["c"]

    # 4. Count files on disk (DB count + sample verification)
    file_count_db = next(db.aql.execute(
        "FOR d IN sparta_url_content "
        "FILTER d.status_code == 200 AND d.file_path != null "
        "COLLECT WITH COUNT INTO c RETURN c"
    )) if db.has_collection("sparta_url_content") else 0

    sample_paths = list(db.aql.execute(
        "FOR d IN sparta_url_content "
        "FILTER d.status_code == 200 AND d.file_path != null "
        "LIMIT 100 "
        "RETURN d.file_path"
    )) if db.has_collection("sparta_url_content") else []
    sample_exists = sum(1 for p in sample_paths if p and os.path.isfile(p))

    # 5. Sample techniques with URL content
    sample_techniques = list(db.aql.execute("""
        FOR ctrl IN sparta_controls
            SORT RAND()
            LET urls = (
                FOR cu IN sparta_control_urls
                    FILTER cu.control_id == ctrl.control_id
                    FOR uc IN sparta_url_content
                        FILTER uc.url_id == cu.url_id AND uc.status_code == 200
                        RETURN cu.url_id
            )
            FILTER LENGTH(urls) > 0
            LET chunks = (
                FOR uid IN urls
                    FOR ch IN datalake_chunks
                        FILTER ch.content_type == 'url_extract'
                           AND ch.source_meta.url_id == uid
                        COLLECT WITH COUNT INTO n
                        RETURN n
            )
            LIMIT 10
            RETURN {
                technique_id:     ctrl.control_id,
                name:             ctrl.name,
                source_framework: ctrl.source_framework,
                url_count:        LENGTH(urls),
                chunk_count:      LENGTH(chunks) > 0 ? chunks[0] : 0
            }
    """, ttl=600))

    result = {
        "total_urls": total_urls,
        "fetched_ok": fetched_ok,
        "has_chunks": has_chunks,
        "frameworks": sorted(framework_rows, key=lambda r: r["framework"]),
        "techniques_with_content": techniques_with,
        "techniques_without_content": techniques_without,
        "chunk_count_url_extract": chunk_count_url_extract,
        "fetched_files_on_disk": file_count_db,
        "disk_sample_check": f"{sample_exists}/{len(sample_paths)} sampled files exist on disk",
        "sample_techniques": sample_techniques,
    }

    result_json = json.dumps(result, indent=2)

    if output:
        from pathlib import Path
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(result_json)
        print(f"[ops-arango] Saved to {output}")

    if _json_output or output:
        print(result_json)
    else:
        print(f"\n{'='*50}")
        print(f"Total URLs:                {total_urls}")
        print(f"Fetched OK (200):          {fetched_ok}")
        print(f"URLs with chunks:          {has_chunks}")
        print(f"Chunk count (url_extract): {chunk_count_url_extract}")
        print(f"Techniques with content:   {techniques_with}")
        print(f"Techniques without:        {techniques_without}")
        print(f"Files on disk (DB):        {file_count_db}")
        print(f"Disk sample:               {sample_exists}/{len(sample_paths)} exist")
        print(f"\nFrameworks:")
        for fw in sorted(framework_rows, key=lambda r: r["framework"]):
            print(f"  {fw['framework']:20s}  controls={fw['total_controls']:5d}  "
                  f"with_urls={fw['controls_with_urls']:5d}  "
                  f"fetched={fw['fetched_ok']:5d}  "
                  f"coverage={fw['coverage_pct']:.1f}%")


def format_health_report_markdown(report: dict) -> str:
    """Format health check report as markdown."""
    lines = []
    lines.append(f"# SPARTA Data Health Report")
    lines.append(f"")
    lines.append(f"**Generated:** {report['timestamp']}")
    lines.append(f"**Overall Status:** {'✅' if report['status'] == 'healthy' else '⚠️' if report['status'] == 'warning' else '❌'} {report['status'].upper()}")
    lines.append(f"")
    lines.append(f"## Summary")
    lines.append(f"")
    lines.append(f"| Metric | Count |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Passed | {report['summary']['passed']} |")
    lines.append(f"| Warnings | {report['summary']['warnings']} |")
    lines.append(f"| Failed | {report['summary']['failed']} |")
    lines.append(f"")

    for cat_name, cat_data in report["categories"].items():
        status_icon = "✅" if cat_data["status"] == "passed" else "⚠️" if cat_data["status"] == "warning" else "❌"
        lines.append(f"## {status_icon} {cat_name.replace('_', ' ').title()}")
        lines.append(f"")
        lines.append(f"| Check | Status | Count | Expected |")
        lines.append(f"|-------|--------|-------|----------|")

        for check in cat_data["checks"]:
            s_icon = "✅" if check["status"] == "passed" else "⚠️" if check["status"] == "warning" else "❌"
            lines.append(f"| {check['name']} | {s_icon} | {check['count']} | {check['expected']} |")

        lines.append(f"")

        # Show details for failed/warning checks
        for check in cat_data["checks"]:
            if check["status"] != "passed" and check.get("details"):
                lines.append(f"<details>")
                lines.append(f"<summary><strong>{check['name']}</strong> — {check['count']} issues</summary>")
                lines.append(f"")
                lines.append(f"```")
                lines.append(f"Query hint: {check.get('query_hint', 'N/A')}")
                lines.append(f"")
                for d in check["details"][:10]:
                    lines.append(f"  {d}")
                if len(check.get("details", [])) > 10:
                    lines.append(f"  ... and {len(check['details']) - 10} more")
                lines.append(f"```")
                lines.append(f"</details>")
                lines.append(f"")

    return "\n".join(lines)


@app.command("health-check")
def health_check_cmd(
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Save report to file (.json or .md)"),
    markdown: bool = typer.Option(False, "--markdown", "-m", help="Output as markdown"),
):
    """Comprehensive SPARTA data integrity validation.

    Runs 26 deterministic checks across 10 categories:
    - qra_schema (7): question, reasoning, evidence, control_id, category, verdict, embedding
    - evidence_case (4): present, required_fields, crosswalk_chains, review_status
    - control_schema (3): description, source_framework, unique_ids
    - edge_integrity (4): null endpoints, dangling _from, dangling _to, duplicates
    - cross_reference (1): QRA→control exists
    - orphan_detection (1): controls without QRAs
    - index_health (3): vector index exists, 384-dim, search view exists
    - coverage (1): QRA coverage by framework
    - url_knowledge (1): embedding completeness
    - lessons (1): embedding completeness
    """
    db = get_db()
    print("[ops-arango] Running comprehensive SPARTA health check...")
    report = sparta_health_check(db)

    if markdown or (output and output.endswith(".md")):
        formatted = format_health_report_markdown(report)
        if output:
            from pathlib import Path
            Path(output).write_text(formatted)
            print(f"[ops-arango] Saved markdown report to {output}")
        else:
            print(formatted)
    elif _json_output or (output and output.endswith(".json")):
        result_json = json.dumps(report, indent=2)
        if output:
            from pathlib import Path
            Path(output).write_text(result_json)
            print(f"[ops-arango] Saved JSON report to {output}")
        else:
            print(result_json)
    else:
        # Default: compact terminal output
        print(f"\n{'='*60}")
        print(f"SPARTA Data Health: {report['status'].upper()}")
        print(f"{'='*60}")
        print(f"Passed: {report['summary']['passed']}  |  Warnings: {report['summary']['warnings']}  |  Failed: {report['summary']['failed']}")
        print(f"")

        for cat_name, cat_data in report["categories"].items():
            status_icon = "✓" if cat_data["status"] == "passed" else "!" if cat_data["status"] == "warning" else "✗"
            print(f"[{status_icon}] {cat_name}")
            for check in cat_data["checks"]:
                if check["status"] != "passed":
                    s_icon = "!" if check["status"] == "warning" else "✗"
                    print(f"    [{s_icon}] {check['name']}: {check['count']} ({check['expected']})")

        if report["status"] != "healthy":
            print(f"\nRun with --json or --markdown for full details.")


if __name__ == "__main__":
    app()
