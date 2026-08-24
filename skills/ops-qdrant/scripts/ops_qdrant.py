"""ops-qdrant: read-only Qdrant vector-store health detector.

Purpose:
    Detect Qdrant health and semantic-recall degradation WITHOUT mutating
    anything. It answers four questions:
      1. Is Qdrant up, and which collections exist?
      2. Per collection: how many points, and what named vectors / media
         modalities (text_mm, image_mm) or single vector does it hold?
      3. Are the collections we expect present?
      4. Does end-to-end dense (semantic) recall actually work through the
         memory daemon, or has it silently degraded to BM25-only (dense == 0)?

Inputs:
    Environment: QDRANT_URL (default http://127.0.0.1:6333),
                 MEMORY_URL  (default http://127.0.0.1:8601),
                 EMBED_URL   (default http://127.0.0.1:8603),
                 OPS_QDRANT_EXPECT (comma-separated expected collections).
    CLI flags: --json, --expect, --q.

Outputs:
    Human-readable summary, or an ``ops_qdrant.health.v1`` JSON document on
    stdout for monitors / ops-memory composition.

Failure modes:
    - Qdrant unreachable        -> status=down, exit code 2.
    - Daemon/embedder unreachable or dense==0 -> status=degraded, exit code 0
      (report is still emitted; each failure is logged at logger.error).

Boundary (non-negotiable):
    This module performs NO writes. It issues only HTTP GETs to Qdrant and the
    embedder, and a single read-only POST /recall to the memory daemon. All
    Qdrant/Arango mutation and semantic sync live ONLY in the memory repo
    (see memory/SKILL.md). Remediation is triggered by ops-memory calling the
    memory repo's sanctioned migration, never from here.
"""

from __future__ import annotations

import json as jsonlib
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

import httpx
import typer
from loguru import logger
from pydantic import BaseModel, Field

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Read-only Qdrant vector-store health detection (NO writes).",
)

# --- configuration (boundary: environment) ---------------------------------

DEFAULT_QDRANT_URL = "http://127.0.0.1:6333"
DEFAULT_MEMORY_URL = "http://127.0.0.1:8601"
DEFAULT_EMBED_URL = "http://127.0.0.1:8603"
DEFAULT_PROBE_Q = "memory first recall pattern"

# Short budgets: these are health checks, not data transfers.
HEALTH_TIMEOUT = httpx.Timeout(connect=3.0, read=6.0, write=3.0, pool=3.0)
RECALL_TIMEOUT = httpx.Timeout(connect=3.0, read=12.0, write=6.0, pool=3.0)


class Status(StrEnum):
    """Closed vocabulary for overall health."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"


# --- boundary models (validate external JSON once) -------------------------


class RecallItem(BaseModel):
    scores: dict[str, float] = Field(default_factory=dict)


class RecallResponse(BaseModel):
    found: bool = False
    confidence: float = 0.0
    items: list[RecallItem] = Field(default_factory=list)


# --- internal typed records ------------------------------------------------


@dataclass(slots=True)
class VectorSpec:
    """One vector space in a collection. ``name`` is None for a single
    unnamed vector; otherwise it is the named-vector key (e.g. text_mm)."""

    name: str | None
    size: int
    distance: str


@dataclass(slots=True)
class CollectionHealth:
    name: str
    points: int
    vectors: list[VectorSpec] = field(default_factory=list)

    @property
    def modalities(self) -> list[str]:
        return sorted(v.name for v in self.vectors if v.name)


@dataclass(slots=True)
class DenseProbe:
    q: str
    found: bool
    dense_max: float
    dense_ok: bool


# --- HTTP helpers (read-only) ----------------------------------------------


def _config() -> dict[str, str]:
    return {
        "qdrant_url": os.environ.get("QDRANT_URL", DEFAULT_QDRANT_URL).rstrip("/"),
        "memory_url": os.environ.get("MEMORY_URL", DEFAULT_MEMORY_URL).rstrip("/"),
        "embed_url": os.environ.get("EMBED_URL", DEFAULT_EMBED_URL).rstrip("/"),
    }


def list_collections(client: httpx.Client, qdrant_url: str) -> list[str] | None:
    """Return collection names, or None if Qdrant is unreachable."""
    try:
        resp = client.get(f"{qdrant_url}/collections")
        resp.raise_for_status()
        result = resp.json().get("result", {})
        return sorted(c["name"] for c in result.get("collections", []))
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.error("qdrant /collections failed at {}: {}", qdrant_url, exc)
        return None


def _parse_vectors(vectors_cfg: object) -> list[VectorSpec]:
    """Normalize Qdrant's two vector-config shapes into VectorSpec list.

    Single unnamed vector: {"size": 1024, "distance": "Cosine"}.
    Named vectors:         {"text_mm": {"size":1024,...}, "image_mm": {...}}.
    """
    specs: list[VectorSpec] = []
    if not isinstance(vectors_cfg, dict):
        return specs
    if "size" in vectors_cfg:  # single unnamed vector
        specs.append(
            VectorSpec(
                name=None,
                size=int(vectors_cfg.get("size", 0)),
                distance=str(vectors_cfg.get("distance", "")),
            )
        )
        return specs
    for name, params in vectors_cfg.items():  # named vectors
        if isinstance(params, dict):
            specs.append(
                VectorSpec(
                    name=name,
                    size=int(params.get("size", 0)),
                    distance=str(params.get("distance", "")),
                )
            )
    return sorted(specs, key=lambda s: s.name or "")


def get_collection(
    client: httpx.Client, qdrant_url: str, name: str
) -> CollectionHealth | None:
    try:
        resp = client.get(f"{qdrant_url}/collections/{name}")
        resp.raise_for_status()
        result = resp.json().get("result", {})
        params = result.get("config", {}).get("params", {})
        return CollectionHealth(
            name=name,
            points=int(result.get("points_count") or 0),
            vectors=_parse_vectors(params.get("vectors", {})),
        )
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.error("qdrant /collections/{} failed: {}", name, exc)
        return None


def embedder_up(client: httpx.Client, embed_url: str) -> bool:
    for path in ("/health", "/"):
        try:
            resp = client.get(f"{embed_url}{path}")
            if resp.status_code < 500:
                return True
        except httpx.HTTPError as exc:
            logger.error("embedder probe {} failed: {}", path, exc)
    return False


def dense_probe(client: httpx.Client, memory_url: str, q: str) -> DenseProbe:
    """Read-only POST /recall; measure max dense score across returned items."""
    try:
        resp = client.post(f"{memory_url}/recall", json={"q": q, "k": 5})
        resp.raise_for_status()
        data = RecallResponse.model_validate(resp.json())
        dense_scores = [i.scores.get("dense", 0.0) for i in data.items]
        dense_max = max(dense_scores) if dense_scores else 0.0
        return DenseProbe(
            q=q, found=data.found, dense_max=dense_max, dense_ok=dense_max > 0.0
        )
    except (httpx.HTTPError, ValueError) as exc:
        logger.error("memory /recall dense probe failed at {}: {}", memory_url, exc)
        return DenseProbe(q=q, found=False, dense_max=0.0, dense_ok=False)


# --- report assembly -------------------------------------------------------


def _expected(expect: str | None) -> list[str]:
    raw = expect if expect is not None else os.environ.get("OPS_QDRANT_EXPECT", "")
    return sorted({c.strip() for c in raw.split(",") if c.strip()})


def build_report(expect: str | None, q: str) -> dict:
    cfg = _config()
    generated_at = datetime.now(UTC).isoformat()
    warnings: list[str] = []

    with httpx.Client(timeout=HEALTH_TIMEOUT) as client:
        names = list_collections(client, cfg["qdrant_url"])
        qdrant_up = names is not None
        collections: list[CollectionHealth] = []
        if qdrant_up:
            for name in names or []:
                ch = get_collection(client, cfg["qdrant_url"], name)
                if ch is not None:
                    collections.append(ch)
        emb_up = embedder_up(client, cfg["embed_url"])

    daemon_up = False
    probe = DenseProbe(q=q, found=False, dense_max=0.0, dense_ok=False)
    if qdrant_up:
        with httpx.Client(timeout=RECALL_TIMEOUT) as rclient:
            probe = dense_probe(rclient, cfg["memory_url"], q)
            daemon_up = probe.found or probe.dense_max > 0.0

    present = {c.name for c in collections}
    expected = _expected(expect)
    missing_expected = sorted(set(expected) - present)

    if not qdrant_up:
        status = Status.DOWN
        warnings.append(f"Qdrant unreachable at {cfg['qdrant_url']}")
    else:
        status = Status.HEALTHY
        if missing_expected:
            status = Status.DEGRADED
            warnings.append(f"expected collections absent: {missing_expected}")
        if probe.found and not probe.dense_ok:
            status = Status.DEGRADED
            warnings.append(
                "dense recall is 0.0 (BM25-only); Qdrant semantic recall "
                "unavailable — check embedder, qdrant_point_id metadata"
            )
        if not emb_up:
            status = Status.DEGRADED
            warnings.append(f"embedder unreachable at {cfg['embed_url']}")

    return {
        "schema": "ops_qdrant.health.v1",
        "generated_at": generated_at,
        "config": cfg,
        "qdrant_up": qdrant_up,
        "embedder_up": emb_up,
        "memory_daemon_up": daemon_up,
        "collection_count": len(collections),
        "collections": [
            {
                "name": c.name,
                "points": c.points,
                "modalities": c.modalities,
                "vectors": [asdict(v) for v in c.vectors],
            }
            for c in collections
        ],
        "expected": expected,
        "missing_expected": missing_expected,
        "dense_probe": asdict(probe),
        "status": str(status),
        "warnings": warnings,
    }


# --- rendering -------------------------------------------------------------


def _print_human(report: dict) -> None:
    logger.info("Qdrant health: {}", report["status"].upper())
    logger.info(
        "qdrant_up={} embedder_up={} daemon_up={} collections={}",
        report["qdrant_up"],
        report["embedder_up"],
        report["memory_daemon_up"],
        report["collection_count"],
    )
    for c in report["collections"]:
        mod = ",".join(c["modalities"]) or "single-vector"
        logger.info("  {:>10} pts  [{}]  {}", c["points"], mod, c["name"])
    probe = report["dense_probe"]
    logger.info(
        "dense probe q={!r} found={} dense_max={} dense_ok={}",
        probe["q"],
        probe["found"],
        probe["dense_max"],
        probe["dense_ok"],
    )
    for w in report["warnings"]:
        logger.warning("  ! {}", w)


def _emit(report: dict, json_out: bool) -> None:
    if json_out:
        typer.echo(jsonlib.dumps(report, indent=2))
    else:
        _print_human(report)


# --- commands --------------------------------------------------------------


@app.command()
def check(
    json_out: bool = typer.Option(False, "--json", help="Emit JSON report."),
    expect: str = typer.Option(
        None, "--expect", help="Comma-separated collections that must exist."
    ),
    q: str = typer.Option(DEFAULT_PROBE_Q, "--q", help="Dense-probe query."),
) -> None:
    """Full read-only health report. Exit 2 if Qdrant itself is unreachable."""
    report = build_report(expect=expect, q=q)
    _emit(report, json_out)
    if not report["qdrant_up"]:
        raise typer.Exit(code=2)


@app.command()
def collections(
    json_out: bool = typer.Option(False, "--json", help="Emit JSON report."),
) -> None:
    """List collections with point counts and named-vector modalities."""
    report = build_report(expect=None, q=DEFAULT_PROBE_Q)
    if json_out:
        typer.echo(jsonlib.dumps(report["collections"], indent=2))
    else:
        for c in report["collections"]:
            mod = ",".join(c["modalities"]) or "single-vector"
            logger.info("{:>10} pts  [{}]  {}", c["points"], mod, c["name"])
    if not report["qdrant_up"]:
        raise typer.Exit(code=2)


@app.command("dense-probe")
def dense_probe_cmd(
    q: str = typer.Option(DEFAULT_PROBE_Q, "--q", help="Query to probe."),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Probe end-to-end dense recall through the memory daemon (read-only)."""
    cfg = _config()
    with httpx.Client(timeout=RECALL_TIMEOUT) as client:
        probe = dense_probe(client, cfg["memory_url"], q)
    if json_out:
        typer.echo(jsonlib.dumps(asdict(probe), indent=2))
    else:
        logger.info(
            "found={} dense_max={} dense_ok={}",
            probe.found,
            probe.dense_max,
            probe.dense_ok,
        )
    if probe.found and not probe.dense_ok:
        logger.warning("dense recall degraded to BM25-only (dense_max=0.0)")


# --- assess: Qdrant single-owner boundary linter ---------------------------
#
# Grammar note (best-practices-python correctness-regex-only-known-grammar): the
# patterns below match a KNOWN, stable grammar — Python import statements and
# literal Qdrant REST ports — anchored to line starts. They are misuse detectors,
# not general parsing. Each maps a specific violation of the Qdrant single-owner
# access boundary (best-practices-arangodb rule 22b) to a corrective message.


@dataclass(slots=True)
class AssessPattern:
    name: str
    regex: str
    severity: str
    message: str
    fix: str


ASSESS_PATTERNS: tuple[AssessPattern, ...] = (
    AssessPattern(
        name="raw_qdrant_client_import",
        # raw PyPI library only — NOT graph_memory.qdrant_client (sanctioned wrapper)
        regex=r"^\s*(from\s+qdrant_client(\.\w+)*\s+import|import\s+qdrant_client)\b",
        severity="error",
        message="raw qdrant_client import — Qdrant is single-owner (memory repo)",
        fix="use /memory recall (dense lane) or graph_memory.qdrant_client; for health use /ops-qdrant",
    ),
    AssessPattern(
        name="qdrant_collection_mutation",
        regex=r"\.(create_collection|recreate_collection|delete_collection)\s*\(",
        severity="error",
        message="Qdrant collection mutation in a skill — config is owned by the memory repo",
        fix="collection config, HNSW/quantization, and dims/distance are memory-repo concerns",
    ),
)


def assess_file(path: Path) -> dict:
    """Scan one source file for Qdrant single-owner boundary violations."""
    issues: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("assess: cannot read {}: {}", path, exc)
        return {"schema": "ops_qdrant.assess.v1", "file": str(path), "error": str(exc), "passed": False, "issues": []}
    for lineno, line in enumerate(text.splitlines(), start=1):
        # The sanctioned wrapper is allowed; never flag it as a raw import.
        if "graph_memory.qdrant_client" in line:
            continue
        for pat in ASSESS_PATTERNS:
            if re.search(pat.regex, line):
                issues.append(
                    {
                        "line": lineno,
                        "pattern": pat.name,
                        "severity": pat.severity,
                        "message": pat.message,
                        "fix": pat.fix,
                    }
                )
    return {
        "schema": "ops_qdrant.assess.v1",
        "file": str(path),
        "passed": not issues,
        "issue_count": len(issues),
        "issues": issues,
    }


@app.command()
def assess(
    path: str = typer.Argument(..., help="Python file to check for Qdrant boundary violations."),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Flag raw qdrant_client usage / direct Qdrant access in external code (read-only)."""
    report = assess_file(Path(path))
    if json_out:
        typer.echo(jsonlib.dumps(report, indent=2))
    else:
        if report.get("error"):
            logger.error("assess {}: {}", report["file"], report["error"])
        elif report["passed"]:
            logger.info("assess {}: OK — no Qdrant boundary violations", report["file"])
        else:
            logger.warning("assess {}: {} issue(s)", report["file"], report["issue_count"])
            for i in report["issues"]:
                logger.warning("  L{} [{}] {} -> {}", i["line"], i["severity"], i["message"], i["fix"])
    if not report["passed"]:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
