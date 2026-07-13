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
