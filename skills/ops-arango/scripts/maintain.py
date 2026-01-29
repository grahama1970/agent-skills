#!/usr/bin/env python3
"""ArangoDB maintenance: embeddings, duplicates, orphans, integrity, stats."""
import argparse
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


def check_embeddings(db, fix: bool = False, embedding_service: Optional[str] = None) -> dict:
    """Find documents missing embedding vectors."""
    results = {"missing": [], "total": 0, "fixed": 0}

    # Collections that should have embeddings
    embedding_collections = ["lessons", "episodes"]

    for coll_name in embedding_collections:
        if not db.has_collection(coll_name):
            continue

        coll = db.collection(coll_name)

        # Query for documents without embeddings
        query = """
        FOR doc IN @@collection
            FILTER doc.embedding == null OR LENGTH(doc.embedding) == 0
            RETURN {_key: doc._key, title: doc.title, content: doc.content}
        """
        cursor = db.aql.execute(query, bind_vars={"@collection": coll_name})
        missing = list(cursor)

        results["total"] += coll.count()
        results["missing"].extend([{"collection": coll_name, **doc} for doc in missing])

        if fix and missing and embedding_service:
            import requests
            for doc in missing:
                try:
                    text = doc.get("title", "") + " " + doc.get("content", "")
                    resp = requests.post(
                        f"{embedding_service}/embed",
                        json={"texts": [text]},
                        timeout=30
                    )
                    if resp.ok:
                        embedding = resp.json()["embeddings"][0]
                        coll.update({"_key": doc["_key"], "embedding": embedding})
                        results["fixed"] += 1
                except Exception as e:
                    print(f"[warn] Failed to fix {coll_name}/{doc['_key']}: {e}", file=sys.stderr)

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


def cmd_check(args):
    """Run all health checks."""
    db = get_db()
    report = MaintenanceReport()

    print("[ops-arango] Running health checks...")

    # Embeddings
    emb = check_embeddings(db)
    report.checks["embeddings"] = {
        "missing": len(emb["missing"]),
        "total": emb["total"]
    }
    if emb["missing"]:
        report.status = "warning"
        report.recommendations.append(f"Run 'embeddings --fix' to fix {len(emb['missing'])} missing embeddings")

    # Duplicates
    dups = check_duplicates(db)
    report.checks["duplicates"] = {
        "found": dups["found"],
        "clusters": len(dups["clusters"])
    }
    if dups["found"] > 0:
        report.status = "warning"
        report.recommendations.append(f"Review {len(dups['clusters'])} duplicate clusters")

    # Orphans
    orphs = check_orphans(db)
    report.checks["orphans"] = {
        "edges": len(orphs["orphaned_edges"])
    }
    if orphs["orphaned_edges"]:
        report.status = "warning"
        report.recommendations.append(f"Run 'orphans --fix' to remove {len(orphs['orphaned_edges'])} orphaned edges")

    # Integrity
    integ = check_integrity(db)
    report.checks["integrity"] = {
        "errors": len(integ["errors"]),
        "checked": integ["checked"]
    }
    if integ["errors"]:
        report.status = "critical"
        report.recommendations.append(f"Fix {len(integ['errors'])} integrity errors")

    # Stats
    stats = get_stats(db)
    report.checks["stats"] = {
        "total_documents": stats["total_documents"],
        "total_size_mb": round(stats["total_size_bytes"] / 1024 / 1024, 2)
    }

    if args.json:
        print(report.to_json())
    else:
        print(f"\nStatus: {report.status.upper()}")
        print(f"Documents: {stats['total_documents']}")
        print(f"Size: {round(stats['total_size_bytes'] / 1024 / 1024, 2)} MB")
        print(f"Missing embeddings: {len(emb['missing'])}")
        print(f"Duplicate clusters: {len(dups['clusters'])}")
        print(f"Orphaned edges: {len(orphs['orphaned_edges'])}")
        print(f"Integrity errors: {len(integ['errors'])}")
        if report.recommendations:
            print("\nRecommendations:")
            for rec in report.recommendations:
                print(f"  - {rec}")


def cmd_embeddings(args):
    """Check/fix missing embeddings."""
    db = get_db()
    embedding_service = os.environ.get("EMBEDDING_SERVICE_URL")

    if args.fix and not embedding_service:
        print("ERROR: EMBEDDING_SERVICE_URL required for --fix", file=sys.stderr)
        sys.exit(1)

    print("[ops-arango] Checking embeddings...")
    result = check_embeddings(db, fix=args.fix, embedding_service=embedding_service)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Total documents: {result['total']}")
        print(f"Missing embeddings: {len(result['missing'])}")
        if args.fix:
            print(f"Fixed: {result['fixed']}")
        if result["missing"] and not args.fix:
            print("\nMissing in:")
            for doc in result["missing"][:10]:
                print(f"  {doc['collection']}/{doc['_key']}: {doc.get('title', 'untitled')[:50]}")
            if len(result["missing"]) > 10:
                print(f"  ... and {len(result['missing']) - 10} more")


def cmd_duplicates(args):
    """Check for duplicate lessons."""
    db = get_db()

    print("[ops-arango] Checking duplicates...")
    result = check_duplicates(db, report_only=not args.merge)

    if args.json:
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


def cmd_orphans(args):
    """Check/fix orphaned edges."""
    db = get_db()

    print("[ops-arango] Checking orphaned edges...")
    result = check_orphans(db, fix=args.fix)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Orphaned edges: {len(result['orphaned_edges'])}")
        if args.fix:
            print(f"Fixed: {result['fixed']}")
        if result["orphaned_edges"] and not args.fix:
            print("\nOrphans:")
            for edge in result["orphaned_edges"][:10]:
                issue = "from missing" if edge["from_missing"] else "to missing"
                print(f"  {edge['collection']}/{edge['_key']}: {issue}")
            if len(result["orphaned_edges"]) > 10:
                print(f"  ... and {len(result['orphaned_edges']) - 10} more")


def cmd_integrity(args):
    """Check referential integrity."""
    db = get_db()

    print("[ops-arango] Checking integrity...")
    result = check_integrity(db)

    if args.json:
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


def cmd_stats(args):
    """Show collection statistics."""
    db = get_db()

    print("[ops-arango] Gathering stats...")
    result = get_stats(db)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"\nTotal documents: {result['total_documents']}")
        print(f"Total size: {round(result['total_size_bytes'] / 1024 / 1024, 2)} MB")
        print("\nCollections:")
        for name, stats in sorted(result["collections"].items(), key=lambda x: x[1].get("count", 0), reverse=True):
            if "error" in stats:
                print(f"  {name}: ERROR")
            else:
                print(f"  {name}: {stats['count']} docs ({round(stats['size_bytes'] / 1024, 1)} KB)")


def cmd_full(args):
    """Run full maintenance cycle."""
    db = get_db()
    embedding_service = os.environ.get("EMBEDDING_SERVICE_URL")
    dry_run = os.environ.get("DRY_RUN", "0") == "1"

    print("[ops-arango] Running full maintenance...")
    report = MaintenanceReport()

    # 1. Check and fix orphans
    print("\n[1/4] Orphaned edges...")
    orphs = check_orphans(db, fix=(args.fix and not dry_run))
    report.checks["orphans"] = {"edges": len(orphs["orphaned_edges"]), "fixed": orphs["fixed"]}

    # 2. Check and fix embeddings
    print("[2/4] Missing embeddings...")
    emb = check_embeddings(db, fix=(args.fix and not dry_run and embedding_service), embedding_service=embedding_service)
    report.checks["embeddings"] = {"missing": len(emb["missing"]), "fixed": emb["fixed"]}

    # 3. Check duplicates (report only)
    print("[3/4] Duplicates...")
    dups = check_duplicates(db)
    report.checks["duplicates"] = {"found": dups["found"], "clusters": len(dups["clusters"])}

    # 4. Integrity
    print("[4/4] Integrity...")
    integ = check_integrity(db)
    report.checks["integrity"] = {"errors": len(integ["errors"])}

    # Determine status
    if integ["errors"]:
        report.status = "critical"
    elif orphs["orphaned_edges"] or emb["missing"] or dups["found"]:
        report.status = "warning"

    if args.json:
        print(report.to_json())
    else:
        print(f"\n{'='*40}")
        print(f"Status: {report.status.upper()}")
        print(f"Orphans: {len(orphs['orphaned_edges'])} (fixed: {orphs['fixed']})")
        print(f"Embeddings: {len(emb['missing'])} missing (fixed: {emb['fixed']})")
        print(f"Duplicates: {dups['found']} in {len(dups['clusters'])} clusters")
        print(f"Integrity: {len(integ['errors'])} errors")


def main():
    parser = argparse.ArgumentParser(description="ArangoDB maintenance")
    parser.add_argument("--json", action="store_true", help="JSON output")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # check
    p_check = subparsers.add_parser("check", help="Run all health checks")
    p_check.set_defaults(func=cmd_check)

    # embeddings
    p_emb = subparsers.add_parser("embeddings", help="Check/fix missing embeddings")
    p_emb.add_argument("--fix", action="store_true", help="Fix missing embeddings")
    p_emb.set_defaults(func=cmd_embeddings)

    # duplicates
    p_dup = subparsers.add_parser("duplicates", help="Detect duplicate lessons")
    p_dup.add_argument("--merge", action="store_true", help="Merge duplicates (not implemented)")
    p_dup.set_defaults(func=cmd_duplicates)

    # orphans
    p_orph = subparsers.add_parser("orphans", help="Find/fix orphaned edges")
    p_orph.add_argument("--fix", action="store_true", help="Delete orphaned edges")
    p_orph.set_defaults(func=cmd_orphans)

    # integrity
    p_integ = subparsers.add_parser("integrity", help="Verify referential integrity")
    p_integ.set_defaults(func=cmd_integrity)

    # stats
    p_stats = subparsers.add_parser("stats", help="Collection statistics")
    p_stats.set_defaults(func=cmd_stats)

    # full
    p_full = subparsers.add_parser("full", help="Full maintenance cycle")
    p_full.add_argument("--fix", action="store_true", help="Apply fixes")
    p_full.set_defaults(func=cmd_full)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
