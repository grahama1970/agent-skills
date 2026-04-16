#!/usr/bin/env python3
"""
Persona Readiness Assessment — determine if a persona has sufficient QRAs
to answer questions about their core competency.

Queries ArangoDB for:
- Per-scope QRA count
- Per-bridge-tag distribution within each scope
- Quality score distribution

Compares against persona's taxonomy_hints, qra_target, and minimum thresholds
to produce a readiness verdict.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger
from rich.console import Console
from rich.table import Table

from monitor_core import PersonaConfig, get_all_personas, load_config

console = Console()

# Minimum QRA thresholds for readiness tiers
MIN_READY = 500        # Minimum QRAs for "READY" status
MIN_PARTIAL = 100      # Minimum QRAs for "PARTIAL" status
MIN_BRIDGE_QRAS = 20   # Minimum QRAs per bridge tag for coverage


@dataclass
class BridgeCoverage:
    """Coverage stats for a single bridge tag."""
    tag: str
    count: int
    sufficient: bool  # >= MIN_BRIDGE_QRAS


@dataclass
class PersonaReadiness:
    """Readiness assessment for a single persona."""
    persona_id: str
    persona_name: str
    scope: str
    category: str
    fictional: bool
    taxonomy_hints: List[str]
    qra_target: int
    total_qras: int
    bridge_coverage: List[BridgeCoverage]
    avg_quality: float
    alternate_collections: Dict[str, int]  # e.g. {"sparta_qra": 214326}
    datalake_chunks: int  # Available raw material in datalake
    verdict: str  # READY | PARTIAL | COLD_START | NO_DATA
    notes: List[str]

    @property
    def target_pct(self) -> float:
        if self.qra_target <= 0:
            return 0.0
        return min(100.0, 100.0 * self.total_qras / self.qra_target)

    @property
    def bridges_covered(self) -> int:
        return sum(1 for b in self.bridge_coverage if b.sufficient)

    @property
    def bridges_total(self) -> int:
        return len(self.bridge_coverage)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "persona_id": self.persona_id,
            "persona_name": self.persona_name,
            "scope": self.scope,
            "category": self.category,
            "fictional": self.fictional,
            "taxonomy_hints": self.taxonomy_hints,
            "qra_target": self.qra_target,
            "total_qras": self.total_qras,
            "target_pct": round(self.target_pct, 1),
            "bridge_coverage": [
                {"tag": b.tag, "count": b.count, "sufficient": b.sufficient}
                for b in self.bridge_coverage
            ],
            "bridges_covered": self.bridges_covered,
            "bridges_total": self.bridges_total,
            "avg_quality": round(self.avg_quality, 3),
            "alternate_collections": self.alternate_collections,
            "datalake_chunks": self.datalake_chunks,
            "verdict": self.verdict,
            "notes": self.notes,
        }


import subprocess
import httpx

SKILLS_DIR = Path(__file__).resolve().parent.parent
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

def _get_memory_available() -> bool:
    """Check if /memory subprocess is available."""
    try:
        _memory_cmd(["count", "--scope", "operational"])
        return True
    except Exception:
        return False


def _query_scope_qra_count(scope: str) -> int:
    """Count QRAs for a given scope via /memory count."""
    try:
        result = _memory_cmd(["count", "--scope", scope])
        return result.get("count", 0)
    except Exception as e:
        logger.debug("QRA count query failed for scope {}: {}", scope, e)
        return 0


def _query_bridge_distribution(scope: str, bridge_tags: List[str]) -> List[BridgeCoverage]:
    """Estimate QRA counts per bridge tag within a scope via /memory recall."""
    coverage = []
    for tag in bridge_tags:
        try:
            result = _memory_cmd([
                "recall", "--q", tag,
                "--scope", scope, "--k", "1",
            ])
            # Use total count from meta if available, else items length
            items = result.get("items", result.get("results", []))
            count = result.get("meta", {}).get("total", len(items))
        except Exception as e:
            logger.debug("Bridge query failed for {}/{}: {}", scope, tag, e)
            count = 0

        coverage.append(BridgeCoverage(
            tag=tag,
            count=count,
            sufficient=count >= MIN_BRIDGE_QRAS,
        ))
    return coverage


def _query_avg_quality(scope: str) -> float:
    """Average quality score for QRAs in a scope (best-effort via /memory)."""
    # /memory doesn't expose aggregate quality; return 0 as unknown
    return 0.0


# Known alternate collections where persona QRAs may live
# Maps persona_id → [(collection_name, label)]
ALTERNATE_COLLECTIONS = {
    "brandon_bailey": [("sparta_qra", "sparta_qra")],
    "horus": [("horus_lore_chunks", "horus_lore")],
}


def _query_collection_count(collection: str) -> int:
    """Count documents in a collection scope via /memory."""
    try:
        result = _memory_cmd(["count", "--scope", collection])
        return result.get("count", 0)
    except Exception as e:
        logger.debug("Collection count failed for {}: {}", collection, e)
        return 0


def _query_datalake_chunks() -> int:
    """Count total chunks in datalake (shared raw material)."""
    try:
        result = _memory_cmd(["count", "--scope", "datalake_chunks"])
        return result.get("count", 0)
    except Exception as e:
        logger.debug("Datalake count failed: {}", e)
        return 0


def _compute_verdict(
    total_qras: int,
    qra_target: int,
    bridge_coverage: List[BridgeCoverage],
    avg_quality: float,
) -> tuple[str, List[str]]:
    """Compute readiness verdict and notes."""
    notes: List[str] = []

    if total_qras == 0:
        return "NO_DATA", ["No QRAs found in this scope"]

    # Check bridge coverage
    if bridge_coverage:
        uncovered = [b.tag for b in bridge_coverage if not b.sufficient]
        if uncovered:
            notes.append(f"Weak bridges: {', '.join(uncovered)}")

    # Check target
    if qra_target > 0:
        pct = 100.0 * total_qras / qra_target
        if pct < 20:
            notes.append(f"Only {pct:.0f}% of QRA target ({qra_target})")
        elif pct < 80:
            notes.append(f"{pct:.0f}% of QRA target ({qra_target})")

    # Check quality
    if avg_quality > 0 and avg_quality < 0.5:
        notes.append(f"Low avg quality: {avg_quality:.2f}")

    # Verdict logic
    effective_target = qra_target if qra_target > 0 else MIN_READY

    if total_qras >= effective_target:
        # Have enough QRAs — check bridge coverage
        if bridge_coverage:
            covered_ratio = sum(1 for b in bridge_coverage if b.sufficient) / len(bridge_coverage)
            if covered_ratio >= 0.8:
                return "READY", notes
            elif covered_ratio >= 0.5:
                notes.append("Good QRA count but incomplete bridge coverage")
                return "PARTIAL", notes
            else:
                notes.append("QRA count sufficient but bridge coverage too sparse")
                return "PARTIAL", notes
        return "READY", notes

    elif total_qras >= MIN_PARTIAL:
        return "PARTIAL", notes

    else:
        notes.append(f"Need {MIN_PARTIAL - total_qras} more QRAs for PARTIAL status")
        return "COLD_START", notes


def assess_persona(persona: PersonaConfig) -> PersonaReadiness:
    """Assess readiness for a single persona."""
    scope = persona.scope
    qra_target = getattr(persona, "qra_target", 0) or 0

    total_qras = _query_scope_qra_count(scope)
    bridge_coverage = _query_bridge_distribution(scope, persona.taxonomy_hints)
    avg_quality = _query_avg_quality(scope)

    # Check alternate collections (e.g. sparta_qra for Brandon, horus_lore for Horus)
    alt_collections: Dict[str, int] = {}
    for coll_name, label in ALTERNATE_COLLECTIONS.get(persona.id, []):
        count = _query_collection_count(coll_name)
        if count > 0:
            alt_collections[label] = count

    verdict, notes = _compute_verdict(total_qras, qra_target, bridge_coverage, avg_quality)

    # Add alternate collection info to notes
    for label, count in alt_collections.items():
        notes.append(f"+{count:,} in {label} (shared)")

    return PersonaReadiness(
        persona_id=persona.id,
        persona_name=persona.name,
        scope=scope,
        category=persona.category,
        fictional=persona.fictional,
        taxonomy_hints=persona.taxonomy_hints,
        qra_target=qra_target,
        total_qras=total_qras,
        bridge_coverage=bridge_coverage,
        avg_quality=avg_quality,
        alternate_collections=alt_collections,
        datalake_chunks=0,
        verdict=verdict,
        notes=notes,
    )


def cmd_readiness(
    persona_id: Optional[str] = None,
    priority: Optional[str] = None,
    json_output: bool = False,
    verbose: bool = False,
):
    """Assess persona readiness — do they have enough QRAs for their core competency?"""
    if not _get_memory_available():
        console.print("[red]Cannot connect to /memory. Ensure memory skill is running.[/red]")
        return

    personas = get_all_personas()

    # Filter
    if persona_id:
        ids = {p.strip().lower() for p in persona_id.split(",")}
        personas = [p for p in personas if p.id.lower() in ids]
    if priority:
        personas = [p for p in personas if p.priority.upper() == priority.upper()]

    if not personas:
        console.print("[yellow]No personas matched filters.[/yellow]")
        return

    # Query datalake once
    datalake_chunks = _query_datalake_chunks()

    results: List[PersonaReadiness] = []
    for persona in personas:
        r = assess_persona(persona)
        r.datalake_chunks = datalake_chunks
        results.append(r)

    # Sort: READY first, then PARTIAL, then COLD_START, then NO_DATA
    verdict_order = {"READY": 0, "PARTIAL": 1, "COLD_START": 2, "NO_DATA": 3}
    results.sort(key=lambda r: (verdict_order.get(r.verdict, 9), -r.total_qras))

    if json_output:
        output = {
            "datalake_chunks": datalake_chunks,
            "personas": [r.to_dict() for r in results],
            "summary": {
                "total": len(results),
                "ready": sum(1 for r in results if r.verdict == "READY"),
                "partial": sum(1 for r in results if r.verdict == "PARTIAL"),
                "cold_start": sum(1 for r in results if r.verdict == "COLD_START"),
                "no_data": sum(1 for r in results if r.verdict == "NO_DATA"),
            },
        }
        console.print(json.dumps(output, indent=2))
        return

    # Rich table output
    console.print()
    console.print(f"[bold]Persona Readiness Assessment[/bold]  (datalake: {datalake_chunks:,} chunks)")
    console.print()

    table = Table(show_header=True, header_style="bold")
    table.add_column("Persona", style="cyan", min_width=18)
    table.add_column("Scope", style="dim")
    table.add_column("QRAs", justify="right")
    table.add_column("Target", justify="right")
    table.add_column("Bridges", justify="center")
    table.add_column("Quality", justify="right")
    table.add_column("Verdict", justify="center")
    table.add_column("Notes", max_width=40)

    verdict_style = {
        "READY": "[bold green]READY[/bold green]",
        "PARTIAL": "[yellow]PARTIAL[/yellow]",
        "COLD_START": "[red]COLD_START[/red]",
        "NO_DATA": "[dim]NO_DATA[/dim]",
    }

    for r in results:
        # Bridge coverage display
        if r.bridges_total > 0:
            bridge_str = f"{r.bridges_covered}/{r.bridges_total}"
        else:
            bridge_str = "-"

        # Target display
        if r.qra_target > 0:
            target_str = f"{r.total_qras}/{r.qra_target} ({r.target_pct:.0f}%)"
        else:
            target_str = str(r.total_qras)

        # Quality display
        quality_str = f"{r.avg_quality:.2f}" if r.avg_quality > 0 else "-"

        table.add_row(
            r.persona_name,
            r.scope,
            f"{r.total_qras:,}",
            target_str,
            bridge_str,
            quality_str,
            verdict_style.get(r.verdict, r.verdict),
            "; ".join(r.notes) if r.notes else "",
        )

    console.print(table)

    # Summary
    n_ready = sum(1 for r in results if r.verdict == "READY")
    n_partial = sum(1 for r in results if r.verdict == "PARTIAL")
    n_cold = sum(1 for r in results if r.verdict == "COLD_START")
    n_none = sum(1 for r in results if r.verdict == "NO_DATA")
    console.print()
    console.print(
        f"  [green]{n_ready} READY[/green]  "
        f"[yellow]{n_partial} PARTIAL[/yellow]  "
        f"[red]{n_cold} COLD_START[/red]  "
        f"[dim]{n_none} NO_DATA[/dim]"
    )

    # Verbose: show per-bridge breakdown for each persona
    if verbose:
        console.print()
        for r in results:
            if not r.bridge_coverage:
                continue
            console.print(f"  [bold]{r.persona_name}[/bold] ({r.scope})")
            for b in r.bridge_coverage:
                icon = "[green]OK[/green]" if b.sufficient else "[red]LOW[/red]"
                bar_len = min(20, b.count // 5) if b.count > 0 else 0
                bar = "█" * bar_len + "░" * (20 - bar_len)
                console.print(f"    {b.tag:<12s} {bar} {b.count:>5d} {icon}")
            console.print()
