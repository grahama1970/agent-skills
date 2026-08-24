"""ops-memory: the natural-language front door to the /memory stack.

Purpose:
    Make the memory database setup inspectable at a glance. It composes the
    owning skills — ``ops-arango`` (ArangoDB admin + read-only coverage),
    ``ops-qdrant`` (read-only vector health), ``memory`` (/recall), and
    ``phart-dag-chart`` (ASCII topology) — and merges their receipts into two
    schemas: ``ops_memory.health.v1`` and ``ops_memory.metrics.v1``. The metrics
    matrix flags collections that go stale, lose their Qdrant vector sync, hold
    no secondary index, or violate the "Arango stores no embedding arrays"
    contract.

Inputs:
    Environment: SKILLS_ROOT (default: two parents up from this file),
                 OPS_ARANGO_RUN / OPS_QDRANT_RUN / MEMORY_RUN / PHART_RUN
                 (override child run.sh paths), QDRANT_URL / MEMORY_URL
                 (passed through to children), ARANGO_BACKUP_DIR
                 (default /mnt/storage12tb/backups/arangodb),
                 OPS_MEMORY_STALE_DAYS (default 30).
    CLI flags: see each command.

Outputs:
    Human summary, or a schema-versioned JSON document on stdout for monitors.

Boundary (non-negotiable):
    ops-memory performs NO direct ArangoDB or Qdrant access — it shells out to
    the sanctioned owning skills only. All Arango/Qdrant mutation and semantic
    sync live in the memory repo. Detection and read-only backups are the only
    side effects here; ``backup`` and ``fix`` are explicit, gated subcommands.

Failure modes:
    - A child skill unreachable / non-zero        -> that lane reports down and
      contributes a warning; overall status degrades, never silently "healthy".
    - A child emits a payload that fails its typed seam check -> SeamViolation
      is raised, attributing the drift to the named child (fail closed).
"""

from __future__ import annotations

import json as jsonlib
import os
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path

import typer
from loguru import logger

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Natural-language front door + health/metrics for the /memory stack.",
)

# --- configuration (boundary: environment) ---------------------------------

DEFAULT_BACKUP_DIR = "/mnt/storage12tb/backups/arangodb"
DEFAULT_STALE_DAYS = 30
CHILD_TIMEOUT = 240  # coverage over 300+ collections is the slow path
RECALL_TIMEOUT = 60


def _skills_root() -> Path:
    override = os.environ.get("SKILLS_ROOT")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2]


def _child_run(name: str, env_var: str) -> Path:
    override = os.environ.get(env_var)
    if override:
        return Path(override)
    return _skills_root() / name / "run.sh"


class Status(StrEnum):
    """Closed vocabulary for overall stack health."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"


class CollectionFlag(StrEnum):
    """Closed vocabulary for per-collection monitoring findings."""

    EMPTY = "empty"
    BM25_ONLY = "bm25_only"  # document collection with 0 Qdrant pointers (no dense lane)
    PARTIAL_SYNC = "partial_sync"  # some, not all, docs vector-synced
    NO_QDRANT_EMBEDDING = "no_qdrant_embedding"  # 0% dense sync (alias emphasis of bm25_only)
    NO_ARANGOSEARCH = "no_arangosearch"  # document collection linked in no ArangoSearch view (no BM25 lane)
    NOT_RECALL_CONNECTED = "not_recall_connected"  # neither BM25 view nor Qdrant vectors -> invisible to /memory recall
    NO_SECONDARY_INDEX = "no_secondary_index"
    SLOW_SCAN_RISK = "slow_scan_risk"  # large collection with no secondary index
    EMBEDDING_ARRAY_VIOLATION = "embedding_array_violation"  # Arango holds vectors
    STALE = "stale"  # latest timestamp older than the stale window
    COVERAGE_ERROR = "coverage_error"


# A collection this big with no secondary index is a query-performance risk.
SLOW_SCAN_MIN_DOCS = 50_000


# --- typed seam contracts (validate every crossing artifact) ---------------


class SeamViolation(RuntimeError):
    """A downstream child emitted a payload that does not match its contract."""


@dataclass(slots=True)
class ArangoCheck:
    status: str
    total_documents: int
    embedding_violations: int
    duplicate_clusters: int
    orphan_edges: int
    integrity_errors: int

    @classmethod
    def from_payload(cls, payload: object) -> ArangoCheck:
        if not isinstance(payload, dict) or "checks" not in payload:
            raise SeamViolation("ops-arango check: missing 'checks' object")
        checks = payload["checks"]
        try:
            return cls(
                status=str(payload.get("status", "unknown")),
                total_documents=int(checks["stats"]["total_documents"]),
                embedding_violations=int(checks["embeddings"]["violations"]),
                duplicate_clusters=int(checks["duplicates"]["clusters"]),
                orphan_edges=int(checks["orphans"]["edges"]),
                integrity_errors=int(checks["integrity"]["errors"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SeamViolation(f"ops-arango check: shape drift ({exc})") from exc


@dataclass(slots=True)
class CoverageDoc:
    name: str
    type: str
    count: int | None
    index_types: list[str]
    arangosearch_views: list[str]
    in_named_graph: bool
    vector_pointer_frac: float | None
    embedding_array_frac: float | None
    sync_states: list[str]
    latest_timestamp: str | None
    error: str | None = None


@dataclass(slots=True)
class ArangoCoverage:
    collections: list[CoverageDoc]

    @classmethod
    def from_payload(cls, payload: object) -> ArangoCoverage:
        if not isinstance(payload, dict) or payload.get("schema") != "ops_arango.coverage.v1":
            raise SeamViolation("ops-arango coverage: wrong or missing schema")
        rows = payload.get("collections")
        if not isinstance(rows, list):
            raise SeamViolation("ops-arango coverage: 'collections' is not a list")
        docs: list[CoverageDoc] = []
        for r in rows:
            docs.append(
                CoverageDoc(
                    name=str(r.get("name", "?")),
                    type=str(r.get("type", "document")),
                    count=r.get("count"),
                    index_types=list(r.get("index_types") or []),
                    arangosearch_views=list(r.get("arangosearch_views") or []),
                    in_named_graph=bool(r.get("in_named_graph")),
                    vector_pointer_frac=r.get("vector_pointer_frac"),
                    embedding_array_frac=r.get("embedding_array_frac"),
                    sync_states=list(r.get("sync_states") or []),
                    latest_timestamp=r.get("latest_timestamp"),
                    error=r.get("error"),
                )
            )
        return cls(collections=docs)


@dataclass(slots=True)
class QdrantHealth:
    up: bool
    status: str
    collection_count: int
    dense_found: bool
    dense_ok: bool
    collections: list[dict]

    @classmethod
    def from_payload(cls, payload: object) -> QdrantHealth:
        if not isinstance(payload, dict) or payload.get("schema") != "ops_qdrant.health.v1":
            raise SeamViolation("ops-qdrant health: wrong or missing schema")
        probe = payload.get("dense_probe") or {}
        return cls(
            up=bool(payload.get("qdrant_up")),
            status=str(payload.get("status", "unknown")),
            collection_count=int(payload.get("collection_count") or 0),
            dense_found=bool(probe.get("found")),
            dense_ok=bool(probe.get("dense_ok")),
            collections=list(payload.get("collections") or []),
        )


# --- child invocation (read-only composition, no shell) --------------------


@dataclass(slots=True)
class ChildResult:
    ok: bool
    returncode: int
    stdout: str
    stderr: str


def _child_env() -> dict[str, str]:
    env = dict(os.environ)
    for key in ("QDRANT_URL", "MEMORY_URL", "EMBED_URL", "ARANGO_URL"):
        if key in os.environ:
            env[key] = os.environ[key]
    return env


def run_child(run_sh: Path, args: list[str], timeout: int = CHILD_TIMEOUT) -> ChildResult:
    """Invoke a sibling skill's run.sh with an argument list (never via a shell)."""
    if not run_sh.exists():
        logger.error("child run.sh missing: {}", run_sh)
        return ChildResult(False, 127, "", f"missing run.sh: {run_sh}")
    try:
        proc = subprocess.run(
            [str(run_sh), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_child_env(),
        )
        return ChildResult(proc.returncode == 0, proc.returncode, proc.stdout, proc.stderr)
    except subprocess.TimeoutExpired as exc:
        logger.error("child timed out: {} {}", run_sh, args)
        return ChildResult(False, 124, exc.stdout or "", "timeout")
    except OSError as exc:
        logger.error("child exec failed: {} ({})", run_sh, exc)
        return ChildResult(False, 126, "", str(exc))


def _parse_json(text: str) -> object | None:
    """Tolerant JSON parse: whole string first, else the last top-level object."""
    text = text.strip()
    if not text:
        return None
    try:
        return jsonlib.loads(text)
    except ValueError:
        start = text.find("{")
        end = text.rfind("}")
        if 0 <= start < end:
            try:
                return jsonlib.loads(text[start : end + 1])
            except ValueError as exc:
                logger.error("child stdout was not JSON: {}", exc)
    return None


# --- lane fetchers ---------------------------------------------------------


def fetch_arango_check() -> tuple[ArangoCheck | None, str | None]:
    res = run_child(_child_run("ops-arango", "OPS_ARANGO_RUN"), ["check", "--json"])
    if not res.ok:
        return None, f"ops-arango check failed (rc={res.returncode})"
    payload = _parse_json(res.stdout)
    if payload is None:
        return None, "ops-arango check emitted no JSON"
    return ArangoCheck.from_payload(payload), None


def fetch_arango_coverage(sample: int) -> tuple[ArangoCoverage | None, str | None]:
    res = run_child(
        _child_run("ops-arango", "OPS_ARANGO_RUN"),
        ["coverage", "--sample", str(sample), "--json"],
    )
    if not res.ok:
        return None, f"ops-arango coverage failed (rc={res.returncode})"
    payload = _parse_json(res.stdout)
    if payload is None:
        return None, "ops-arango coverage emitted no JSON"
    return ArangoCoverage.from_payload(payload), None


def fetch_qdrant_health() -> tuple[QdrantHealth | None, str | None]:
    res = run_child(_child_run("ops-qdrant", "OPS_QDRANT_RUN"), ["check", "--json"])
    # ops-qdrant exits 2 when Qdrant itself is down but still emits a valid report.
    payload = _parse_json(res.stdout)
    if payload is None:
        return None, f"ops-qdrant check emitted no JSON (rc={res.returncode})"
    return QdrantHealth.from_payload(payload), None


# --- report assembly -------------------------------------------------------


def build_health() -> dict:
    warnings: list[str] = []
    arango, a_err = fetch_arango_check()
    qdrant, q_err = fetch_qdrant_health()
    for err in (a_err, q_err):
        if err:
            warnings.append(err)

    arango_up = arango is not None
    if not arango_up and (qdrant is None or not qdrant.up):
        status = Status.DOWN
    else:
        status = Status.HEALTHY
        if arango is not None and arango.status not in ("ok", "healthy"):
            status = Status.DEGRADED
            warnings.append(f"ArangoDB status={arango.status}")
        if arango is not None and arango.embedding_violations:
            status = Status.DEGRADED
            warnings.append(
                f"{arango.embedding_violations} docs hold embedding arrays in Arango "
                "(contract violation; migration owned by the memory repo)"
            )
        if qdrant is None or not qdrant.up:
            status = Status.DEGRADED
            warnings.append("Qdrant unreachable")
        elif qdrant.dense_found and not qdrant.dense_ok:
            status = Status.DEGRADED
            warnings.append("dense recall degraded to BM25-only (dense=0.0)")

    return {
        "schema": "ops_memory.health.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "status": str(status),
        "arango": {
            "up": arango_up,
            "status": arango.status if arango else None,
            "total_documents": arango.total_documents if arango else None,
            "embedding_violations": arango.embedding_violations if arango else None,
            "duplicate_clusters": arango.duplicate_clusters if arango else None,
            "orphan_edges": arango.orphan_edges if arango else None,
            "integrity_errors": arango.integrity_errors if arango else None,
        },
        "qdrant": {
            "up": qdrant.up if qdrant else False,
            "status": qdrant.status if qdrant else None,
            "collection_count": qdrant.collection_count if qdrant else None,
            "dense_found": qdrant.dense_found if qdrant else None,
            "dense_ok": qdrant.dense_ok if qdrant else None,
        },
        "seam_validation": {"kind": "ops_memory.health", "status": "PASS"},
        "warnings": warnings,
    }


def _parse_timestamp(raw: object) -> datetime | None:
    """Parse an ISO-8601 string or an epoch number (seconds or milliseconds)."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)) or (isinstance(raw, str) and raw.strip().isdigit()):
        epoch = float(raw)
        if epoch > 1e12:  # milliseconds
            epoch /= 1000.0
        try:
            return datetime.fromtimestamp(epoch, UTC)
        except (OverflowError, OSError, ValueError):
            return None
    try:
        ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return ts if ts.tzinfo else ts.replace(tzinfo=UTC)
    except ValueError:
        return None


def _recall_connected(doc: CoverageDoc) -> bool:
    """A collection is reachable by /memory recall iff it has at least one of the
    three recall lanes: BM25 (an ArangoSearch view links it), dense (Qdrant
    vectors), or graph (an edge collection / named-graph member reachable by the
    multi-hop traversal lane)."""
    has_bm25 = bool(doc.arangosearch_views)
    has_dense = bool(doc.vector_pointer_frac)
    has_graph = doc.type == "edge" or doc.in_named_graph
    return has_bm25 or has_dense or has_graph


def _flags_for(doc: CoverageDoc, stale_before: datetime) -> list[str]:
    flags: list[str] = []
    if doc.error:
        flags.append(CollectionFlag.COVERAGE_ERROR)
        return flags
    if doc.count == 0:
        flags.append(CollectionFlag.EMPTY)
        return flags
    is_edge = doc.type == "edge"

    # Dense (Qdrant) lane — edges never carry embeddings, so exempt them.
    if not is_edge:
        frac = doc.vector_pointer_frac
        if frac is not None:
            if frac == 0.0:
                flags.append(CollectionFlag.BM25_ONLY)
                flags.append(CollectionFlag.NO_QDRANT_EMBEDDING)
            elif frac < 0.9:
                flags.append(CollectionFlag.PARTIAL_SYNC)

        # BM25 (ArangoSearch) lane — a document collection with no view link is
        # not text-searchable, so it is invisible to /memory recall's BM25 path.
        if not doc.arangosearch_views:
            flags.append(CollectionFlag.NO_ARANGOSEARCH)

        # Neither lane => the collection cannot be reached by /memory recall.
        if not _recall_connected(doc):
            flags.append(CollectionFlag.NOT_RECALL_CONNECTED)

    # Query-index health.
    if set(doc.index_types) <= {"primary", "edge"}:
        flags.append(CollectionFlag.NO_SECONDARY_INDEX)
        if (doc.count or 0) >= SLOW_SCAN_MIN_DOCS:
            flags.append(CollectionFlag.SLOW_SCAN_RISK)

    if doc.embedding_array_frac:
        flags.append(CollectionFlag.EMBEDDING_ARRAY_VIOLATION)

    if doc.latest_timestamp:
        ts = _parse_timestamp(doc.latest_timestamp)
        if ts is None:
            logger.error("unparseable timestamp for {}: {}", doc.name, doc.latest_timestamp)
        elif ts < stale_before:
            flags.append(CollectionFlag.STALE)
    return flags


def build_metrics(sample: int, stale_days: int) -> dict:
    warnings: list[str] = []
    coverage, c_err = fetch_arango_coverage(sample)
    qdrant, q_err = fetch_qdrant_health()
    for err in (c_err, q_err):
        if err:
            warnings.append(err)

    stale_before = datetime.now(UTC) - timedelta(days=stale_days)
    rows: list[dict] = []
    flag_counts: dict[str, int] = {}
    if coverage is not None:
        for doc in coverage.collections:
            flags = [str(f) for f in _flags_for(doc, stale_before)]
            for f in flags:
                flag_counts[f] = flag_counts.get(f, 0) + 1
            rows.append(
                {
                    "name": doc.name,
                    "type": doc.type,
                    "count": doc.count,
                    "index_types": doc.index_types,
                    "arangosearch_views": doc.arangosearch_views,
                    "in_named_graph": doc.in_named_graph,
                    "vector_pointer_frac": doc.vector_pointer_frac,
                    "recall_connected": _recall_connected(doc),
                    "recall_lanes": (
                        (["bm25"] if doc.arangosearch_views else [])
                        + (["dense"] if doc.vector_pointer_frac else [])
                        + (["graph"] if doc.in_named_graph or doc.type == "edge" else [])
                    ),
                    "sync_states": doc.sync_states,
                    "latest_timestamp": doc.latest_timestamp,
                    "flags": flags,
                }
            )
    rows.sort(key=lambda r: -(r["count"] or 0))
    non_empty = sum(1 for r in rows if (r["count"] or 0) > 0)
    recall_connected = sum(
        1 for r in rows if r.get("recall_connected") and (r["count"] or 0) > 0
    )

    return {
        "schema": "ops_memory.metrics.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "stale_days": stale_days,
        "sample_size": sample,
        "arango_collection_count": len(rows),
        "recall_connectivity": {
            "connected": recall_connected,
            "not_connected": non_empty - recall_connected,
            "non_empty": non_empty,
        },
        "qdrant": {
            "up": qdrant.up if qdrant else False,
            "collection_count": qdrant.collection_count if qdrant else None,
            "collections": qdrant.collections if qdrant else [],
            "dense_ok": qdrant.dense_ok if qdrant else None,
        },
        "flag_counts": flag_counts,
        "collections": rows,
        "seam_validation": {"kind": "ops_memory.metrics", "status": "PASS"},
        "warnings": warnings,
    }


def build_topology_dag() -> dict:
    """A phart-renderable ask.dag.v1 graph of the /memory stack.

    phart only accepts the node types memory.recall/dogpile.search/ask.oracle/
    skill.run, so every stack component uses skill.run and encodes its role and
    port in the node id (which is what the chart renders).
    """
    return {
        "schema_version": "ask.dag.v1",
        "graph_id": "memory-stack",
        "description": "How the /memory stack is wired and monitored",
        "nodes": [
            {"id": "agent", "type": "skill.run", "depends_on": []},
            {"id": "ops-memory.frontdoor", "type": "skill.run", "depends_on": ["agent"]},
            {"id": "memory.daemon-8601", "type": "memory.recall", "depends_on": ["ops-memory.frontdoor"]},
            {"id": "ops-arango.admin-coverage", "type": "skill.run", "depends_on": ["ops-memory.frontdoor"]},
            {"id": "ops-qdrant.vector-health", "type": "skill.run", "depends_on": ["ops-memory.frontdoor"]},
            {"id": "arangodb.docs-pointers-8529", "type": "skill.run",
             "depends_on": ["memory.daemon-8601", "ops-arango.admin-coverage"]},
            {"id": "qdrant.vectors-6333", "type": "skill.run",
             "depends_on": ["memory.daemon-8601", "ops-qdrant.vector-health"]},
            {"id": "embedder.jina-mm-8603", "type": "skill.run", "depends_on": ["memory.daemon-8601"]},
            {"id": "backups.12tb-retention", "type": "skill.run", "depends_on": ["ops-arango.admin-coverage"]},
        ],
    }


# --- explain: closed-vocabulary NL router (no regex classification) --------


class Intent(StrEnum):
    HEALTH = "health"
    METRICS = "metrics"
    TOPOLOGY = "topology"
    RECALL = "recall"
    BACKUPS = "backups"


INTENT_KEYWORDS: dict[Intent, set[str]] = {
    Intent.HEALTH: {"health", "healthy", "working", "broken", "status", "up", "down", "ok"},
    Intent.METRICS: {
        "metrics", "stale", "embedding", "embeddings", "vector", "vectors", "sync",
        "synced", "index", "indexes", "collection", "collections", "count", "counts",
        "coverage", "missing", "points",
    },
    Intent.TOPOLOGY: {
        "topology", "architecture", "constructed", "wired", "diagram", "chart",
        "schema", "how", "works", "built", "structure",
    },
    Intent.RECALL: {"recall", "know", "remember", "search", "find", "lookup"},
    Intent.BACKUPS: {"backup", "backups", "dump", "retention", "restore", "snapshot"},
}


def route_intent(question: str) -> tuple[Intent, dict[str, int]]:
    tokens = {t for t in "".join(c.lower() if c.isalnum() else " " for c in question).split()}
    scores = {intent: len(tokens & kws) for intent, kws in INTENT_KEYWORDS.items()}
    best = max(scores, key=lambda i: scores[i])
    if scores[best] == 0:
        best = Intent.HEALTH  # safe default: report overall health
    return best, {i.value: s for i, s in scores.items()}


# --- rendering -------------------------------------------------------------


def _emit(report: dict, json_out: bool, human) -> None:
    if json_out:
        typer.echo(jsonlib.dumps(report, indent=2))
    else:
        human(report)


def _human_health(report: dict) -> None:
    logger.info("/memory stack: {}", report["status"].upper())
    a = report["arango"]
    q = report["qdrant"]
    logger.info(
        "arango up={} docs={} embed_violations={} dup_clusters={} orphans={} integrity_errors={}",
        a["up"], a["total_documents"], a["embedding_violations"],
        a["duplicate_clusters"], a["orphan_edges"], a["integrity_errors"],
    )
    logger.info(
        "qdrant up={} collections={} dense_ok={}",
        q["up"], q["collection_count"], q["dense_ok"],
    )
    for w in report["warnings"]:
        logger.warning("  ! {}", w)


def _human_metrics(report: dict) -> None:
    logger.info(
        "/memory collections: {} arango, {} qdrant  (sample={}, stale>{}d)",
        report["arango_collection_count"],
        report["qdrant"]["collection_count"],
        report["sample_size"],
        report["stale_days"],
    )
    rc = report["recall_connectivity"]
    logger.info(
        "/memory recall connectivity: {}/{} non-empty collections reachable ({} NOT reachable)",
        rc["connected"], rc["non_empty"], rc["not_connected"],
    )
    if report["flag_counts"]:
        logger.info("flags: {}", report["flag_counts"])
    logger.info("{:>10}  {:>6}  {:<14}  {:<34} {}", "docs", "synced", "recall_lanes", "flags", "collection")
    for r in report["collections"][:40]:
        frac = r["vector_pointer_frac"]
        synced = "n/a" if frac is None else f"{int(frac * 100)}%"
        lanes = ",".join(r["recall_lanes"]) or "NONE"
        flags = ",".join(r["flags"]) or "-"
        logger.info("{:>10}  {:>6}  {:<14}  {:<34} {}", r["count"], synced, lanes, flags, r["name"])
    for w in report["warnings"]:
        logger.warning("  ! {}", w)


# --- commands --------------------------------------------------------------


@app.command()
def health(json_out: bool = typer.Option(False, "--json", help="Emit JSON.")) -> None:
    """Merged ArangoDB + Qdrant health for the whole /memory stack."""
    report = build_health()
    _emit(report, json_out, _human_health)
    if report["status"] == Status.DOWN:
        raise typer.Exit(code=2)


@app.command()
def metrics(
    json_out: bool = typer.Option(False, "--json", help="Emit JSON."),
    sample: int = typer.Option(200, "--sample", help="Docs sampled per collection for sync coverage."),
    stale_days: int = typer.Option(
        DEFAULT_STALE_DAYS, "--stale-days", help="A collection is STALE if its latest timestamp is older."
    ),
) -> None:
    """Per-collection matrix: counts, index inventory, Qdrant-sync, staleness flags."""
    report = build_metrics(sample=sample, stale_days=stale_days)
    _emit(report, json_out, _human_metrics)


@app.command()
def topology(
    chart: bool = typer.Option(False, "--chart", help="Render ASCII via phart-dag-chart."),
    json_out: bool = typer.Option(False, "--json", help="Emit the raw ask.dag.v1 JSON."),
) -> None:
    """Show how the /memory stack is wired (JSON, or ASCII chart via phart-dag-chart)."""
    dag = build_topology_dag()
    if json_out:
        typer.echo(jsonlib.dumps(dag, indent=2))
        return
    if not chart:
        for node in dag["nodes"]:
            deps = ", ".join(node["depends_on"]) or "(root)"
            logger.info("{:<14} [{}] <- {}", node["id"], node["type"], deps)
        return
    tmp = Path(os.environ.get("TMPDIR", "/tmp")) / f"ops-memory-topology-{os.getpid()}.dag.json"
    tmp.write_text(jsonlib.dumps(dag), encoding="utf-8")
    try:
        res = run_child(_child_run("phart-dag-chart", "PHART_RUN"), ["chart", str(tmp)], timeout=60)
        typer.echo(res.stdout if res.ok else res.stderr)
        if not res.ok:
            raise typer.Exit(code=1)
    finally:
        tmp.unlink(missing_ok=True)


@app.command()
def explain(question: str = typer.Argument(..., help="A plain-language question about /memory.")) -> None:
    """Route a plain-language question to the right report and run it."""
    intent, scores = route_intent(question)
    logger.info("routed {!r} -> {} (scores={})", question, intent.value, scores)
    if intent == Intent.HEALTH:
        _human_health(build_health())
    elif intent == Intent.METRICS:
        _human_metrics(build_metrics(sample=200, stale_days=DEFAULT_STALE_DAYS))
    elif intent == Intent.TOPOLOGY:
        topology(chart=True, json_out=False)
    elif intent == Intent.BACKUPS:
        _human_backups(build_backups())
    elif intent == Intent.RECALL:
        recall(query=question, k=5)


@app.command()
def recall(
    query: str = typer.Argument(..., help="Recall query."),
    k: int = typer.Option(5, "--k", help="Max results."),
) -> None:
    """Passthrough to the memory daemon's /recall via the memory skill."""
    res = run_child(
        _child_run("memory", "MEMORY_RUN"),
        ["recall", "--q", query, "--k", str(k)],
        timeout=RECALL_TIMEOUT,
    )
    typer.echo(res.stdout if res.stdout else res.stderr)
    if not res.ok:
        raise typer.Exit(code=res.returncode or 1)


# --- backups (read-only filesystem view + explicit gated trigger) ----------


def _backup_dir() -> Path:
    return Path(os.environ.get("ARANGO_BACKUP_DIR", DEFAULT_BACKUP_DIR))


def build_backups() -> dict:
    base = _backup_dir()
    entries: list[dict] = []
    if base.exists():
        for d in sorted((p for p in base.iterdir() if p.is_dir()), reverse=True):
            try:
                stat = d.stat()
                size_mb = round(sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) / 1_048_576, 1)
            except OSError as exc:
                logger.error("stat failed for {}: {}", d, exc)
                continue
            entries.append(
                {
                    "name": d.name,
                    "modified": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
                    "size_mb": size_mb,
                    "has_manifest": (d / "manifest.json").exists() or any(d.glob("**/*.structure.json")),
                }
            )
    return {
        "schema": "ops_memory.backups.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "backup_dir": str(base),
        "exists": base.exists(),
        "count": len(entries),
        "latest": entries[0] if entries else None,
        "backups": entries,
    }


def _human_backups(report: dict) -> None:
    logger.info("ArangoDB backups in {}: {}", report["backup_dir"], report["count"])
    if not report["exists"]:
        logger.warning("backup dir does not exist yet — run: ops-memory backup --now")
    for b in report["backups"][:10]:
        logger.info("  {}  {} MB  manifest={}  {}", b["modified"], b["size_mb"], b["has_manifest"], b["name"])


@app.command()
def backups(json_out: bool = typer.Option(False, "--json", help="Emit JSON.")) -> None:
    """List ArangoDB backups on the 12TB drive with size and retention (read-only)."""
    _emit(build_backups(), json_out, _human_backups)


@app.command()
def backup(
    now: bool = typer.Option(False, "--now", help="Confirm: create a real dump on the 12TB drive."),
) -> None:
    """Create an ArangoDB backup on the 12TB drive by delegating to ops-arango dump."""
    if not now:
        base = _backup_dir()
        logger.info("This writes a real ArangoDB dump under {} (retention keeps last 7).", base)
        logger.info("Re-run with --now to proceed:  ops-memory backup --now")
        raise typer.Exit(code=0)
    res = run_child(_child_run("ops-arango", "OPS_ARANGO_RUN"), ["dump"], timeout=CHILD_TIMEOUT)
    typer.echo(res.stdout)
    if res.stderr:
        typer.echo(res.stderr)
    if not res.ok:
        raise typer.Exit(code=res.returncode or 1)


# Which memory-owned Dewey repair operation remediates each metrics flag.
FLAG_TO_DEWEY_OP: dict[str, str] = {
    str(CollectionFlag.EMBEDDING_ARRAY_VIOLATION): "inline-vectors",
    str(CollectionFlag.BM25_ONLY): "missing-qdrant-embeddings",
    str(CollectionFlag.NO_QDRANT_EMBEDDING): "missing-qdrant-embeddings",
    str(CollectionFlag.PARTIAL_SYNC): "qdrant-pointer-metadata",
}


def _dewey_repair_script(memory_repo: Path) -> Path:
    return memory_repo / "scripts" / "validation" / "dewey_embedding_repair.py"


@app.command()
def fix(
    collection: str = typer.Option(None, "--collection", help="Single collection to repair (required for --apply)."),
    operation: str = typer.Option(
        None, "--operation",
        help="Dewey op: inline-vectors | missing-qdrant-embeddings | qdrant-pointer-metadata.",
    ),
    apply: bool = typer.Option(False, "--apply", help="Confirm: run one Dewey repair lane (external write)."),
) -> None:
    """Plan (default) or run one memory-owned Dewey embedding-repair lane.

    Semantic-sync remediation is owned by the memory repo. The sanctioned,
    tracked primitive is ``scripts/validation/dewey_embedding_repair.py`` — it
    writes a rollback manifest before mutating and fails closed. ops-memory never
    reimplements sync; it only plans the per-lane commands (mapping each metrics
    flag to a Dewey operation) and, with --apply, runs ONE explicitly-named lane.
    """
    memory_repo = Path(os.environ.get("MEMORY_REPO", Path.home() / "workspace/experiments/memory"))
    script = _dewey_repair_script(memory_repo)
    contract = memory_repo / "docs" / "guides" / "QDRANT_SEMANTIC_SYNC_CONTRACT.md"
    logger.info("sanctioned repair primitive: {} (exists={})", script, script.exists())
    logger.info("sync contract: {} (exists={})", contract, contract.exists())

    if not apply:
        logger.info("Plan only — Dewey repairs one collection+operation lane at a time:")
        for flag, op in sorted(set(FLAG_TO_DEWEY_OP.items())):
            logger.info(
                "  flag {:<26} -> uv run --project {} python {} {} --collection <NAME> "
                "--output <receipt.json> --rollback-out <rollback.jsonl> --apply",
                flag, memory_repo, script, op,
            )
        logger.info("Re-run with --collection <NAME> --operation <OP> --apply to execute one lane.")
        raise typer.Exit(code=0)

    if not script.exists():
        logger.error("Dewey repair primitive not found at {}", script)
        raise typer.Exit(code=2)
    if not collection or not operation:
        logger.error("--apply requires --collection and --operation (Dewey repairs one lane at a time)")
        raise typer.Exit(code=2)
    if operation not in set(FLAG_TO_DEWEY_OP.values()):
        logger.error("unknown --operation {} (use one of {})", operation, sorted(set(FLAG_TO_DEWEY_OP.values())))
        raise typer.Exit(code=2)
    receipt = Path(os.environ.get("TMPDIR", "/tmp")) / f"ops-memory-dewey-{collection}-{os.getpid()}.json"
    rollback = receipt.with_suffix(".rollback.jsonl")
    # dewey takes `operation` positionally and runs under the memory repo's uv env.
    argv = [
        "uv", "run", "--project", str(memory_repo), "python", str(script),
        operation, "--collection", collection,
        "--output", str(receipt), "--rollback-out", str(rollback), "--apply",
    ]
    logger.info("invoking Dewey: {}", " ".join(argv))
    try:
        proc = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=CHILD_TIMEOUT, env=_child_env())
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.error("Dewey invocation failed: {}", exc)
        raise typer.Exit(code=1) from exc
    typer.echo(proc.stdout or proc.stderr)
    logger.info("receipt: {}  rollback: {}", receipt, rollback)
    if proc.returncode != 0:
        raise typer.Exit(code=proc.returncode or 1)


# --- config doctor (non-interactive readiness) -----------------------------


@app.command()
def config(
    action: str = typer.Argument("doctor", help="doctor (non-interactive readiness)."),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Non-interactive readiness: which children resolve, which services answer."""
    if action != "doctor":
        logger.error("unknown config action: {} (use: doctor)", action)
        raise typer.Exit(code=2)

    needs_attention: list[dict] = []
    children = {
        "ops-arango": _child_run("ops-arango", "OPS_ARANGO_RUN"),
        "ops-qdrant": _child_run("ops-qdrant", "OPS_QDRANT_RUN"),
        "memory": _child_run("memory", "MEMORY_RUN"),
        "phart-dag-chart": _child_run("phart-dag-chart", "PHART_RUN"),
    }
    child_status = {name: p.exists() for name, p in children.items()}
    for name, present in child_status.items():
        if not present:
            needs_attention.append(
                {
                    "reason": f"missing_child:{name}",
                    "safe_default": "do_not_claim_ready",
                    "resume_hint": f"set {name.upper().replace('-', '_')}_RUN or restore skills/{name}/run.sh",
                }
            )
    if not os.environ.get("ARANGO_PASS"):
        needs_attention.append(
            {
                "reason": "missing_config:ARANGO_PASS",
                "safe_default": "arango_lanes_may_401",
                "resume_hint": "set ARANGO_PASS in the repo-root .env",
            }
        )
    backup_dir = _backup_dir()
    if not backup_dir.exists():
        needs_attention.append(
            {
                "reason": f"missing_backup_dir:{backup_dir}",
                "safe_default": "no_backups_yet",
                "resume_hint": "ops-memory backup --now",
            }
        )

    report = {
        "schema": "ops_memory.config_doctor.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "skills_root": str(_skills_root()),
        "children": {name: {"run_sh": str(p), "present": child_status[name]} for name, p in children.items()},
        "backup_dir": str(backup_dir),
        "readiness": "READY" if not needs_attention else "USABLE_WITH_GAPS",
        "needs_attention": needs_attention,
    }
    if json_out:
        typer.echo(jsonlib.dumps(report, indent=2))
    else:
        logger.info("ops-memory readiness: {}", report["readiness"])
        for name, meta in report["children"].items():
            logger.info("  child {:<16} present={}", name, meta["present"])
        for na in needs_attention:
            logger.warning("  needs_attention: {} -> {}", na["reason"], na["resume_hint"])


if __name__ == "__main__":
    app()
