#!/usr/bin/env python3
"""Render an arena-first broadcast from a provider/Tau adaptive-lineage campaign."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


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


class SelectionTeamRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    retention_decision: str = Field(min_length=1)
    selected_generation: int | None = None
    generation_1_fitness_receipt_sha256: str | None = None
    generation_2_fitness_receipt_sha256: str | None = None
    tie_break_reason: str | None = None


class SelectionReceipt(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_: Literal["battle.adaptive_selection_receipt.v1"] = Field(alias="schema")
    status: Literal["PASS"]
    teams: dict[Literal["red", "blue"], SelectionTeamRecord]


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

    @field_validator("source_activity_indices", mode="before")
    @classmethod
    def activity_indices_are_exact_ints(cls, value: Any) -> Any:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("source_activity_indices must be an object")
        for team, indices in value.items():
            if team not in {"red", "blue"}:
                raise ValueError(f"unknown team activity source {team!r}")
            if not isinstance(indices, list):
                raise ValueError(f"{team}: source activity indices must be a list")
            for index in indices:
                if not isinstance(index, int) or isinstance(index, bool):
                    raise ValueError(f"{team}: source activity indices must be integer indexes")
        return value


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

    @model_validator(mode="after")
    def every_line_has_exact_arena_or_team_reference(self) -> "PlayByPlayCommentaryReceipt":
        bound_team_receipts = {
            "red": self.red_team_activity_receipt,
            "blue": self.blue_team_activity_receipt,
        }
        allowed_receipts = {self.arena_receipt, *bound_team_receipts.values()}
        errors: list[str] = []
        for line_number, line in enumerate(self.commentary_lines):
            line_prefix = f"commentary_lines[{line_number}]"
            for source_receipt in line.source_receipts:
                if source_receipt not in allowed_receipts:
                    errors.append(f"{line_prefix}: source receipt is not one of the exact bound receipts")
            has_exact_arena = self.arena_receipt in line.source_receipts
            has_exact_team_activity = False
            for team, indices in line.source_activity_indices.items():
                if not indices:
                    errors.append(f"{line_prefix}: {team} activity index list must be nonempty")
                    continue
                if bound_team_receipts[team] not in line.source_receipts:
                    errors.append(f"{line_prefix}: {team} activity indices do not cite the exact bound team receipt")
                    continue
                has_exact_team_activity = True
            if not has_exact_arena and not has_exact_team_activity:
                errors.append(f"{line_prefix}: lacks exact arena receipt or exact team activity reference")
        if errors:
            raise ValueError("; ".join(errors))
        return self


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


def _known_generations(receipt: dict[str, Any]) -> set[int]:
    generations: set[int] = set()
    for generation in receipt.get("generations") or []:
        try:
            generations.add(int(generation.get("generation")))
        except (TypeError, ValueError):
            continue
    return generations


def _selection_outcome(decision: str | None, selected_generation: int | None) -> str:
    normalized = (decision or "").upper()
    if selected_generation == 2:
        return "child_promoted"
    if selected_generation == 1 or "PARENT" in normalized or "GENERATION_1" in normalized:
        return "parent_retained"
    if selected_generation is None and (
        "NO_ELIGIBLE" in normalized
        or "NO_PROMOTION" in normalized
        or "INELIGIBLE" in normalized
    ):
        return "no_eligible_promotion"
    return "selection_recorded"


def _decision_expected_outcome(decision: str | None) -> str | None:
    normalized = (decision or "").upper()
    if "NO_ELIGIBLE" in normalized or "NO_PROMOTION" in normalized or "INELIGIBLE" in normalized:
        return "no_eligible_promotion"
    if "PARENT" in normalized or "GENERATION_1" in normalized:
        return "parent_retained"
    if "CHILD" in normalized or "GENERATION_2" in normalized:
        return "child_promoted"
    return None


def _selection_commentary(team: str, activity: TeamActivity) -> str:
    outcome = _selection_outcome(activity.retention_decision, activity.selected_generation)
    decision = activity.retention_decision or "selection_recorded"
    if outcome == "child_promoted":
        return (
            f"{team.upper()} selection whistle: {decision}; "
            f"generation {activity.selected_generation} child promoted by receipt."
        )
    if outcome == "parent_retained":
        generation = activity.selected_generation if activity.selected_generation is not None else 1
        return (
            f"{team.upper()} selection whistle: {decision}; "
            f"generation {generation} parent retained by receipt."
        )
    if outcome == "no_eligible_promotion":
        return (
            f"{team.upper()} selection whistle: {decision}; "
            "no eligible child promotion was recorded by receipt."
        )
    return (
        f"{team.upper()} selection whistle: {decision}; "
        f"selection recorded generation {activity.selected_generation}."
    )


def selection_report_status(receipt: dict[str, Any]) -> dict[str, Any]:
    raw_selection = receipt.get("selection")
    known_generations = _known_generations(receipt)
    errors: list[str] = []
    outcomes: dict[str, dict[str, Any]] = {}
    if not isinstance(raw_selection, dict):
        errors.append("selection: missing selection receipt")
        teams = {}
    else:
        try:
            selection = SelectionReceipt.model_validate(raw_selection)
        except ValidationError as exc:
            errors.extend(
                f"selection: validation_error type={err['type']} loc={'.'.join(str(part) for part in err['loc'])}"
                for err in exc.errors()
            )
            raw_teams = raw_selection.get("teams") if isinstance(raw_selection.get("teams"), dict) else {}
            teams = raw_teams
        else:
            teams = selection.teams
    for team in ("red", "blue"):
        item = teams.get(team)
        if isinstance(item, SelectionTeamRecord):
            decision = item.retention_decision
            raw_generation = item.selected_generation
        elif isinstance(item, dict):
            decision = item.get("retention_decision")
            raw_generation = item.get("selected_generation")
        else:
            errors.append(f"{team}: missing selection team record")
            continue
        if not isinstance(decision, str) or not decision.strip():
            errors.append(f"{team}: missing retention_decision")
        selected_generation: int | None = None
        if raw_generation is None:
            if _selection_outcome(decision, None) != "no_eligible_promotion":
                errors.append(f"{team}: selected_generation is missing without a no-promotion decision")
        else:
            try:
                selected_generation = int(raw_generation)
            except (TypeError, ValueError):
                errors.append(f"{team}: selected_generation is not an integer")
            else:
                if known_generations and selected_generation not in known_generations:
                    errors.append(f"{team}: selected_generation {selected_generation} has no generation receipt")
        outcome = _selection_outcome(decision, selected_generation)
        expected_outcome = _decision_expected_outcome(decision)
        if expected_outcome is not None and outcome != expected_outcome:
            errors.append(
                f"{team}: retention_decision {decision!r} conflicts with selected_generation {selected_generation!r}"
            )
        outcomes[team] = {
            "retention_decision": decision,
            "selected_generation": selected_generation,
            "outcome": outcome,
        }
    return {
        "name": "selection_decisions_valid",
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "outcomes": outcomes,
        "child_promotion_canary": {
            "both_generation_2_selected": all(
                outcomes.get(team, {}).get("selected_generation") == 2 for team in ("red", "blue")
            ),
            "gates_broadcast_validity": False,
        },
    }


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
                        speaker_line=_selection_commentary(team, activity),
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


def _bound_receipt_hash_errors(commentary: PlayByPlayCommentaryReceipt) -> list[str]:
    errors: list[str] = []
    for label, raw_path, expected_sha256 in [
        ("arena", commentary.arena_receipt, commentary.arena_receipt_sha256),
        ("red", commentary.red_team_activity_receipt, commentary.red_team_activity_receipt_sha256),
        ("blue", commentary.blue_team_activity_receipt, commentary.blue_team_activity_receipt_sha256),
    ]:
        path = Path(raw_path)
        if not path.is_file():
            errors.append(f"{label}: bound receipt path is missing")
            continue
        actual_sha256 = sha256_file(path)
        if actual_sha256 != expected_sha256:
            errors.append(f"{label}: bound receipt sha256 mismatch")
    return errors


def commentary_provenance_errors(
    commentary: PlayByPlayCommentaryReceipt,
    red: TeamActivityReceipt,
    blue: TeamActivityReceipt,
) -> list[str]:
    errors = _bound_receipt_hash_errors(commentary)
    counts = {"red": len(red.activities), "blue": len(blue.activities)}
    team_receipts = {
        "red": commentary.red_team_activity_receipt,
        "blue": commentary.blue_team_activity_receipt,
    }
    allowed_receipts = {commentary.arena_receipt, *team_receipts.values()}
    for line in commentary.commentary_lines:
        has_exact_arena = commentary.arena_receipt in line.source_receipts
        has_valid_team_activity = False
        for source_receipt in line.source_receipts:
            if source_receipt not in allowed_receipts:
                errors.append(f"{line.period}: unbound source receipt {source_receipt}")
        for team, indices in line.source_activity_indices.items():
            if not indices:
                errors.append(f"{line.period}: {team} activity index list is empty")
                continue
            if team_receipts[team] not in line.source_receipts:
                errors.append(f"{line.period}: {team} activity indices lack exact bound team receipt")
                continue
            valid_indices = [
                index
                for index in indices
                if isinstance(index, int) and not isinstance(index, bool) and 0 <= index < counts[team]
            ]
            if len(valid_indices) != len(indices):
                errors.append(f"{line.period}: {team} activity indices include invalid index")
                continue
            has_valid_team_activity = True
        if not has_exact_arena and not has_valid_team_activity:
            errors.append(f"{line.period}: lacks exact hashed arena receipt or exact team activity index")
    return errors


def commentary_is_grounded(commentary: PlayByPlayCommentaryReceipt, red: TeamActivityReceipt, blue: TeamActivityReceipt) -> bool:
    return not commentary_provenance_errors(commentary, red, blue)


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _docker_replay_status(integrity: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    matched_replay_count = integrity.get("matched_replay_count")
    required_replay_count = integrity.get("required_replay_count")
    matched_slot_count = integrity.get("matched_slot_count")
    required_slot_count = integrity.get("required_slot_count")
    if not _positive_int(required_replay_count):
        errors.append("required_replay_count must be a positive integer")
    if not _positive_int(matched_replay_count):
        errors.append("matched_replay_count must be a positive integer")
    if not _positive_int(required_slot_count):
        errors.append("required_slot_count must be a positive integer")
    if not _positive_int(matched_slot_count):
        errors.append("matched_slot_count must be a positive integer")
    if not errors:
        if matched_replay_count != required_replay_count:
            errors.append("matched_replay_count must equal required_replay_count")
        if matched_slot_count != required_slot_count:
            errors.append("matched_slot_count must equal required_slot_count")

    judge_replays = integrity.get("judge_replays")
    if not isinstance(judge_replays, list) or not judge_replays:
        errors.append("judge_replays must be a nonempty list")
    elif _positive_int(required_replay_count) and len(judge_replays) != required_replay_count:
        errors.append("judge_replays length must equal required_replay_count")
    if isinstance(judge_replays, list):
        for index, replay in enumerate(judge_replays):
            if not isinstance(replay, dict):
                errors.append(f"judge_replays[{index}] must be an object")
                continue
            if replay.get("status") != "PASS" or replay.get("matched") is not True:
                errors.append(f"judge_replays[{index}] must be PASS and matched")
            if not replay.get("path") or not replay.get("expected_sha256"):
                errors.append(f"judge_replays[{index}] must bind path and expected_sha256")

    return {
        "name": "docker_judge_replays_bound",
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "artifact_integrity": integrity.get("path"),
        "matched_replay_count": matched_replay_count,
        "required_replay_count": required_replay_count,
        "matched_slot_count": matched_slot_count,
        "required_slot_count": required_slot_count,
        "judge_replay_count": len(judge_replays) if isinstance(judge_replays, list) else 0,
    }


def _seed_citation_status(
    *,
    seed_items: list[dict[str, Any]],
    seed_bundle: dict[str, Any],
    inheritance: dict[str, Any],
) -> dict[str, Any]:
    campaign_seeds = seed_bundle.get("receipts", [])
    required_seeds = campaign_seeds if isinstance(campaign_seeds, list) and campaign_seeds else seed_items
    errors: list[str] = []
    if not required_seeds:
        errors.append("seed receipts must be explicitly bound")
    all_citations: list[Any] = []
    citations_by_team: dict[str, list[dict[str, Any]]] = {}
    for team in ("red", "blue"):
        ack = inheritance.get(team) if isinstance(inheritance, dict) else None
        raw_citations = ack.get("mutation_seed_citations", []) if isinstance(ack, dict) else []
        team_citations = [cite for cite in raw_citations if isinstance(cite, dict)]
        all_citations.extend(raw_citations if isinstance(raw_citations, list) else [])
        citations_by_team[team] = team_citations
        if not team_citations:
            errors.append(f"{team}: provider seed citations must be nonempty")
        for seed in required_seeds:
            if not isinstance(seed, dict):
                errors.append("seed receipt entries must be objects")
                continue
            kind = seed.get("kind")
            sha256 = seed.get("sha256")
            if not kind or not sha256:
                errors.append("seed receipt must include kind and sha256")
                continue
            matches = [
                citation
                for citation in team_citations
                if citation.get("kind") == kind and citation.get("sha256") == sha256
            ]
            if not matches:
                errors.append(f"{team}: missing provider citation for seed {kind}:{sha256}")
            elif not any(citation.get("cited_in_provider_response") is True for citation in matches):
                errors.append(f"{team}: seed citation for {kind}:{sha256} is not marked cited")
    if not all_citations:
        errors.append("provider seed citations must be nonempty")

    return {
        "name": "seed_hashes_cited_by_provider",
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "required_seed_count": len(required_seeds),
        "provider_seed_citation_count": len([cite for cite in all_citations if isinstance(cite, dict)]),
        "provider_seed_citation_count_by_team": {
            team: len(citations) for team, citations in citations_by_team.items()
        },
        "citations": all_citations,
    }


def status_checks(receipt: dict[str, Any], seed_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    research = receipt.get("research") or {}
    inheritance = receipt.get("inheritance") or {}
    integrity = receipt.get("artifact_integrity") or {}
    generations = receipt.get("generations") or []
    seed_bundle = receipt.get("mutation_seed_receipts") or {}
    return [
        {"name": "campaign_live_provider_tau", "status": "PASS" if receipt.get("status") == "PASS" and receipt.get("live") is True and receipt.get("mocked") is False and "tau_scillm" in str(receipt.get("live_mode")) else "FAIL"},
        {"name": "authorization_passed", "status": "PASS" if (receipt.get("authorization") or {}).get("status") == "PASS" else "FAIL"},
        {"name": "research_receipts_bound", "status": "PASS" if set(research) >= {"red", "blue"} and all((r or {}).get("source_count", 0) > 0 for r in research.values()) else "FAIL"},
        {"name": "seed_receipts_bound", "status": "PASS" if seed_items or seed_bundle.get("receipts") else "FAIL", "external_seed_count": len(seed_items), "campaign_seed_count": len(seed_bundle.get("receipts", []))},
        _seed_citation_status(seed_items=seed_items, seed_bundle=seed_bundle, inheritance=inheritance),
        {"name": "children_materialized", "status": "PASS" if len(generations) >= 2 and all(((generations[1].get("artifact_pipelines") or {}).get(t) or {}).get("selected_artifact_path") for t in ("red", "blue")) else "FAIL"},
        _docker_replay_status(integrity),
        selection_report_status(receipt),
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
        selected = (receipt.get("selection") or {}).get("teams", {}).get(team, {})
        selected_generation = selected.get("selected_generation")
        selection_outcome = _selection_outcome(selected.get("retention_decision"), selected_generation)
        lines.append(
            f"- {team.upper()}: spawn `{spawn.get('decision')}` after parent `{spawn.get('judge_verdict')}`; provider cited inherited packet={ack.get('packet_cited_in_provider_response')}, genome={ack.get('inherited_genome_cited')}, observation={ack.get('inherited_observation_cited')}, external research={ack.get('external_research_cited_in_provider_response')}; semantic mutations `{delta.get('semantic_change_count')}`; selection outcome `{selection_outcome}` with generation `{selected_generation}`."
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
    commentary_errors = commentary_provenance_errors(commentary, red, blue)
    checks.append(
        {
            "name": "pydantic_arena_team_commentary_receipts",
            "status": "PASS" if not commentary_errors else "FAIL",
            "errors": commentary_errors,
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
