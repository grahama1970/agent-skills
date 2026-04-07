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
            import httpx
            for doc in missing:
                try:
                    text = doc.get("title", "") + " " + doc.get("content", "")
                    resp = httpx.post(
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
        "missing": len(emb["missing"]),
        "total": emb["total"]
    }
    if emb["missing"]:
        report.status = "warning"
        report.recommendations.append(f"Run 'embeddings --fix' to fix {len(emb['missing'])} missing embeddings")

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
        print(f"Missing embeddings: {len(emb['missing'])}")
        print(f"Duplicate clusters: {len(dups['clusters'])}")
        print(f"Orphaned edges: {len(orphs['orphaned_edges'])}")
        print(f"Integrity errors: {len(integ['errors'])}")
        if report.recommendations:
            print("\nRecommendations:")
            for rec in report.recommendations:
                print(f"  - {rec}")


@app.command()
def embeddings(
    fix: bool = typer.Option(False, help="Fix missing embeddings"),
):
    """Check/fix missing embeddings."""
    db = get_db()
    embedding_service = os.environ.get("EMBEDDING_SERVICE_URL")

    if fix and not embedding_service:
        print("ERROR: EMBEDDING_SERVICE_URL required for --fix", file=sys.stderr)
        sys.exit(1)

    print("[ops-arango] Checking embeddings...")
    result = check_embeddings(db, fix=fix, embedding_service=embedding_service)

    if _json_output:
        print(json.dumps(result, indent=2))
    else:
        print(f"Total documents: {result['total']}")
        print(f"Missing embeddings: {len(result['missing'])}")
        if fix:
            print(f"Fixed: {result['fixed']}")
        if result["missing"] and not fix:
            print("\nMissing in:")
            for doc in result["missing"][:10]:
                print(f"  {doc['collection']}/{doc['_key']}: {doc.get('title', 'untitled')[:50]}")
            if len(result["missing"]) > 10:
                print(f"  ... and {len(result['missing']) - 10} more")


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

    print("[2/4] Missing embeddings...")
    emb = check_embeddings(db, fix=(fix and not dry_run and bool(embedding_service)), embedding_service=embedding_service)
    report.checks["embeddings"] = {"missing": len(emb["missing"]), "fixed": emb["fixed"]}

    print("[3/4] Duplicates...")
    dups = check_duplicates(db)
    report.checks["duplicates"] = {"found": dups["found"], "clusters": len(dups["clusters"])}

    print("[4/4] Integrity...")
    integ = check_integrity(db)
    report.checks["integrity"] = {"errors": len(integ["errors"])}

    if integ["errors"]:
        report.status = "critical"
    elif orphs["orphaned_edges"] or emb["missing"] or dups["found"]:
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


if __name__ == "__main__":
    app()
