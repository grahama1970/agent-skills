"""V14 durable-memory canary rooted in a retained V13 adaptive campaign."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from .adaptive_red_blue_lineage_canary import (
    _copy_public_arena,
    _judge_reviewed_generation,
    _provider_genomes,
    _read_json,
    _reviewed_manifest,
    _run_tau_harness,
    _sha,
    _write_tau_public_context,
)
from .arena_battle_proof import _write_json


SCHEMA = "battle.adaptive_memory_canary.v1"
MEMORY_COLLECTION = "lessons"
MEMORY_PROJECTION_KIND = "adaptive_memory_v14"
MEMORY_EVENT_STAGES = (
    "memory_promoted",
    "memory_written",
    "memory_recalled",
    "memory_use_acknowledged",
)
MEMORY_RECEIPT_FILES = {
    "memory_promoted": "memory-promotion-receipt.json",
    "memory_written": "memory-write-receipt.json",
    "memory_recalled": "memory-recall-receipt.json",
    "memory_use_acknowledged": "memory-use-acknowledgement.json",
}
MEMORY_RECEIPT_SCHEMAS = {
    "memory_promoted": "battle.memory_promotion_receipt.v1",
    "memory_written": "battle.memory_write_receipt.v1",
    "memory_recalled": "battle.memory_recall_receipt.v1",
    "memory_use_acknowledged": "battle.memory_use_acknowledgement.v1",
}
PROJECTION_FORBIDDEN_MARKERS = (
    "/tmp/",
    "/home/",
    "/mnt/",
    "tau-live",
    "tau-dag-run/",
    "command-loop/",
    "command-artifacts/",
    "provider-workspace",
    "reviewed/",
    "arena/private",
    "/judge/",
    "scillm",
)


def materialize_adaptive_memory_projection(
    *,
    archive_root: Path,
    fixture_id: str,
    local_fixture_path: Path,
    public_fixture_path: Path,
) -> dict[str, Any]:
    """Project one archived V14 run without rerunning any live dependency."""
    index = materialize_adaptive_memory_journal(archive_root=archive_root)
    from .normalized_adaptive_lineage_fixture import (
        build_normalized_adaptive_fixture,
        write_fixture_copies,
    )

    fixture = build_normalized_adaptive_fixture(
        campaign_root=archive_root,
        source_index_path=archive_root / "source-receipt-index.json",
        fixture_id=fixture_id,
    )
    validation = write_fixture_copies(
        fixture=fixture,
        local_path=local_fixture_path,
        public_path=public_fixture_path,
    )
    validation.update(
        {
            "projection_kind": index["projection_kind"],
            "source_run_id": index["run_id"],
            "source_receipt_count": len(index["public_receipts"]),
            "journal_sha256": _sha(archive_root / "events.jsonl"),
            "source_index_sha256": _sha(
                archive_root / "source-receipt-index.json"
            ),
        }
    )
    _write_json(
        archive_root / "normalized-adaptive-memory-validation.json", validation
    )
    return validation


def materialize_adaptive_memory_journal(
    *, archive_root: Path
) -> dict[str, Any]:
    """Write a deterministic V14 receipt-time journal and public source index."""
    archive_root = archive_root.resolve()
    top_path = archive_root / "adaptive-memory-canary-receipt.json"
    top = _read_json(top_path)
    _validate_adaptive_memory_top_receipt(top)
    top_sha256 = _sha(top_path)

    archived: dict[str, dict[str, dict[str, Any]]] = {
        team: {} for team in ("red", "blue")
    }
    source_refs: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    stage_rank = {stage: rank for rank, stage in enumerate(MEMORY_EVENT_STAGES)}
    team_rank = {"red": 0, "blue": 1}

    top_groups = {
        "memory_promoted": "promotions",
        "memory_written": "writes",
        "memory_recalled": "recalls",
        "memory_use_acknowledged": "provider_use",
    }
    for stage in MEMORY_EVENT_STAGES:
        group_name = top_groups[stage]
        top_group = top.get(group_name)
        if not isinstance(top_group, dict):
            raise RuntimeError(f"V14 receipt lacks {group_name}")
        for team in ("red", "blue"):
            path = archive_root / "memory" / team / MEMORY_RECEIPT_FILES[stage]
            receipt = _read_json(path)
            expected = top_group.get(team)
            if not isinstance(expected, dict):
                raise RuntimeError(f"V14 receipt lacks {group_name}.{team}")
            receipt_sha256 = _sha(path)
            _validate_archived_memory_receipt(
                stage=stage,
                team=team,
                receipt=receipt,
                expected=expected,
                receipt_sha256=receipt_sha256,
                run_id=str(top["run_id"]),
            )
            archived[team][stage] = receipt
            source_ref = _memory_receipt_ref(
                stage=stage,
                team=team,
                run_id=str(top["run_id"]),
                receipt=receipt,
                receipt_sha256=receipt_sha256,
            )
            source_refs.append(source_ref)
            candidates.append(
                {
                    "event_type": stage,
                    "team": team,
                    "generation": 3,
                    "created_at": _receipt_datetime(
                        receipt.get("created_at"), f"{team} {stage}"
                    ),
                    "stage_rank": stage_rank[stage],
                    "team_rank": team_rank[team],
                    "source_receipt": source_ref,
                    "payload": _public_memory_event_payload(
                        stage=stage, receipt=receipt
                    ),
                }
            )

    generation = top.get("generation_3")
    if not isinstance(generation, dict):
        raise RuntimeError("V14 receipt lacks generation_3")
    if generation.get("judge_status") != "PASS":
        raise RuntimeError("V14 Generation 3 Judge receipt is not PASS")
    pipelines = generation.get("pipelines")
    if not isinstance(pipelines, dict) or any(
        not isinstance(pipelines.get(team), dict)
        or pipelines[team].get("status") != "PASS"
        for team in ("red", "blue")
    ):
        raise RuntimeError("V14 Generation 3 pipelines are not both PASS")
    global_ref = {
        "receipt_id": str(top["run_id"]),
        "schema": str(top["schema"]),
        "sha256": top_sha256,
        "status": str(top["status"]),
        "verdict": generation.get("judge_verdict"),
    }
    source_refs.append(global_ref)
    candidates.append(
        {
            "event_type": "memory_generation_evaluated",
            "team": None,
            "generation": 3,
            "created_at": _receipt_datetime(
                top.get("created_at"), "adaptive memory canary"
            ),
            "stage_rank": len(MEMORY_EVENT_STAGES),
            "team_rank": len(team_rank),
            "source_receipt": global_ref,
            "payload": _public_memory_generation_payload(generation),
        }
    )

    candidates.sort(
        key=lambda item: (
            item["created_at"],
            item["stage_rank"],
            item["team_rank"],
            item["source_receipt"]["sha256"],
        )
    )
    base_time = candidates[0]["created_at"]
    previous_us = -1
    events: list[dict[str, Any]] = []
    run_id = str(top["run_id"])
    campaign_clock_id = f"{run_id}-receipt-created-at-clock"
    for seq, candidate in enumerate(candidates, 1):
        raw_us = max(
            0,
            int((candidate["created_at"] - base_time).total_seconds() * 1_000_000),
        )
        elapsed_us = max(raw_us, previous_us + 1)
        previous_us = elapsed_us
        events.append(
            {
                "schema": "battle.campaign_event.v1",
                "seq": seq,
                "event_id": f"{run_id}-event-{seq:04d}",
                "battle_id": str(top["battle_id"]),
                "run_id": run_id,
                "campaign_clock_id": campaign_clock_id,
                "generation": candidate["generation"],
                "team": candidate["team"],
                "event_type": candidate["event_type"],
                "timing": {
                    "source_created_at": _canonical_datetime(
                        candidate["created_at"]
                    ),
                    "source_elapsed_seconds": raw_us / 1_000_000,
                    "elapsed_seconds": elapsed_us / 1_000_000,
                    "timing_source": "receipt_created_at",
                    "projection_tie_break_applied": elapsed_us != raw_us,
                },
                "source_receipt": candidate["source_receipt"],
                "payload": candidate["payload"],
            }
        )

    expected_types = [
        *(stage for stage in MEMORY_EVENT_STAGES for _team in ("red", "blue")),
        "memory_generation_evaluated",
    ]
    actual_types = [event["event_type"] for event in events]
    if sorted(actual_types) != sorted(expected_types):
        raise RuntimeError("V14 journal does not contain the required semantic stages")
    elapsed = [event["timing"]["elapsed_seconds"] for event in events]
    if any(right <= left for left, right in zip(elapsed, elapsed[1:])):
        raise RuntimeError("V14 journal elapsed time is not strictly monotonic")

    events_path = archive_root / "events.jsonl"
    events_path.write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
        encoding="utf-8",
    )
    lifecycle = _public_memory_lifecycle(top=top, archived=archived)
    index = {
        "schema": "battle.adaptive_memory_source_receipt_index.v1",
        "projection_kind": MEMORY_PROJECTION_KIND,
        "campaign_root_id": archive_root.name,
        "battle_id": str(top["battle_id"]),
        "run_id": run_id,
        "source_run_count": 2,
        "source_campaign": _public_source_campaign(top),
        "public_receipts": source_refs,
        "selection": {
            "schema": "battle.adaptive_memory_source_selection.v1",
            "status": "PASS",
            "source_run_id": top["source_campaign"]["run_id"],
            "selection_receipt_sha256": top["source_campaign"][
                "selection_receipt_sha256"
            ],
            "selected_generations": {"red": 2, "blue": 2},
        },
        "memory_evaluation": {
            "schema": "battle.adaptive_memory_projection_evaluation.v1",
            "status": "PASS",
            "improvement_proven": False,
            "teams": {
                team: {
                    "evidence_classification": archived[team][
                        "memory_promoted"
                    ]["evidence_classification"],
                    "promotion_status": archived[team]["memory_promoted"][
                        "status"
                    ],
                    "recall_status": archived[team]["memory_recalled"]["status"],
                    "use_status": archived[team][
                        "memory_use_acknowledged"
                    ]["status"],
                }
                for team in ("red", "blue")
            },
        },
        "memory_lifecycle": lifecycle,
        "top_receipt_sha256": top_sha256,
    }
    serialized = json.dumps({"events": events, "index": index}, sort_keys=True)
    if any(marker in serialized for marker in PROJECTION_FORBIDDEN_MARKERS):
        raise RuntimeError("V14 projection exposes a raw runtime path")
    _write_json(archive_root / "source-receipt-index.json", index)
    return index


def _validate_adaptive_memory_top_receipt(receipt: dict[str, Any]) -> None:
    if receipt.get("schema") != SCHEMA:
        raise RuntimeError("archive is not a Battle V14 adaptive-memory receipt")
    if receipt.get("status") != "PASS":
        raise RuntimeError("V14 archive receipt must be PASS")
    if receipt.get("mocked") is not False or receipt.get("live") is not True:
        raise RuntimeError("V14 archive must be non-mocked and live")
    if receipt.get("fixture_fallback_used") is not False:
        raise RuntimeError("V14 archive used fixture fallback")
    if not receipt.get("battle_id") or not receipt.get("run_id"):
        raise RuntimeError("V14 archive lacks stable battle or run identity")


def _validate_archived_memory_receipt(
    *,
    stage: str,
    team: str,
    receipt: dict[str, Any],
    expected: dict[str, Any],
    receipt_sha256: str,
    run_id: str,
) -> None:
    if receipt.get("schema") != MEMORY_RECEIPT_SCHEMAS[stage]:
        raise RuntimeError(f"unexpected {team} {stage} receipt schema")
    if receipt.get("status") != "PASS" or receipt.get("team") != team:
        raise RuntimeError(f"invalid {team} {stage} receipt")
    if stage in {"memory_promoted", "memory_use_acknowledged"} and receipt.get(
        "run_id"
    ) != run_id:
        raise RuntimeError(f"{team} {stage} run identity mismatch")
    if expected.get("receipt_sha256") != receipt_sha256:
        raise RuntimeError(f"{team} {stage} receipt hash mismatch")
    _receipt_datetime(receipt.get("created_at"), f"{team} {stage}")


def _memory_receipt_ref(
    *,
    stage: str,
    team: str,
    run_id: str,
    receipt: dict[str, Any],
    receipt_sha256: str,
) -> dict[str, Any]:
    if stage == "memory_promoted":
        receipt_id = receipt.get("promotion_id")
    elif stage == "memory_use_acknowledged":
        receipt_id = receipt.get("acknowledgement_id")
    else:
        receipt_id = f"{run_id}-{team}-{stage.replace('_', '-')}"
    return {
        "receipt_id": str(receipt_id),
        "schema": str(receipt["schema"]),
        "sha256": receipt_sha256,
        "status": str(receipt["status"]),
        "verdict": None,
    }


def _public_memory_event_payload(
    *, stage: str, receipt: dict[str, Any]
) -> dict[str, Any]:
    key_sha256 = hashlib.sha256(
        str(receipt.get("memory_key") or "").encode("utf-8")
    ).hexdigest()
    if stage == "memory_promoted":
        return {
            "evidence_classification": receipt["evidence_classification"],
            "visibility_scope": receipt["visibility_scope"],
            "selected_generation": receipt["selected_generation"],
            "selection_receipt_sha256": receipt["selection_receipt_sha256"],
            "fitness_receipt_sha256": receipt["fitness_receipt_sha256"],
            "observation_receipt_sha256": receipt[
                "observation_receipt_sha256"
            ],
            "judge_receipt_sha256": receipt["judge_receipt_sha256"],
            "genome_sha256": receipt["genome_sha256"],
            "selected_artifact_sha256": receipt["selected_artifact_sha256"],
        }
    if stage == "memory_written":
        return {
            "memory_key_sha256": key_sha256,
            "memory_content_sha256": receipt["memory_content_sha256"],
            "promotion_receipt_sha256": receipt[
                "promotion_receipt_sha256"
            ],
            "request_document_sha256": receipt["request_document_sha256"],
            "live": receipt.get("live") is True,
            "mocked": receipt.get("mocked") is True,
        }
    if stage == "memory_recalled":
        return {
            "memory_key_sha256": key_sha256,
            "memory_content_sha256": receipt["memory_content_sha256"],
            "memory_write_receipt_sha256": receipt[
                "memory_write_receipt_sha256"
            ],
            "query_sha256": receipt["query_sha256"],
            "exact_match_count": receipt["exact_match_count"],
            "cross_team_items_absent": receipt["cross_team_items_absent"],
            "service_found": receipt.get("service_found") is True,
        }
    if stage == "memory_use_acknowledged":
        return {
            "memory_key_sha256": key_sha256,
            "memory_content_sha256": receipt["memory_content_sha256"],
            "memory_recall_receipt_sha256": receipt[
                "memory_recall_receipt_sha256"
            ],
            "provider_call_receipt_sha256": receipt[
                "provider_call_receipt_sha256"
            ],
            "provider_citation_count": sum(
                bool(value) for value in receipt.get("provider_citations", {}).values()
            ),
            "reused_method_count": len(receipt.get("reused_selected_methods", [])),
            "parent_genome_sha256": receipt["parent_genome_sha256"],
            "child_genome_sha256": receipt["child_genome_sha256"],
            "parent_artifact_sha256": receipt["parent_artifact_sha256"],
            "child_artifact_sha256": receipt["child_artifact_sha256"],
            "artifact_changed": receipt["artifact_changed"] is True,
            "improvement_proven": False,
        }
    raise RuntimeError(f"unsupported memory projection stage: {stage}")


def _public_memory_generation_payload(generation: dict[str, Any]) -> dict[str, Any]:
    pipelines = generation["pipelines"]
    return {
        "tau_status": generation.get("tau_status"),
        "pipelines": {
            team: {
                "status": pipelines[team]["status"],
                "selected_artifact_sha256": pipelines[team][
                    "selected_artifact_sha256"
                ],
                "handoff_sha256": pipelines[team]["handoff_sha256"],
            }
            for team in ("red", "blue")
        },
        "judge_status": generation.get("judge_status"),
        "judge_verdict": generation.get("judge_verdict"),
        "judge_receipt_sha256": generation.get("judge_receipt_sha256"),
        "improvement_proven": False,
    }


def _public_memory_lifecycle(
    *,
    top: dict[str, Any],
    archived: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    generation = top["generation_3"]
    return {
        "schema": "battle.normalized_adaptive_memory_lifecycle.v1",
        "status": "PASS",
        "source_generation": 2,
        "memory_generation": 3,
        "improvement_proven": False,
        "teams": {
            team: {
                "evidence_classification": archived[team]["memory_promoted"][
                    "evidence_classification"
                ],
                "promotion_status": archived[team]["memory_promoted"]["status"],
                "write_status": archived[team]["memory_written"]["status"],
                "recall_status": archived[team]["memory_recalled"]["status"],
                "use_status": archived[team]["memory_use_acknowledged"]["status"],
                "exact_match_count": archived[team]["memory_recalled"][
                    "exact_match_count"
                ],
                "cross_team_items_absent": archived[team]["memory_recalled"][
                    "cross_team_items_absent"
                ],
                "artifact_changed": archived[team]["memory_use_acknowledged"][
                    "artifact_changed"
                ],
                "reused_method_count": len(
                    archived[team]["memory_use_acknowledged"].get(
                        "reused_selected_methods", []
                    )
                ),
                "memory_content_sha256": archived[team]["memory_written"][
                    "memory_content_sha256"
                ],
                "parent_artifact_sha256": archived[team][
                    "memory_use_acknowledged"
                ]["parent_artifact_sha256"],
                "child_artifact_sha256": archived[team][
                    "memory_use_acknowledged"
                ]["child_artifact_sha256"],
            }
            for team in ("red", "blue")
        },
        "generation_3": _public_memory_generation_payload(generation),
    }


def _public_source_campaign(top: dict[str, Any]) -> dict[str, Any]:
    source = top.get("source_campaign")
    if not isinstance(source, dict):
        raise RuntimeError("V14 receipt lacks source_campaign")
    required = (
        "run_id",
        "campaign_receipt_sha256",
        "selection_receipt_sha256",
    )
    if any(not source.get(key) for key in required):
        raise RuntimeError("V14 source campaign binding is incomplete")
    return {key: source[key] for key in required}


def _receipt_datetime(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"{label} receipt lacks created_at")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise RuntimeError(f"{label} created_at is invalid") from exc
    if parsed.tzinfo is None:
        raise RuntimeError(f"{label} created_at lacks timezone")
    return parsed.astimezone(UTC)


def _canonical_datetime(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def run_adaptive_memory_canary(
    *,
    battle_id: str,
    source_root: Path,
    out_dir: Path,
    run_id: str,
    memory_base_url: str = "http://127.0.0.1:8601",
    docker_image: str = "python:3.12-slim",
    model: str = "gpt-5.5",
    scillm_base_url: str = "http://localhost:4001",
    timeout_s: float = 300.0,
) -> dict[str, Any]:
    """Write selected V13 evidence, recall it, and require live provider use."""
    source_root = source_root.resolve()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    source = _load_v13_source(battle_id=battle_id, source_root=source_root)

    promotions: dict[str, dict[str, Any]] = {}
    writes: dict[str, dict[str, Any]] = {}
    recalls: dict[str, dict[str, Any]] = {}
    documents: dict[str, dict[str, Any]] = {}
    with httpx.Client(
        base_url=memory_base_url,
        timeout=httpx.Timeout(30.0, connect=3.0),
    ) as client:
        health = client.get("/health")
        health.raise_for_status()
        _write_json(
            out_dir / "memory-health.json", _json_object(health.json(), "memory health")
        )
        for team in ("red", "blue"):
            promotion = build_memory_promotion_receipt(
                battle_id=battle_id,
                run_id=run_id,
                team=team,
                source=source,
            )
            promotion_path = _write_json(
                out_dir / "memory" / team / "memory-promotion-receipt.json",
                promotion,
            )
            promotion["receipt_sha256"] = _sha(promotion_path)
            promotions[team] = promotion

            document = build_memory_document(
                team=team, promotion=promotion, source=source
            )
            documents[team] = document
            write = _write_memory(
                client=client,
                team=team,
                document=document,
                promotion=promotion,
            )
            write_path = _write_json(
                out_dir / "memory" / team / "memory-write-receipt.json", write
            )
            write["receipt_sha256"] = _sha(write_path)
            writes[team] = write

            recall = _recall_memory(
                client=client,
                team=team,
                document=document,
                write=write,
            )
            recall_path = _write_json(
                out_dir / "memory" / team / "memory-recall-receipt.json", recall
            )
            recall["receipt_sha256"] = _sha(recall_path)
            recalls[team] = recall

    blocked_recalls = [
        team for team, receipt in recalls.items() if receipt["status"] != "PASS"
    ]
    if blocked_recalls:
        raise RuntimeError(
            "durable memory recall blocked before Tau dispatch: "
            + ", ".join(blocked_recalls)
        )

    generation_dir = out_dir / "generation-3"
    _copy_public_arena(source_root / "generation-1", generation_dir)
    scenario = source["scenario"]
    context_path = _write_tau_public_context(
        out_dir=generation_dir,
        battle_id=battle_id,
        run_id=f"{run_id}-g3",
        scenario=scenario,
        red_workers=1,
        blue_workers=1,
    )
    context = _read_json(context_path)
    context["summary"]["generation"] = 3
    context["team_contexts"] = {
        team: _team_memory_context(team, documents[team], recalls[team])
        for team in ("red", "blue")
    }
    for team in ("red", "blue"):
        context["summary"]["teams"][team]["objective"] = _memory_objective(
            team, documents[team], recalls[team]
        )
    _write_json(context_path, context)

    manifest_path = _run_tau_harness(
        out_dir=generation_dir,
        battle_id=battle_id,
        run_id=f"{run_id}-g3",
        scenario_id=scenario["scenario_id"],
        context_path=context_path,
        red_persona="battle-red-durable-memory-child",
        blue_persona="battle-blue-durable-memory-child",
        model=model,
        scillm_base_url=scillm_base_url,
        timeout_s=timeout_s,
        red_workers=1,
        blue_workers=1,
    )
    manifest = _read_json(manifest_path)
    parent_genomes = source["genomes"]
    genomes = _provider_genomes(
        battle_id=battle_id,
        run_id=f"{run_id}-g3",
        generation=3,
        generation_dir=generation_dir,
        manifest=manifest,
        parent_genomes=parent_genomes,
    )

    use_receipts: dict[str, dict[str, Any]] = {}
    for team in ("red", "blue"):
        use = build_memory_use_acknowledgement(
            battle_id=battle_id,
            run_id=run_id,
            team=team,
            manifest=manifest,
            genome=genomes[team],
            parent_genome=parent_genomes[team],
            document=documents[team],
            recall=recalls[team],
            parent_artifact_sha256=source["artifacts"][team]["sha256"],
        )
        use_path = _write_json(
            out_dir / "memory" / team / "memory-use-acknowledgement.json", use
        )
        use["receipt_sha256"] = _sha(use_path)
        use_receipts[team] = use

    target_identity_sha256 = source["target_identity_sha256"]
    reviewed_manifest, pipelines = _reviewed_manifest(
        battle_id=battle_id,
        run_id=f"{run_id}-g3",
        generation=3,
        generation_dir=generation_dir,
        manifest=manifest,
        target_identity_sha256=target_identity_sha256,
        docker_image=docker_image,
        genomes=genomes,
    )
    judge = _judge_reviewed_generation(
        generation_dir=generation_dir,
        scenario=scenario,
        docker_image=docker_image,
        reviewed_manifest=reviewed_manifest,
        pipelines=pipelines,
        target_identity_sha256=target_identity_sha256,
    )
    judge_path = _write_json(generation_dir / "judge" / "judge-receipt.json", judge)
    judge["receipt_sha256"] = _sha(judge_path)

    status = (
        "PASS"
        if _canary_passes(
            promotions=promotions,
            writes=writes,
            recalls=recalls,
            uses=use_receipts,
            manifest=manifest,
            pipelines=pipelines,
            judge=judge,
        )
        else "BLOCKED"
    )
    receipt = {
        "schema": SCHEMA,
        "status": status,
        "battle_id": battle_id,
        "run_id": run_id,
        "source_campaign": {
            "run_id": source["campaign"]["run_id"],
            "campaign_receipt_sha256": _sha(source_root / "campaign-receipt.json"),
            "selection_receipt_sha256": _sha(source_root / "selection-receipt.json"),
        },
        "mocked": False,
        "live": True,
        "fixture_fallback_used": False,
        "memory_service": memory_base_url,
        "memory_collection": MEMORY_COLLECTION,
        "promotions": promotions,
        "writes": writes,
        "recalls": recalls,
        "provider_use": use_receipts,
        "generation_3": {
            "tau_status": manifest.get("status"),
            "pipelines": {
                team: {
                    "status": pipelines[team]["status"],
                    "selected_artifact_sha256": pipelines[team][
                        "selected_artifact_sha256"
                    ],
                    "handoff_sha256": _sha(Path(pipelines[team]["handoff_path"])),
                }
                for team in ("red", "blue")
            },
            "judge_status": judge.get("status"),
            "judge_verdict": judge.get("verdict"),
            "judge_receipt_sha256": judge["receipt_sha256"],
        },
        "claims": {
            "proves": [
                "Battle authorized and wrote one team-scoped selected V13 memory per team.",
                "Battle recalled each memory through the live Memory service.",
                "Live Tau/SciLLM Red and Blue providers cited and used their own recalled memory.",
                "The memory-informed artifacts crossed Docker compile, review, handoff, and Judge.",
            ]
            if status == "PASS"
            else [],
            "does_not_prove": [
                "The Memory service enforces team ACLs; Battle enforces routing isolation.",
                "Either team improved because durable memory was used.",
                "Judge-confirmed Red exploit success unless the Judge verdict states it.",
                "Population-scale durable learning is production-ready.",
            ],
        },
        "created_at": _now(),
    }
    _write_json(out_dir / "adaptive-memory-canary-receipt.json", receipt)
    materialize_adaptive_memory_journal(archive_root=out_dir)
    return receipt


def build_memory_promotion_receipt(
    *, battle_id: str, run_id: str, team: str, source: dict[str, Any]
) -> dict[str, Any]:
    """Authorize one selected V13 evidence record for team-scoped durable storage."""
    fitness = source["fitness"][team]
    judge_label = fitness["components"]["judge_outcome"]["label"]
    classification = (
        "validated_negative_exploit_evidence"
        if team == "red"
        else "judge_confirmed_defense_evidence"
    )
    allowed = judge_label == "BLUE_SUCCESS" and fitness["status"] == "PASS"
    return {
        "schema": "battle.memory_promotion_receipt.v1",
        "status": "PASS" if allowed else "BLOCKED",
        "promotion_id": f"{run_id}-{team}-memory-promotion",
        "battle_id": battle_id,
        "run_id": run_id,
        "team": team,
        "visibility_scope": f"{team}_only",
        "selected_generation": 2,
        "evidence_classification": classification,
        "selection_receipt_sha256": source["selection_sha256"],
        "fitness_receipt_sha256": fitness["sha256"],
        "observation_receipt_sha256": fitness["observation_receipt_sha256"],
        "judge_receipt_sha256": fitness["judge_receipt_sha256"],
        "genome_sha256": fitness["genome_sha256"],
        "selected_artifact_sha256": fitness["selected_artifact_sha256"],
        "policy": {
            "positive_requires_judge": True,
            "negative_requires_reviewed_runtime_and_judge": True,
            "memory_is_not_outcome_authority": True,
        },
        "created_at": _now(),
    }


def build_memory_document(
    *, team: str, promotion: dict[str, Any], source: dict[str, Any]
) -> dict[str, Any]:
    genome = source["genomes"][team]
    observation = source["observations"][team]
    payload = {
        "kind": "battle_adaptive_selected_evidence",
        "battle_id": promotion["battle_id"],
        "source_run_id": source["campaign"]["run_id"],
        "team": team,
        "visibility_scope": promotion["visibility_scope"],
        "selected_generation": promotion["selected_generation"],
        "evidence_classification": promotion["evidence_classification"],
        "summary": _memory_summary(team, genome, observation),
        "strategy": {
            "selected_methods": genome["selected_methods"],
            "rejected_methods": genome["rejected_methods"],
            "parameters": genome["parameters"],
            "expected_observation": genome["expected_observation"],
        },
        "source_receipts": {
            "promotion_receipt_sha256": promotion["receipt_sha256"],
            "selection_receipt_sha256": promotion["selection_receipt_sha256"],
            "fitness_receipt_sha256": promotion["fitness_receipt_sha256"],
            "observation_receipt_sha256": promotion["observation_receipt_sha256"],
            "judge_receipt_sha256": promotion["judge_receipt_sha256"],
            "genome_sha256": promotion["genome_sha256"],
            "selected_artifact_sha256": promotion["selected_artifact_sha256"],
        },
        "tags": [
            "battle",
            "durable-memory",
            f"team:{team}",
            "battle-004",
            "v13-selected",
        ],
        "status": "current",
    }
    content_sha256 = _canonical_sha(payload)
    lesson_solution = json.dumps(
        {"summary": payload["summary"], "strategy": payload["strategy"]},
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "_key": f"battle-004-v13-{team}-g2-selected-evidence",
        **payload,
        "problem": f"What selected V13 {team} evidence should a later Battle worker recall?",
        "solution": lesson_solution,
        "content_sha256": content_sha256,
        "tags": [*payload["tags"], f"content-sha:{content_sha256}"],
        "updated_at": _now(),
    }


def build_memory_use_acknowledgement(
    *,
    battle_id: str,
    run_id: str,
    team: str,
    manifest: dict[str, Any],
    genome: dict[str, Any],
    parent_genome: dict[str, Any],
    document: dict[str, Any],
    recall: dict[str, Any],
    parent_artifact_sha256: str,
) -> dict[str, Any]:
    entry = next(item for item in manifest["teams"] if item["team"] == team)
    call = _read_json(Path(entry["scillm_call"]))
    parsed = _json_object(call.get("parsed_json"), f"{team} provider response")
    provider_text = json.dumps(parsed, sort_keys=True)
    selected = {str(value) for value in genome["selected_methods"]}
    recalled_payload = _recalled_payload(recall)
    recalled = {
        str(value) for value in recalled_payload["strategy"]["selected_methods"]
    }
    reused = sorted(selected & recalled)
    required_tokens = [
        document["_key"],
        document["content_sha256"],
        recall["receipt_sha256"],
    ]
    token_checks = {token: token in provider_text for token in required_tokens}
    artifact_sha = str(entry["materialized"]["artifact_sha256"])
    status = (
        "PASS"
        if all(token_checks.values())
        and reused
        and artifact_sha != parent_artifact_sha256
        else "BLOCKED"
    )
    return {
        "schema": "battle.memory_use_acknowledgement.v1",
        "status": status,
        "acknowledgement_id": f"{run_id}-{team}-memory-use",
        "battle_id": battle_id,
        "run_id": run_id,
        "team": team,
        "memory_key": document["_key"],
        "memory_content_sha256": document["content_sha256"],
        "memory_recall_receipt_sha256": recall["receipt_sha256"],
        "provider_call_receipt_sha256": _sha(Path(entry["scillm_call"])),
        "provider_citations": token_checks,
        "reused_selected_methods": reused,
        "parent_genome_sha256": parent_genome["sha256"],
        "child_genome_sha256": genome["sha256"],
        "parent_artifact_sha256": parent_artifact_sha256,
        "child_artifact_sha256": artifact_sha,
        "artifact_changed": artifact_sha != parent_artifact_sha256,
        "claims": {
            "proves": [
                "The provider cited the exact recalled memory key, content hash, and recall receipt.",
                "The provider retained at least one selected method from recalled memory.",
            ]
            if status == "PASS"
            else [],
            "does_not_prove": ["The recalled strategy improved Judge outcome."],
        },
        "created_at": _now(),
    }


def _load_v13_source(*, battle_id: str, source_root: Path) -> dict[str, Any]:
    campaign = _read_json(source_root / "campaign-receipt.json")
    selection_path = source_root / "selection-receipt.json"
    selection = _read_json(selection_path)
    if campaign.get("status") != "PASS" or campaign.get("mocked") is not False:
        raise RuntimeError("V13 source campaign must be non-mocked PASS")
    if campaign.get("battle_id") != battle_id or selection.get("status") != "PASS":
        raise RuntimeError("V13 source campaign identity or selection is invalid")
    selected = {
        team: selection["teams"][team]["selected_generation"]
        for team in ("red", "blue")
    }
    if selected != {"red": 2, "blue": 2}:
        raise RuntimeError("V14 currently requires both V13 Generation 2 selections")
    fitness: dict[str, dict[str, Any]] = {}
    for team in ("red", "blue"):
        fitness_path = source_root / "generation-2" / team / "fitness-vector.json"
        fitness[team] = _read_json(fitness_path)
        fitness[team]["sha256"] = _sha(fitness_path)
    observations = {
        team: _read_json(
            source_root / "generation-2" / team / "generation-observation-receipt.json"
        )
        for team in ("red", "blue")
    }
    genomes: dict[str, dict[str, Any]] = {}
    artifacts: dict[str, dict[str, str]] = {}
    for team in ("red", "blue"):
        genome_path = (
            source_root / "generation-2" / "genomes" / f"{team}-team-genome.json"
        )
        genome = _read_json(genome_path)
        genome["path"] = str(genome_path)
        genome["sha256"] = _sha(genome_path)
        genomes[team] = genome
        artifact_name = "red_exploit_submission.py" if team == "red" else "app.py"
        artifact_path = source_root / "generation-2" / "reviewed" / team / artifact_name
        artifacts[team] = {"path": str(artifact_path), "sha256": _sha(artifact_path)}
        if fitness[team]["genome_sha256"] != genome["sha256"]:
            raise RuntimeError(f"{team} selected genome hash mismatch")
        if fitness[team]["selected_artifact_sha256"] != artifacts[team]["sha256"]:
            raise RuntimeError(f"{team} selected artifact hash mismatch")
    target_path = (
        source_root / "generation-1" / "arena" / "team-public" / "target" / "app.py"
    )
    return {
        "campaign": campaign,
        "selection": selection,
        "selection_sha256": _sha(selection_path),
        "fitness": fitness,
        "observations": observations,
        "genomes": genomes,
        "artifacts": artifacts,
        "scenario": _read_json(
            source_root / "generation-1" / "arena" / "scenario.json"
        ),
        "target_identity_sha256": _sha(target_path),
    }


def _write_memory(
    *,
    client: httpx.Client,
    team: str,
    document: dict[str, Any],
    promotion: dict[str, Any],
) -> dict[str, Any]:
    response = client.post(
        "/upsert",
        json={"collection": MEMORY_COLLECTION, "documents": [document]},
    )
    response.raise_for_status()
    body = _json_object(response.json(), f"{team} memory upsert response")
    return {
        "schema": "battle.memory_write_receipt.v1",
        "status": "PASS",
        "team": team,
        "memory_key": document["_key"],
        "memory_content_sha256": document["content_sha256"],
        "collection": MEMORY_COLLECTION,
        "promotion_receipt_sha256": promotion["receipt_sha256"],
        "request_document_sha256": _canonical_sha(document),
        "service_response": body,
        "mocked": False,
        "live": True,
        "created_at": _now(),
    }


def _recall_memory(
    *, client: httpx.Client, team: str, document: dict[str, Any], write: dict[str, Any]
) -> dict[str, Any]:
    query = document["_key"]
    expected_content_tag = f"content-sha:{document['content_sha256']}"
    body: dict[str, Any] = {}
    items: list[Any] = []
    matches: list[dict[str, Any]] = []
    for attempt in range(10):
        response = client.post(
            "/recall",
            json={
                "q": query,
                "k": 5,
                "collections": [MEMORY_COLLECTION],
                "tags": [f"team:{team}"],
                "threshold": 0.0,
            },
        )
        response.raise_for_status()
        body = _json_object(response.json(), f"{team} memory recall response")
        raw_items = body.get("items")
        if not isinstance(raw_items, list):
            raise RuntimeError("memory recall response lacks items")
        items = raw_items
        matches = [
            item
            for item in items
            if isinstance(item, dict) and item.get("_key") == document["_key"]
        ]
        if any(
            expected_content_tag in (item.get("tags") or [])
            and item.get("solution") == document["solution"]
            for item in matches
        ):
            break
        if attempt < 9:
            time.sleep(1)
    exact_matches = [
        item
        for item in matches
        if expected_content_tag in (item.get("tags") or [])
        and item.get("solution") == document["solution"]
    ]
    exact = exact_matches[0] if len(exact_matches) == 1 else None
    opposite_tag = f"team:{'blue' if team == 'red' else 'red'}"
    no_cross_team = all(
        not isinstance(item, dict) or opposite_tag not in (item.get("tags") or [])
        for item in items
    )
    status = (
        "PASS"
        if (
            exact is not None
            and expected_content_tag in (exact.get("tags") or [])
            and f"team:{team}" in (exact.get("tags") or [])
            and exact.get("solution") == document["solution"]
            and no_cross_team
        )
        else "BLOCKED"
    )
    return {
        "schema": "battle.memory_recall_receipt.v1",
        "status": status,
        "team": team,
        "memory_key": document["_key"],
        "memory_content_sha256": document["content_sha256"],
        "memory_write_receipt_sha256": write["receipt_sha256"],
        "collection": MEMORY_COLLECTION,
        "query_sha256": hashlib.sha256(query.encode()).hexdigest(),
        "service_found": body.get("found"),
        "service_confidence": body.get("confidence"),
        "exact_match_count": len(exact_matches),
        "team_filter_applied": f"team:{team}",
        "cross_team_items_absent": no_cross_team,
        "recalled_document": exact,
        "mocked": False,
        "live": True,
        "created_at": _now(),
    }


def _team_memory_context(
    team: str, document: dict[str, Any], recall: dict[str, Any]
) -> dict[str, Any]:
    recalled_payload = _recalled_payload(recall)
    return {
        "team": team,
        "durable_memory_recall": {
            "memory_key": document["_key"],
            "memory_content_sha256": document["content_sha256"],
            "memory_recall_receipt_sha256": recall["receipt_sha256"],
            "summary": recalled_payload["summary"],
            "strategy": recalled_payload["strategy"],
        },
        "authority": {
            "memory_is_design_input_only": True,
            "Battle_and_Judge_retain_outcome_authority": True,
        },
    }


def _memory_objective(
    team: str, document: dict[str, Any], recall: dict[str, Any]
) -> str:
    recalled_payload = _recalled_payload(recall)
    methods = json.dumps(
        recalled_payload["strategy"]["selected_methods"], sort_keys=True
    )
    return (
        f"Create the next {team} artifact using durable recalled memory. "
        f"In rationale and strategy_genome.mutation_origin cite memory_key={document['_key']}, "
        f"memory_sha256={document['content_sha256']}, and "
        f"recall_receipt_sha256={recall['receipt_sha256']}. "
        f"Retain at least one exact selected method from this recalled list: {methods}. "
        "Produce a changed artifact; memory is design input and does not authorize outcomes."
    )


def _memory_summary(
    team: str, genome: dict[str, Any], observation: dict[str, Any]
) -> str:
    outcome = observation.get("judge", {}).get("verdict") or "UNKNOWN"
    return (
        f"Selected V13 {team} Generation 2 strategy received Judge verdict {outcome}. "
        f"Expected observation: {genome['expected_observation']}"
    )


def _recalled_payload(recall: dict[str, Any]) -> dict[str, Any]:
    document = recall.get("recalled_document")
    if not isinstance(document, dict):
        raise RuntimeError("memory recall receipt lacks recalled document")
    try:
        payload = json.loads(str(document["solution"]))
    except (KeyError, json.JSONDecodeError) as exc:
        raise RuntimeError("recalled memory solution is not structured JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("strategy"), dict):
        raise RuntimeError("recalled memory payload lacks strategy")
    return payload


def _canary_passes(
    *,
    promotions: dict[str, dict[str, Any]],
    writes: dict[str, dict[str, Any]],
    recalls: dict[str, dict[str, Any]],
    uses: dict[str, dict[str, Any]],
    manifest: dict[str, Any],
    pipelines: dict[str, dict[str, Any]],
    judge: dict[str, Any],
) -> bool:
    collections = (promotions, writes, recalls, uses, pipelines)
    return (
        all(
            all(group[team].get("status") == "PASS" for team in ("red", "blue"))
            for group in collections
        )
        and manifest.get("status") == "PASS"
        and judge.get("status") == "PASS"
        and int(judge.get("judged_pair_count") or 0) == 1
    )


def _canonical_sha(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def _json_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must be a JSON object")
    return value


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
