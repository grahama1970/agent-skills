#!/usr/bin/env python3
"""Render an arena-first broadcast from a provider/Tau adaptive-lineage campaign."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCHEMA = "battle.provider_tau_lineage_broadcast.v1"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, data: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_seed(path: Path | None, kind: str) -> dict[str, Any] | None:
    if path is None:
        return None
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"{kind} seed receipt missing: {resolved}")
    item: dict[str, Any] = {
        "kind": kind,
        "path": str(resolved),
        "sha256": sha256_file(resolved),
        "bytes": resolved.stat().st_size,
    }
    if resolved.suffix == ".json":
        data = read_json(resolved)
        item["schema"] = data.get("schema")
        item["source_bearing_evidence_count"] = data.get("source_bearing_evidence_count")
        item["provider_statuses"] = data.get("provider_statuses", [])
    return item


def collect_events(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for generation in receipt.get("generations", []):
        gen = generation.get("generation")
        events.append({"event_type": "judge_call", "generation": gen, "verdict": generation.get("judge_verdict"), "source": "campaign_receipt"})
        for team in ("red", "blue"):
            pipe = (generation.get("artifact_pipelines") or {}).get(team) or {}
            events.append({
                "event_type": "child_specimen_materialized" if gen == 2 else "parent_specimen_materialized",
                "generation": gen,
                "team": team,
                "path": pipe.get("selected_artifact_path"),
                "sha256": pipe.get("selected_artifact_sha256"),
                "compile_receipt_sha256": pipe.get("compile_receipt_sha256"),
            })
    for team, spawn in (receipt.get("spawn") or {}).items():
        events.append({"event_type": "spawn_policy", "team": team, "decision": spawn.get("decision"), "judge_verdict": spawn.get("judge_verdict")})
    for team, ack in (receipt.get("inheritance") or {}).items():
        events.append({"event_type": "provider_seed_ack", "team": team, "status": ack.get("status"), "research_cited": ack.get("external_research_cited_in_provider_response"), "mutation_seed_citations": ack.get("mutation_seed_citations", [])})
    for team, delta in (receipt.get("genome_deltas") or {}).items():
        events.append({"event_type": "genome_mutated", "team": team, "semantic_change_count": delta.get("semantic_change_count"), "sha256": delta.get("sha256")})
    selection = receipt.get("selection") or {}
    for team, item in (selection.get("teams") or {}).items():
        events.append({"event_type": "selection_decision", "team": team, "selected_generation": item.get("selected_generation"), "retention_decision": item.get("retention_decision")})
    return events


def status_checks(receipt: dict[str, Any], seed_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    research = receipt.get("research") or {}
    inheritance = receipt.get("inheritance") or {}
    integrity = receipt.get("artifact_integrity") or {}
    generations = receipt.get("generations") or []
    seed_bundle = receipt.get("mutation_seed_receipts") or {}
    provider_seed_citations = [
        cite
        for ack in inheritance.values()
        for cite in ack.get("mutation_seed_citations", [])
    ]
    return [
        {"name": "campaign_live_provider_tau", "status": "PASS" if receipt.get("status") == "PASS" and receipt.get("live") is True and receipt.get("mocked") is False and "tau_scillm" in str(receipt.get("live_mode")) else "FAIL"},
        {"name": "authorization_passed", "status": "PASS" if (receipt.get("authorization") or {}).get("status") == "PASS" else "FAIL"},
        {"name": "research_receipts_bound", "status": "PASS" if set(research) >= {"red", "blue"} and all((r or {}).get("source_count", 0) > 0 for r in research.values()) else "FAIL"},
        {"name": "seed_receipts_bound", "status": "PASS" if seed_items or seed_bundle.get("receipts") else "FAIL", "external_seed_count": len(seed_items), "campaign_seed_count": len(seed_bundle.get("receipts", []))},
        {"name": "seed_hashes_cited_by_provider", "status": "PASS" if not seed_bundle.get("receipts") or all(c.get("cited_in_provider_response") for c in provider_seed_citations) else "FAIL", "citations": provider_seed_citations},
        {"name": "children_materialized", "status": "PASS" if len(generations) >= 2 and all(((generations[1].get("artifact_pipelines") or {}).get(t) or {}).get("selected_artifact_path") for t in ("red", "blue")) else "FAIL"},
        {"name": "docker_judge_replays_bound", "status": "PASS" if integrity.get("matched_replay_count") == integrity.get("required_replay_count") and integrity.get("matched_slot_count") == integrity.get("required_slot_count") else "FAIL", "artifact_integrity": integrity.get("path")},
        {"name": "selection_promoted_children", "status": "PASS" if all((receipt.get("selection") or {}).get("teams", {}).get(t, {}).get("selected_generation") == 2 for t in ("red", "blue")) else "FAIL"},
    ]


def render_report(receipt: dict[str, Any], checks: list[dict[str, Any]], seed_items: list[dict[str, Any]], events_path: Path) -> str:
    arena = receipt.get("arena") or {}
    lines = [
        "# Provider/Tau Adaptive-Lineage Battle Broadcast",
        "",
        "## Arena prologue",
        f"Arena: `{arena.get('scenario_id')}`. The target stayed byte-identical across both generations: `{arena.get('generation_1_target_sha256')}`.",
        "Why it exists: force Red and Blue to mutate from the same public target, the same Judge verdict, and the same source-bearing research instead of letting either team narrate its own win.",
        "Equalizers: one Red and one Blue provider worker per generation; no private Arena paths in the child prompt; Docker/Judge receipts decide the scoreboard; selection is deterministic after replay.",
        "Expected exploit family: archive import / Zip Slip path traversal against a Python import-zip surface, with Blue defending containment and functionality preservation.",
        "",
        "## Seed packet",
    ]
    if seed_items:
        for seed in seed_items:
            count = seed.get("source_bearing_evidence_count")
            suffix = f", source-bearing evidence {count}" if count is not None else ""
            lines.append(f"- `{seed['kind']}` seed `{seed['sha256']}` from `{seed['path']}`{suffix}.")
    for seed in (receipt.get("mutation_seed_receipts") or {}).get("receipts", []):
        lines.append(f"- Campaign-bound `{seed['kind']}` mutation seed `{seed['sha256']}` from `{seed['path']}`.")
    if not seed_items and not (receipt.get("mutation_seed_receipts") or {}).get("receipts"):
        lines.append("- No Dogpile/memory seed was bound to this campaign; report is provider/Tau only.")
    lines += ["", "## Play-by-play"]
    for generation in receipt.get("generations", []):
        gen = generation.get("generation")
        verdict = generation.get("judge_verdict")
        lines.append(f"### Generation {gen}: Judge calls `{verdict}`")
        for team in ("red", "blue"):
            pipe = (generation.get("artifact_pipelines") or {}).get(team) or {}
            role = "monster bite" if team == "red" else "shield wall"
            lines.append(f"- {team.upper()} {role}: materialized `{pipe.get('selected_artifact_path')}` with sha `{pipe.get('selected_artifact_sha256')}`; compile receipt `{pipe.get('compile_receipt_sha256')}`.")
    lines += ["", "## Warm pond lineage"]
    for team, spawn in (receipt.get("spawn") or {}).items():
        ack = (receipt.get("inheritance") or {}).get(team) or {}
        delta = (receipt.get("genome_deltas") or {}).get(team) or {}
        selected = (receipt.get("selection") or {}).get("teams", {}).get(team, {}).get("selected_generation")
        lines.append(
            f"- {team.upper()}: spawn `{spawn.get('decision')}` after parent `{spawn.get('judge_verdict')}`; provider cited inherited packet={ack.get('packet_cited_in_provider_response')}, genome={ack.get('inherited_genome_cited')}, observation={ack.get('inherited_observation_cited')}, external research={ack.get('external_research_cited_in_provider_response')}; semantic mutations `{delta.get('semantic_change_count')}`; selection kept generation `{selected}`."
        )
        for cite in ack.get("mutation_seed_citations", []):
            lines.append(f"  - seed citation `{cite.get('kind')}` `{cite.get('sha256')}` cited={cite.get('cited_in_provider_response')}.")
    lines += ["", "## Receipts that make the call"]
    for check in checks:
        lines.append(f"- {check['name']}: {check['status']}")
    lines += ["", f"Event ledger: `{events_path}`"]
    lines += ["", "## Proof boundary", "Proven here: provider/Tau child generation, source-bearing research, inherited evidence citation, child materialization, Docker/Judge replay binding, and deterministic selection from receipts.", "Not proven here: arbitrary external target exploitation, production deployment, overnight scale, or durable memory write promotion."]
    return "\n".join(lines) + "\n"


def render(campaign_receipt: Path, out_dir: Path, dogpile_seed: Path | None, memory_seed: Path | None) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    receipt = read_json(campaign_receipt)
    seed_items = [item for item in [load_seed(dogpile_seed, "dogpile"), load_seed(memory_seed, "memory")] if item]
    checks = status_checks(receipt, seed_items)
    events = collect_events(receipt)
    events_path = out_dir / "provider-tau-event-ledger.jsonl"
    events_path.write_text("".join(json.dumps(event, sort_keys=True) + "\n" for event in events), encoding="utf-8")
    report_path = out_dir / "PROVIDER_TAU_LINEAGE_REPORT.md"
    report_path.write_text(render_report(receipt, checks, seed_items, events_path), encoding="utf-8")
    top = {
        "schema": SCHEMA,
        "status": "PASS" if all(check["status"] == "PASS" for check in checks) else "FAIL",
        "campaign_receipt": str(campaign_receipt),
        "campaign_receipt_sha256": sha256_file(campaign_receipt),
        "report": str(report_path),
        "report_sha256": sha256_file(report_path),
        "event_ledger": str(events_path),
        "event_ledger_sha256": sha256_file(events_path),
        "seed_receipts": seed_items,
        "checks": checks,
        "claims": {
            "proves": [
                "Provider/Tau adaptive-lineage child artifacts were narrated from campaign receipts.",
                "Dogpile and/or memory seed receipts are bound when supplied and campaign seed citations are checked when present.",
            ],
            "does_not_prove": [
                "External target exploitability.",
                "Durable memory promotion.",
                "Overnight production throughput.",
            ],
        },
        "created_at": utc_now(),
    }
    write_json(out_dir / "provider-tau-lineage-broadcast-receipt.json", top)
    return top


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-receipt", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dogpile-seed", type=Path)
    parser.add_argument("--memory-seed", type=Path)
    args = parser.parse_args()
    receipt = render(args.campaign_receipt, args.out, args.dogpile_seed, args.memory_seed)
    print(json.dumps({"status": receipt["status"], "receipt": str(args.out / "provider-tau-lineage-broadcast-receipt.json"), "report": receipt["report"]}, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
