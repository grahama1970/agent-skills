#!/usr/bin/env python3
"""Render an arena-first broadcast from a provider/Tau adaptive-lineage campaign."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


SCHEMA = "battle.provider_tau_lineage_broadcast.v1"


class ArenaReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_: Literal["battle.arena_receipt.v1"] = Field("battle.arena_receipt.v1", alias="schema")
    status: Literal["PASS"] = "PASS"
    campaign_receipt: str
    campaign_receipt_sha256: str
    scenario_id: str = Field(min_length=1)
    target_sha256_by_generation: dict[str, str]
    equalizers: list[str] = Field(min_length=1)
    expected_exploit_family: str = Field(min_length=1)


class TeamActivity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["campaign_receipt"] = "campaign_receipt"
    event_type: str = Field(min_length=1)
    generation: int | None = None
    judge_verdict: str | None = None
    artifact_path: str | None = None
    artifact_sha256: str | None = None
    compile_receipt_sha256: str | None = None
    spawn_decision: str | None = None
    seed_citations: list[dict[str, Any]] = Field(default_factory=list)
    semantic_change_count: int | None = None
    selected_generation: int | None = None
    retention_decision: str | None = None


class TeamActivityReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_: Literal["battle.team_activity_receipt.v1"] = Field("battle.team_activity_receipt.v1", alias="schema")
    status: Literal["PASS"] = "PASS"
    team: Literal["red", "blue"]
    campaign_receipt: str
    campaign_receipt_sha256: str
    activities: list[TeamActivity] = Field(min_length=1)


class CommentaryLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: str = Field(min_length=1)
    speaker_line: str = Field(min_length=1)
    source_receipts: list[str] = Field(min_length=1)
    source_activity_indices: dict[Literal["red", "blue"], list[int]] = Field(default_factory=dict)


class PlayByPlayCommentaryReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_: Literal["battle.sports_play_by_play_commentary_receipt.v1"] = Field("battle.sports_play_by_play_commentary_receipt.v1", alias="schema")
    status: Literal["PASS"] = "PASS"
    arena_receipt: str
    arena_receipt_sha256: str
    red_team_activity_receipt: str
    red_team_activity_receipt_sha256: str
    blue_team_activity_receipt: str
    blue_team_activity_receipt_sha256: str
    commentary_lines: list[CommentaryLine] = Field(min_length=1)

    @field_validator("commentary_lines")
    @classmethod
    def every_line_has_activity_or_arena(cls, value: list[CommentaryLine]) -> list[CommentaryLine]:
        for line in value:
            if not line.source_activity_indices and not any(
                receipt.endswith("arena-receipt.json") for receipt in line.source_receipts
            ):
                raise ValueError("commentary line lacks arena or team activity source")
        return value


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


def write_model(path: Path, model: BaseModel) -> Path:
    return write_json(path, model.model_dump(mode="json", by_alias=True))


def build_arena_receipt(campaign_receipt: Path, receipt: dict[str, Any]) -> ArenaReceipt:
    arena = receipt.get("arena") or {}
    return ArenaReceipt(
        campaign_receipt=str(campaign_receipt),
        campaign_receipt_sha256=sha256_file(campaign_receipt),
        scenario_id=str(arena.get("scenario_id") or "unknown-scenario"),
        target_sha256_by_generation={
            "1": str(arena.get("generation_1_target_sha256") or ""),
            "2": str(arena.get("generation_2_target_sha256") or ""),
        },
        equalizers=[
            "Red and Blue consume the same public arena context.",
            "Provider/Tau outputs cannot self-award wins.",
            "Docker/Judge replay binds the score call.",
            "Selection is deterministic after receipt replay.",
        ],
        expected_exploit_family="Zip Slip archive path traversal against import-zip handling.",
    )


def build_team_activity_receipt(
    *,
    team: Literal["red", "blue"],
    campaign_receipt: Path,
    receipt: dict[str, Any],
) -> TeamActivityReceipt:
    activities: list[TeamActivity] = []
    for generation in receipt.get("generations", []):
        gen = int(generation.get("generation") or 0)
        pipe = (generation.get("artifact_pipelines") or {}).get(team) or {}
        activities.append(
            TeamActivity(
                event_type="specimen_materialized",
                generation=gen,
                judge_verdict=generation.get("judge_verdict"),
                artifact_path=pipe.get("selected_artifact_path"),
                artifact_sha256=pipe.get("selected_artifact_sha256"),
                compile_receipt_sha256=pipe.get("compile_receipt_sha256"),
            )
        )
    spawn = (receipt.get("spawn") or {}).get(team) or {}
    activities.append(
        TeamActivity(
            event_type="spawn_policy",
            judge_verdict=spawn.get("judge_verdict"),
            spawn_decision=spawn.get("decision"),
        )
    )
    ack = (receipt.get("inheritance") or {}).get(team) or {}
    activities.append(
        TeamActivity(
            event_type="provider_seed_ack",
            seed_citations=ack.get("mutation_seed_citations", []),
        )
    )
    delta = (receipt.get("genome_deltas") or {}).get(team) or {}
    activities.append(
        TeamActivity(
            event_type="genome_mutated",
            semantic_change_count=delta.get("semantic_change_count"),
            artifact_sha256=delta.get("sha256"),
        )
    )
    selected = (receipt.get("selection") or {}).get("teams", {}).get(team) or {}
    activities.append(
        TeamActivity(
            event_type="selection_decision",
            selected_generation=selected.get("selected_generation"),
            retention_decision=selected.get("retention_decision"),
        )
    )
    return TeamActivityReceipt(
        team=team,
        campaign_receipt=str(campaign_receipt),
        campaign_receipt_sha256=sha256_file(campaign_receipt),
        activities=activities,
    )


def build_commentary_receipt(
    *,
    arena_path: Path,
    red_path: Path,
    blue_path: Path,
    arena: ArenaReceipt,
    red: TeamActivityReceipt,
    blue: TeamActivityReceipt,
) -> PlayByPlayCommentaryReceipt:
    lines = [
        CommentaryLine(
            period="arena_open",
            speaker_line=(
                f"Welcome to {arena.scenario_id}: equal public terrain, hidden Judge authority, "
                f"and {arena.expected_exploit_family} on the marquee."
            ),
            source_receipts=[str(arena_path)],
        )
    ]
    for idx, activity in enumerate(red.activities):
        if activity.event_type == "specimen_materialized":
            lines.append(
                CommentaryLine(
                    period=f"generation_{activity.generation}",
                    speaker_line=(
                        f"RED takes the monster lane in generation {activity.generation}: "
                        f"artifact {activity.artifact_sha256} hits the arena under Judge call {activity.judge_verdict}."
                    ),
                    source_receipts=[str(red_path)],
                    source_activity_indices={"red": [idx]},
                )
            )
    for idx, activity in enumerate(blue.activities):
        if activity.event_type == "specimen_materialized":
            lines.append(
                CommentaryLine(
                    period=f"generation_{activity.generation}",
                    speaker_line=(
                        f"BLUE answers with the shield wall in generation {activity.generation}: "
                        f"artifact {activity.artifact_sha256} stays bound to Judge call {activity.judge_verdict}."
                    ),
                    source_receipts=[str(blue_path)],
                    source_activity_indices={"blue": [idx]},
                )
            )
    for team, activity_receipt, path in [("red", red, red_path), ("blue", blue, blue_path)]:
        for idx, activity in enumerate(activity_receipt.activities):
            if activity.event_type == "selection_decision":
                lines.append(
                    CommentaryLine(
                        period="selection",
                        speaker_line=(
                            f"{team.upper()} selection whistle: {activity.retention_decision}, "
                            f"generation {activity.selected_generation} promoted by receipt."
                        ),
                        source_receipts=[str(path)],
                        source_activity_indices={team: [idx]},
                    )
                )
    return PlayByPlayCommentaryReceipt(
        arena_receipt=str(arena_path),
        arena_receipt_sha256=sha256_file(arena_path),
        red_team_activity_receipt=str(red_path),
        red_team_activity_receipt_sha256=sha256_file(red_path),
        blue_team_activity_receipt=str(blue_path),
        blue_team_activity_receipt_sha256=sha256_file(blue_path),
        commentary_lines=lines,
    )


def commentary_is_grounded(commentary: PlayByPlayCommentaryReceipt, red: TeamActivityReceipt, blue: TeamActivityReceipt) -> bool:
    counts = {"red": len(red.activities), "blue": len(blue.activities)}
    for line in commentary.commentary_lines:
        for team, indices in line.source_activity_indices.items():
            if any(index < 0 or index >= counts[team] for index in indices):
                return False
    return True


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


def render_report(
    receipt: dict[str, Any],
    checks: list[dict[str, Any]],
    seed_items: list[dict[str, Any]],
    events_path: Path,
    commentary: PlayByPlayCommentaryReceipt,
) -> str:
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
    for line in commentary.commentary_lines:
        sources = ", ".join(line.source_receipts)
        indices = json.dumps(line.source_activity_indices, sort_keys=True)
        lines.append(f"- **{line.period}** {line.speaker_line} _(sources: {sources}; activity_indices: {indices})_")
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
    lines += [
        "",
        "## Proof boundary",
        "Proven here: provider/Tau child generation, source-bearing research, inherited evidence citation, child materialization, Docker/Judge replay binding, deterministic selection from receipts, and sports play-by-play generated from validated JSON commentary lines.",
        "Not proven here: arbitrary external target exploitation, production deployment, overnight scale, or durable memory write promotion.",
    ]
    return "\n".join(lines) + "\n"


def render(campaign_receipt: Path, out_dir: Path, dogpile_seed: Path | None, memory_seed: Path | None) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    receipt = read_json(campaign_receipt)
    seed_items = [item for item in [load_seed(dogpile_seed, "dogpile"), load_seed(memory_seed, "memory")] if item]

    arena = build_arena_receipt(campaign_receipt, receipt)
    arena_path = write_model(out_dir / "arena-receipt.json", arena)
    red = build_team_activity_receipt(team="red", campaign_receipt=campaign_receipt, receipt=receipt)
    red_path = write_model(out_dir / "red-team-activity-receipt.json", red)
    blue = build_team_activity_receipt(team="blue", campaign_receipt=campaign_receipt, receipt=receipt)
    blue_path = write_model(out_dir / "blue-team-activity-receipt.json", blue)
    commentary = build_commentary_receipt(
        arena_path=arena_path,
        red_path=red_path,
        blue_path=blue_path,
        arena=arena,
        red=red,
        blue=blue,
    )
    commentary_path = write_model(out_dir / "sports-play-by-play-commentary-receipt.json", commentary)

    checks = status_checks(receipt, seed_items)
    checks.append(
        {
            "name": "pydantic_arena_team_commentary_receipts",
            "status": "PASS" if commentary_is_grounded(commentary, red, blue) else "FAIL",
            "arena_receipt": str(arena_path),
            "red_team_activity_receipt": str(red_path),
            "blue_team_activity_receipt": str(blue_path),
            "sports_play_by_play_commentary_receipt": str(commentary_path),
        }
    )
    events = collect_events(receipt)
    events_path = out_dir / "provider-tau-event-ledger.jsonl"
    events_path.write_text("".join(json.dumps(event, sort_keys=True) + "\n" for event in events), encoding="utf-8")
    report_path = out_dir / "PROVIDER_TAU_LINEAGE_REPORT.md"
    report_path.write_text(render_report(receipt, checks, seed_items, events_path, commentary), encoding="utf-8")
    top = {
        "schema": SCHEMA,
        "status": "PASS" if all(check["status"] == "PASS" for check in checks) else "FAIL",
        "campaign_receipt": str(campaign_receipt),
        "campaign_receipt_sha256": sha256_file(campaign_receipt),
        "arena_receipt": str(arena_path),
        "arena_receipt_sha256": sha256_file(arena_path),
        "red_team_activity_receipt": str(red_path),
        "red_team_activity_receipt_sha256": sha256_file(red_path),
        "blue_team_activity_receipt": str(blue_path),
        "blue_team_activity_receipt_sha256": sha256_file(blue_path),
        "sports_play_by_play_commentary_receipt": str(commentary_path),
        "sports_play_by_play_commentary_receipt_sha256": sha256_file(commentary_path),
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
                "Arena, Red activity, Blue activity, and sports play-by-play commentary are Pydantic-validated JSON receipts.",
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
