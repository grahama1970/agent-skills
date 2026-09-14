#!/usr/bin/env python3
"""Build the Persona Dream journal source packet from agent-chosen Memory recall."""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
class JournalSourcePacket(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_: Literal["persona_dream.journal_source_packet.v1"] = Field(alias="schema")
    query: str
    selection_mode: str
    selection: dict[str, Any]
    source_context: str
    entity_relationships: dict[str, Any]


DEFAULT_COLLECTIONS = [
    "persona_memory",
    "persona_journal",
    "persona_entities",
    "persona_memory_edges",
    "persona_memory_entity_edges",
    "tom_edges",
    "agent_conversations",
    "code_symbols",
    "project_activity",
    "project_states",
    "live_evidence_source_context",
    "watch_content",
    "dogpile_research",
]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _read_recall(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("recall JSON root must be an object")
    return payload


def run_memory_recall(*, query: str, collections: list[str], k: int) -> dict[str, Any]:
    memory = REPO_ROOT / "skills" / "memory" / "run.sh"
    cmd = [str(memory), "recall", "-q", query, "--collections", ",".join(collections), "--k", str(k), "--brief"]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, text=True, capture_output=True, check=False, timeout=120)
    if proc.returncode != 0:
        raise SystemExit(f"memory recall failed: {proc.stderr.strip() or proc.stdout.strip()}")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit("memory recall did not return JSON") from exc
    return payload if isinstance(payload, dict) else {"items": []}


def source_context(selection: dict[str, Any]) -> str:
    lines = [
        "# Persona Dream journal source context",
        "",
        f"Query: {selection.get('query', '')}",
        f"Selection mode: {selection.get('selection_mode', 'mixed')}",
        "Boundary: source fuel for dream/journal prose, not a complete report.",
        "",
    ]
    for idx, row in enumerate(selection.get("selected") or [], 1):
        if not isinstance(row, dict):
            continue
        intensity = row.get("intensity") if isinstance(row.get("intensity"), dict) else {}
        lines.extend([
            f"## {idx}. {row.get('source_role', 'supporting_context')} / {row.get('source_collection', 'unknown')}",
            f"Intensity: {intensity.get('bucket', 'unknown')} | reason: {row.get('selection_reason', '')}",
            str(row.get("text") or "").strip(),
            "",
        ])
    return "\n".join(lines).strip() + "\n"


def entity_relationships(selection: dict[str, Any]) -> dict[str, Any]:
    rows = []
    seen: set[str] = set()
    for row in selection.get("selected") or []:
        if not isinstance(row, dict):
            continue
        text = str(row.get("text") or "")
        for entity in re.findall(r"\b[A-Z][A-Za-z0-9_-]{2,}\b", text):
            if entity in seen or entity.upper() == entity:
                continue
            seen.add(entity)
            rows.append({
                "entity": entity,
                "kind": "source_text_entity",
                "relationship": f"mentioned in {row.get('source_role', 'supporting_context')}",
                "source_memory_ids": [],
                "use_boundary": "may ground symbolic journal prose only; do not invent facts",
            })
            if len(rows) >= 24:
                return {"entity_relationships": rows}
    return {"entity_relationships": rows}


def build_packet(*, recall: dict[str, Any], query: str, seed: str, limit: int, mode: str) -> dict[str, Any]:
    selector = _load("journal_memory_selector")
    selection = selector.run(recall, query=query, seed=seed, limit=limit, mode=mode)
    return JournalSourcePacket(
        schema="persona_dream.journal_source_packet.v1",
        query=query,
        selection_mode=mode,
        selection=selection,
        source_context=source_context(selection),
        entity_relationships=entity_relationships(selection),
    ).model_dump(by_alias=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cycle-dir", type=Path, required=True)
    ap.add_argument("--query", required=True)
    ap.add_argument("--mode", choices=["mixed", "intense", "weird", "persona-heavy", "code-heavy", "agent-conversation-heavy", "project-heavy"], default="mixed")
    ap.add_argument("--seed", default="")
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--k", type=int, default=24)
    ap.add_argument("--collections", default=",".join(DEFAULT_COLLECTIONS))
    ap.add_argument("--recall-json", type=Path)
    ap.add_argument("--output", type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    collections = [c.strip() for c in args.collections.split(",") if c.strip()]
    recall = _read_recall(args.recall_json) if args.recall_json else run_memory_recall(query=args.query, collections=collections, k=args.k)
    packet = build_packet(recall=recall, query=args.query, seed=args.seed or args.query, limit=args.limit, mode=args.mode)
    cycle = args.cycle_dir
    cycle.mkdir(parents=True, exist_ok=True)
    (cycle / "journal_memory_selection.json").write_text(json.dumps(packet["selection"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (cycle / "journal_source_context.md").write_text(packet["source_context"], encoding="utf-8")
    (cycle / "journal_entity_relationships.json").write_text(json.dumps(packet["entity_relationships"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    out_path = args.output or cycle / "journal_source_packet.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(packet, indent=2, sort_keys=True))
    else:
        print("JOURNAL_SOURCE_PACKET_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
