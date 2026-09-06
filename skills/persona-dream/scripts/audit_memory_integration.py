#!/usr/bin/env python3
"""Audit persona-dream memory integration without faking pipeline proof.

This script checks two different things and keeps them separate:

1. Current live memory recall evidence for persona-dream records.
2. Source-code evidence that future pane/Tau runs automatically write/read
   those records through memory, Arango graph, Qdrant, and extract-entities.

It intentionally marks automation as PARTIAL/FAIL unless source hooks are
present. Existing records alone are not treated as proof of future automation.
"""

from __future__ import annotations

from pydantic_step_gate import validate_http_json

import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import httpx
except Exception as exc:  # pragma: no cover - environment diagnostic
    raise SystemExit(f"httpx is required for live memory audit: {exc}") from exc


ROOT = Path("/home/graham/workspace/experiments/agent-skills")
PERSONA_DREAM = ROOT / "skills/persona-dream"
PI_MONO = Path("/home/graham/workspace/experiments/pi-mono")
TAU = Path("/home/graham/workspace/experiments/tau")
REPORTS = PERSONA_DREAM / "reports"
MEMORY_URL = os.environ.get("MEMORY_URL", "http://127.0.0.1:8601")


@dataclass
class Check:
    id: str
    status: str
    evidence: list[str]
    missing: list[str]


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def read_text(path: Path) -> str:
    try:
        return path.read_text(errors="ignore")
    except Exception:
        return ""


def compact_match(path: Path, pattern: str, text: str, limit: int = 5) -> list[str]:
    out: list[str] = []
    rx = re.compile(pattern, re.IGNORECASE)
    for idx, line in enumerate(text.splitlines(), 1):
        if rx.search(line):
            stripped = re.sub(r"\s+", " ", line).strip()
            out.append(f"{path}:{idx}: {stripped[:220]}")
            if len(out) >= limit:
                break
    return out


def scan_files(root: Path, include_suffixes: tuple[str, ...], patterns: list[str], max_files: int = 4000) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {pattern: [] for pattern in patterns}
    if not root.exists():
        return hits
    skipped = {"node_modules", ".git", "dist", "build", ".next", "__pycache__"}
    scanned = 0
    for path in root.rglob("*"):
        if scanned >= max_files:
            break
        if any(part in skipped for part in path.parts):
            continue
        if not path.is_file() or path.suffix not in include_suffixes:
            continue
        scanned += 1
        text = read_text(path)
        if not text:
            continue
        for pattern in patterns:
            if len(hits[pattern]) >= 20:
                continue
            hits[pattern].extend(compact_match(path, pattern, text, limit=3))
            hits[pattern] = hits[pattern][:20]
    return hits


def memory_get(path: str) -> dict[str, Any]:
    with httpx.Client(timeout=20.0) as client:
        response = client.get(f"{MEMORY_URL}{path}")
        response.raise_for_status()
        return validate_http_json("memory_generic", response.json())


def memory_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    with httpx.Client(timeout=30.0) as client:
        response = client.post(f"{MEMORY_URL}{path}", json=payload)
        response.raise_for_status()
        return validate_http_json("memory_generic", response.json())


def recall(query: str, collections: list[str] | None = None, tags: list[str] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "q": query,
        "k": 8,
        "use_graph": True,
        "include_scores": True,
    }
    if collections:
        payload["collections"] = collections
    if tags:
        payload["tags"] = tags
    return memory_post("/recall", payload)


def summarize_items(result: dict[str, Any]) -> dict[str, Any]:
    items = result.get("items") or []
    score_counts = {"bm25": 0, "graph": 0, "dense": 0}
    samples: list[dict[str, Any]] = []
    for item in items:
        scores = item.get("scores") or {}
        for key in score_counts:
            try:
                if float(scores.get(key) or 0) > 0:
                    score_counts[key] += 1
            except Exception:
                pass
        samples.append(
            {
                "collection": item.get("collection"),
                "key": item.get("_key") or item.get("id"),
                "title": item.get("title") or item.get("name") or item.get("phase"),
                "scores": {k: scores.get(k) for k in ("bm25", "graph", "dense")},
            }
        )
    return {"count": len(items), "score_counts": score_counts, "samples": samples[:5]}


def status_from(predicate: bool, partial: bool = False) -> str:
    if predicate:
        return "PASS"
    if partial:
        return "PARTIAL"
    return "FAIL"


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()
    artifact_path = REPORTS / f"persona_dream_memory_integration_audit_{now_stamp()}.json"

    health: dict[str, Any]
    try:
        health = memory_get("/health")
    except Exception as exc:
        report = {
            "schema": "persona_dream.memory_integration_audit.v1",
            "generated_at": generated_at,
            "mocked": False,
            "live": False,
            "memory_url": MEMORY_URL,
            "memory_health_error": str(exc),
            "checks": [
                asdict(
                    Check(
                        id="memory_daemon_available",
                        status="FAIL",
                        evidence=[],
                        missing=[f"Memory daemon did not respond at {MEMORY_URL}: {exc}"],
                    )
                )
            ],
            "summary": {"PASS": 0, "PARTIAL": 0, "FAIL": 1},
            "not_proven": ["No memory integration proof possible while memory daemon is unavailable."],
        }
        artifact_path.write_text(json.dumps(report, indent=2))
        print(json.dumps({"artifact": str(artifact_path), "summary": report["summary"]}, indent=2))
        return 2

    code_patterns = [
        r"/recall\b|memory.*recall|MEMORY_URL|127\.0\.0\.1:8601",
        r"/upsert\b|/store\b|write-memory|memory_write_receipt|memory write receipt",
        r"extract-entities|entity_context\.json|entity_environment_script_table|interaction_matrix",
        r"qdrant|index-qdrant|dense",
        r"persona_memory_edges|tom_edges|Arango|graph",
        r"/api/tau/dream|latest.*json|story_contract|script_contract|contact_sheet",
    ]
    source_hits = {
        "persona_dream_skill": scan_files(PERSONA_DREAM, (".py", ".ts", ".tsx", ".json", ".md", ".sh"), code_patterns),
        "ux_lab": scan_files(PI_MONO / "packages/ux-lab", (".ts", ".tsx", ".js", ".mjs"), code_patterns),
        "tau": scan_files(TAU, (".py", ".json", ".md", ".sh"), code_patterns),
    }

    recalls = {
        "story_script_matrix": summarize_items(
            recall(
                "persona-dream Embry Kai Kahaluʻu story script interaction matrix environment coverage",
                collections=["persona_memory", "persona_memory_edges", "tom_edges"],
                tags=["persona-dream"],
            )
        ),
        "media_graph": summarize_items(
            recall(
                "persona-dream Embry Kai surfing image video sound audio TOM graph edges",
                collections=["persona_memory", "persona_memory_edges", "tom_edges", "persona_dream_visual_assets"],
                tags=["persona-dream"],
            )
        ),
        "contact_sheets": summarize_items(
            recall(
                "persona-dream contact sheets Embry Kai surfboard June Swell Lava Reef Kona Coast build receipt",
                collections=["persona_memory", "persona_dream_visual_assets"],
                tags=["persona-dream"],
            )
        ),
    }

    def hit_count(scope: str, pattern_index: int) -> int:
        pattern = code_patterns[pattern_index]
        return len(source_hits[scope].get(pattern, []))

    pane_read_hits = hit_count("ux_lab", 0)
    pane_json_hits = hit_count("ux_lab", 5)
    pane_write_hits = hit_count("ux_lab", 1)
    tau_write_hits = hit_count("tau", 1)
    tau_extract_hits = hit_count("tau", 2)
    skill_extract_hits = hit_count("persona_dream_skill", 2)
    graph_hits = hit_count("persona_dream_skill", 4) + hit_count("tau", 4)
    qdrant_hits = hit_count("persona_dream_skill", 3) + hit_count("tau", 3)

    checks: list[Check] = []
    checks.append(
        Check(
            id="current_memory_recall_has_bm25_graph_dense_signals",
            status=status_from(
                all(
                    recalls[name]["count"] > 0
                    and recalls[name]["score_counts"]["bm25"] > 0
                    and recalls[name]["score_counts"]["graph"] > 0
                    and recalls[name]["score_counts"]["dense"] > 0
                    for name in recalls
                )
            ),
            evidence=[
                f"{name}: count={data['count']} score_counts={data['score_counts']}"
                for name, data in recalls.items()
            ],
            missing=[
                "Any count or score_counts.bm25/graph/dense at 0 means recall is not proven across all channels."
            ]
            if not all(
                recalls[name]["count"] > 0
                and recalls[name]["score_counts"]["bm25"] > 0
                and recalls[name]["score_counts"]["graph"] > 0
                and recalls[name]["score_counts"]["dense"] > 0
                for name in recalls
            )
            else [],
        )
    )
    checks.append(
        Check(
            id="every_pane_automatically_writes_receipts_to_memory",
            status=status_from(False, partial=pane_write_hits > 0 or tau_write_hits > 0),
            evidence=[
                f"ux_lab memory write hook hits={pane_write_hits}",
                f"tau memory write hook hits={tau_write_hits}",
            ],
            missing=[
                "No proof that every pane completion path writes its receipt to memory automatically.",
                "Need pane-by-pane completion hooks or a shared Tau completion adapter that calls memory /upsert or /store and emits a receipt.",
            ],
        )
    )
    checks.append(
        Check(
            id="tau_creator_reviewer_loops_write_durable_artifacts_to_memory",
            status=status_from(False, partial=tau_write_hits > 0),
            evidence=[f"tau memory write hook hits={tau_write_hits}"],
            missing=[
                "Need one live Tau creator/reviewer run per phase showing durable artifact write receipt in memory.",
                "A Tau JSON proof directory alone is not proof that memory was updated.",
            ],
        )
    )
    checks.append(
        Check(
            id="ui_panes_read_from_memory_instead_of_stale_local_json",
            status=status_from(pane_read_hits > 0 and pane_json_hits == 0, partial=pane_read_hits > 0 and pane_json_hits > 0),
            evidence=[
                f"ux_lab memory recall/read hits={pane_read_hits}",
                f"ux_lab local latest/json endpoint hits={pane_json_hits}",
            ],
            missing=[
                "UI still has local/Tau latest JSON read paths; memory-backed reads are not proven as the authoritative source for every pane."
            ]
            if pane_json_hits > 0 or pane_read_hits == 0
            else [],
        )
    )
    checks.append(
        Check(
            id="new_media_edges_auto_added_to_arango_graph_and_qdrant",
            status=status_from(False, partial=graph_hits > 0 and qdrant_hits > 0 and recalls["media_graph"]["count"] > 0),
            evidence=[
                f"graph-related source hits={graph_hits}",
                f"qdrant-related source hits={qdrant_hits}",
                f"media_graph recall={recalls['media_graph']}",
            ],
            missing=[
                "Current graph/dense recall exists, but no proof every new asset/media edge is automatically upserted to Arango graph and Qdrant.",
                "Need a live new-media ingestion canary that creates an edge, then proves BM25 + graph + dense recall.",
            ],
        )
    )
    checks.append(
        Check(
            id="generation_paths_use_extract_entities_and_persist_coverage",
            status=status_from(False, partial=(tau_extract_hits + skill_extract_hits) > 0),
            evidence=[
                f"tau extract-entities/coverage hits={tau_extract_hits}",
                f"persona-dream extract-entities/coverage hits={skill_extract_hits}",
                f"story_script_matrix recall={recalls['story_script_matrix']}",
            ],
            missing=[
                "Need live story/script/contact-sheet generation receipts showing extract-entities execution and persisted coverage records.",
                "Existing coverage records are not proof every generation path enforces the gate.",
            ],
        )
    )

    summary = {"PASS": 0, "PARTIAL": 0, "FAIL": 0}
    for check in checks:
        summary[check.status] += 1

    not_proven = [
        check.id
        for check in checks
        if check.status != "PASS"
    ]

    report = {
        "schema": "persona_dream.memory_integration_audit.v1",
        "generated_at": generated_at,
        "mocked": False,
        "live": True,
        "memory_url": MEMORY_URL,
        "memory_health": health,
        "artifact_path": str(artifact_path),
        "recall_summaries": recalls,
        "source_hit_summary": {
            scope: {pattern: len(matches) for pattern, matches in patterns.items()}
            for scope, patterns in source_hits.items()
        },
        "source_hit_samples": source_hits,
        "checks": [asdict(check) for check in checks],
        "summary": summary,
        "not_proven": not_proven,
    }
    artifact_path.write_text(json.dumps(report, indent=2))
    print(json.dumps({"artifact": str(artifact_path), "summary": summary, "not_proven": not_proven}, indent=2))
    return 1 if not_proven else 0


if __name__ == "__main__":
    raise SystemExit(main())
