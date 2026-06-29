"""Bounded multi-round Battle v1 proof rung.

This module composes the existing single-round Docker operational runner into a
small multi-round scheduler. It proves one missing production behavior: feedback
from an earlier round is stored through memory, recalled through ``/recall``,
and used to weight the next round's warm-pond combinations.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from .arena_docker_smoke import MEMORY_BASE_URL, artifact_list, public_scenario, safe_key
from .battle_v1_operational import (
    NON_CLAIMS as OPERATIONAL_NON_CLAIMS,
    battle_execution_scope,
    run_battle_v1_operational,
)
from .receipts import utc_now, write_json


MULTIROUND_NON_CLAIMS = [
    *OPERATIONAL_NON_CLAIMS,
    "does_not_execute_unbounded_mutation_swarm",
    "does_not_prove_tau_loop_repair_cycle",
    "does_not_prove_memory_finetuning",
    "does_not_prove_live_websocket_monitoring",
]


def run_battle_v1_multiround(
    *,
    fixture_dir: Path,
    out_dir: Path,
    rounds: int = 2,
    red_persona: str = "brandon-bailey",
    blue_persona: str = "coder",
    red_workers: int = 2,
    blue_workers: int = 2,
    max_attempts: int = 4,
    tau_live: bool = False,
    tau_live_model: str = "gpt-5.5",
    memory_required: bool = True,
    memory_base_url: str = MEMORY_BASE_URL,
    research_broker: bool = True,
) -> dict[str, Any]:
    """Run a bounded multi-round Battle proof with memory feedback."""

    scenario = json.loads((fixture_dir / "scenario.json").read_text(encoding="utf-8"))
    battle_id = str(scenario.get("battle_id", fixture_dir.name))
    run_id = f"battle-v1-multiround-{uuid.uuid4().hex[:12]}"
    rounds = max(2, min(rounds, 5))

    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "battle-plan.json", public_scenario(scenario))

    previous_feedback: dict[str, Any] | None = None
    round_summaries: list[dict[str, Any]] = []
    feedback_receipts: list[dict[str, Any]] = []
    root_start = time.monotonic()

    for round_number in range(1, rounds + 1):
        round_dir = out_dir / "rounds" / f"round-{round_number:03d}"
        round_dir.mkdir(parents=True, exist_ok=True)

        pre_recall = None
        if round_number > 1:
            pre_recall = recall_round_feedback(
                battle_id=battle_id,
                run_id=run_id,
                scenario=scenario,
                round_number=round_number,
                memory_base_url=memory_base_url,
                memory_required=memory_required,
                previous_feedback=previous_feedback,
            )
            write_json(
                out_dir / "round-feedback" / f"round-{round_number:03d}-memory-recall-receipt.json",
                pre_recall,
            )
            pre_recall["artifact_path"] = (
                f"round-feedback/round-{round_number:03d}-memory-recall-receipt.json"
            )
            feedback_receipts.append(pre_recall)
            if pre_recall["status"] == "BLOCKED" and memory_required:
                return write_multiround_blocked(
                    out_dir=out_dir,
                    battle_id=battle_id,
                    run_id=run_id,
                    reason="round_feedback_recall_failed",
                    round_summaries=round_summaries,
                    feedback_receipts=feedback_receipts,
                )
            previous_feedback = pre_recall.get("feedback") if pre_recall.get("found") else previous_feedback

        round_result = run_battle_v1_operational(
            fixture_dir=fixture_dir,
            out_dir=round_dir,
            red_persona=red_persona,
            blue_persona=blue_persona,
            red_workers=red_workers,
            blue_workers=blue_workers,
            max_attempts=max_attempts,
            tau_live=tau_live,
            tau_live_model=tau_live_model,
            memory_required=memory_required,
            memory_base_url=memory_base_url,
            research_broker=research_broker,
            previous_round_feedback=previous_feedback,
        )

        round_summary = summarize_round(
            root_out_dir=out_dir,
            round_dir=round_dir,
            round_number=round_number,
            round_result=round_result,
        )
        round_summaries.append(round_summary)
        write_json(out_dir / "rounds" / f"round-{round_number:03d}-summary.json", round_summary)

        if round_result.get("status") != "PASS":
            return write_multiround_blocked(
                out_dir=out_dir,
                battle_id=battle_id,
                run_id=run_id,
                reason=f"round_{round_number:03d}_failed",
                round_summaries=round_summaries,
                feedback_receipts=feedback_receipts,
            )

        feedback = build_round_feedback(
            battle_id=battle_id,
            run_id=run_id,
            scenario=scenario,
            round_number=round_number,
            round_summary=round_summary,
            red_persona=red_persona,
            blue_persona=blue_persona,
        )
        store_receipt = store_round_feedback(
            feedback=feedback,
            memory_base_url=memory_base_url,
            memory_required=memory_required,
        )
        write_json(
            out_dir / "round-feedback" / f"round-{round_number:03d}-memory-store-receipt.json",
            store_receipt,
        )
        store_receipt["artifact_path"] = (
            f"round-feedback/round-{round_number:03d}-memory-store-receipt.json"
        )
        feedback_receipts.append(store_receipt)
        if store_receipt["status"] == "BLOCKED" and memory_required:
            return write_multiround_blocked(
                out_dir=out_dir,
                battle_id=battle_id,
                run_id=run_id,
                reason="round_feedback_store_failed",
                round_summaries=round_summaries,
                feedback_receipts=feedback_receipts,
            )
        previous_feedback = feedback

    final_round = round_summaries[-1]
    negative_evidence = build_negative_evidence_receipt(
        battle_id=battle_id,
        run_id=run_id,
        round_summaries=round_summaries,
    )
    write_json(out_dir / "round-feedback" / "negative-evidence-receipt.json", negative_evidence)
    second_or_later = [item for item in round_summaries if item["round_number"] > 1]
    memory_influenced = any(
        item.get("previous_round_memory_weighted_combination_count", 0) > 0
        for item in second_or_later
    )
    true_recall_receipts = [
        item for item in feedback_receipts if item.get("schema") == "battle.round_feedback_recall_receipt.v1"
    ]
    true_recall_ok = bool(true_recall_receipts) and all(
        item.get("status") == "PASS" and item.get("found") and item.get("endpoint") == "/recall"
        for item in true_recall_receipts
    )
    negative_evidence_count = int(negative_evidence["negative_evidence_count"])
    status = "PASS" if memory_influenced and true_recall_ok and negative_evidence_count else "BLOCKED"
    run_receipt = {
        "schema": "battle.multiround_run_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "status": status,
        "verdict": final_round.get("verdict", "BLOCKED") if status == "PASS" else "BLOCKED",
        "execution": {
            **battle_execution_scope(),
            "live": "docker_multiround_memory_feedback",
            "multi_round": True,
            "memory_feedback": True,
            "tau_live": tau_live,
            "round_count": rounds,
        },
        "claim_scope": "battle_v1_bounded_multiround_memory_feedback_proof",
        "non_claims": MULTIROUND_NON_CLAIMS,
        "round_count": rounds,
        "rounds": round_summaries,
        "feedback_receipts": [receipt_path_for_feedback(item) for item in feedback_receipts],
        "negative_evidence_receipt": "round-feedback/negative-evidence-receipt.json",
        "true_recall_ok": true_recall_ok,
        "memory_influenced_round_count": len(
            [
                item
                for item in second_or_later
                if item.get("previous_round_memory_weighted_combination_count", 0) > 0
            ]
        ),
        "negative_evidence_count": negative_evidence_count,
        "duration_seconds": round(time.monotonic() - root_start, 6),
        "artifacts": artifact_list(out_dir),
        "created_at": utc_now(),
    }
    write_json(out_dir / "multi-round-receipt.json", run_receipt)
    write_json(out_dir / "run-receipt.json", run_receipt)
    write_multiround_monitor_index(out_dir=out_dir, battle_id=battle_id, scenario=scenario, receipt=run_receipt)
    run_receipt["artifacts"] = artifact_list(out_dir)
    write_json(out_dir / "multi-round-receipt.json", run_receipt)
    write_json(out_dir / "run-receipt.json", run_receipt)
    if status != "PASS":
        run_receipt["reason"] = "memory_feedback_or_negative_evidence_not_proven"
        write_json(out_dir / "run-receipt.json", run_receipt)
    return run_receipt


def summarize_round(
    *,
    root_out_dir: Path,
    round_dir: Path,
    round_number: int,
    round_result: dict[str, Any],
) -> dict[str, Any]:
    warm_pond = read_json_object(round_dir / "context" / "warm-pond-receipt.json")
    scorekeeper = read_json_object(round_dir / "scorekeeper" / "scorekeeper-receipt.json")
    scoreboard = read_json_object(round_dir / "scoreboard.json")
    selected_ids = [
        str(item.get("combination_id"))
        for item in scorekeeper.get("attempts", [])
        if item.get("combination_id")
    ]
    if not selected_ids:
        selected_ids = [
            str(item.get("combination_id"))
            for item in load_attempt_receipts(round_dir, scorekeeper)
            if item.get("combination_id")
        ]
    combinations = [
        item for item in warm_pond.get("combinations", []) if isinstance(item, dict)
    ]
    selected_set = set(selected_ids)
    passed_attempts = [
        item
        for item in load_attempt_receipts(round_dir, scorekeeper)
        if item.get("status") == "PASS"
    ]
    promoted_ids = [str(item["combination_id"]) for item in passed_attempts if item.get("combination_id")]
    unselected = [item for item in combinations if str(item.get("id")) not in selected_set]
    unselected = sorted(
        unselected,
        key=lambda item: (float(item.get("affinity", 0.0)), str(item.get("id", ""))),
    )
    negative_ids = [str(item.get("id")) for item in unselected[: max(1, min(4, len(unselected)))]]
    summary = {
        "schema": "battle.round_summary.v1",
        "round_number": round_number,
        "round_dir": str(round_dir.relative_to(root_out_dir)),
        "status": round_result.get("status"),
        "verdict": round_result.get("verdict"),
        "scoreboard": str((round_dir / "scoreboard.json").relative_to(root_out_dir)),
        "run_receipt": str((round_dir / "run-receipt.json").relative_to(root_out_dir)),
        "warm_pond": str((round_dir / "context" / "warm-pond-receipt.json").relative_to(root_out_dir)),
        "scorekeeper": str((round_dir / "scorekeeper" / "scorekeeper-receipt.json").relative_to(root_out_dir)),
        "selected_combination_ids": selected_ids,
        "promoted_combination_ids": promoted_ids,
        "negative_combination_ids": negative_ids,
        "negative_evidence_type": "unselected_low_affinity_not_promoted",
        "previous_round_memory_weighted_combination_count": warm_pond.get(
            "previous_round_memory_weighted_combination_count", 0
        ),
        "previous_round_feedback": warm_pond.get("previous_round_feedback", {}),
        "attempt_count": scorekeeper.get("attempt_count", 0),
        "passed_attempt_count": scorekeeper.get("passed_attempt_count", 0),
        "failed_attempt_count": scorekeeper.get("failed_attempt_count", 0),
        "blue_success": scoreboard.get("verdict") == "BLUE_SUCCESS",
        "created_at": utc_now(),
    }
    return summary


def load_attempt_receipts(round_dir: Path, scorekeeper: dict[str, Any]) -> list[dict[str, Any]]:
    attempts = []
    for rel in scorekeeper.get("attempt_receipts", []):
        path = round_dir / str(rel)
        if path.is_file():
            data = read_json_object(path)
            if data:
                attempts.append(data)
    return attempts


def build_round_feedback(
    *,
    battle_id: str,
    run_id: str,
    scenario: dict[str, Any],
    round_number: int,
    round_summary: dict[str, Any],
    red_persona: str,
    blue_persona: str,
) -> dict[str, Any]:
    scenario_id = str(scenario.get("scenario_id", battle_id))
    promoted_ids = [str(value) for value in round_summary.get("promoted_combination_ids", [])]
    negative_ids = [str(value) for value in round_summary.get("negative_combination_ids", [])]
    key_source = f"{run_id}:{scenario_id}:round:{round_number}:feedback"
    key = safe_key(hashlib.sha256(key_source.encode("utf-8")).hexdigest()[:24])
    token = f"battle_multiround_feedback_{key}"
    return {
        "_key": key,
        "schema": "battle.round_feedback_memory.v1",
        "kind": "battle_round_feedback",
        "source": "battle_v1_multiround",
        "feedback_token": token,
        "battle_id": battle_id,
        "run_id": run_id,
        "scenario_id": scenario_id,
        "round_number": round_number,
        "red_persona": red_persona,
        "blue_persona": blue_persona,
        "promoted_combination_ids": promoted_ids,
        "negative_combination_ids": negative_ids,
        "negative_evidence_type": round_summary.get("negative_evidence_type"),
        "problem": (
            f"{token}: Battle needs prior-round warm-pond feedback for scenario "
            f"{scenario_id} before choosing the next round's exploit and defense combinations."
        ),
        "solution": (
            f"Promote combinations {', '.join(promoted_ids[:8])}; deprioritize "
            f"low-affinity unselected combinations {', '.join(negative_ids[:8])}."
        ),
        "text": (
            f"{token} Battle multi-round feedback scenario={scenario_id} "
            f"round={round_number} promoted={' '.join(promoted_ids)} "
            f"negative={' '.join(negative_ids)} red={red_persona} blue={blue_persona}"
        ),
        "tags": [
            "battle",
            "multi_round",
            "round_feedback",
            "warm_pond",
            "mutation",
            f"battle:{battle_id}",
            f"scenario:{scenario_id}",
            f"persona:{red_persona}",
            f"persona:{blue_persona}",
        ],
        "artifact_paths": {
            "round_summary": f"rounds/round-{round_number:03d}-summary.json",
            "round_run_receipt": round_summary.get("run_receipt"),
            "warm_pond": round_summary.get("warm_pond"),
            "scorekeeper": round_summary.get("scorekeeper"),
        },
        "created_at": utc_now(),
    }


def build_negative_evidence_receipt(
    *,
    battle_id: str,
    run_id: str,
    round_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for summary in round_summaries:
        round_number = int(summary.get("round_number", 0) or 0)
        for combination_id in summary.get("negative_combination_ids", []):
            records.append(
                {
                    "round_number": round_number,
                    "combination_id": str(combination_id),
                    "negative_evidence_type": summary.get("negative_evidence_type"),
                    "reason": "not_promoted_low_affinity_or_deprioritized_by_feedback",
                    "source_round_summary": f"rounds/round-{round_number:03d}-summary.json",
                }
            )
    return {
        "schema": "battle.negative_evidence_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "status": "PASS" if records else "BLOCKED",
        "negative_evidence_count": len(records),
        "records": records,
        "claim_scope": (
            "Records unselected or deprioritized warm-pond combinations for this bounded "
            "proof. These are negative strategy signals, not necessarily failed exploit "
            "executions unless a scorekeeper attempt receipt says FAIL."
        ),
        "created_at": utc_now(),
    }


def store_round_feedback(
    *,
    feedback: dict[str, Any],
    memory_base_url: str,
    memory_required: bool,
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "schema": "battle.round_feedback_store_receipt.v1",
        "status": "PASS",
        "endpoint": "/upsert",
        "memory_base_url": memory_base_url,
        "collection": "lessons",
        "feedback_key": feedback.get("_key"),
        "feedback_token": feedback.get("feedback_token"),
        "promoted_combination_ids": feedback.get("promoted_combination_ids", []),
        "negative_combination_ids": feedback.get("negative_combination_ids", []),
        "required": memory_required,
        "created_at": utc_now(),
    }
    try:
        with httpx.Client(
            base_url=memory_base_url,
            timeout=httpx.Timeout(10.0, connect=2.0),
        ) as client:
            response = client.post(
                "/upsert",
                json={"collection": "lessons", "documents": [feedback]},
            )
            receipt["http_status"] = response.status_code
            response.raise_for_status()
            receipt["response"] = response.json()
    except Exception as exc:
        receipt["status"] = "BLOCKED" if memory_required else "SKIPPED"
        receipt["reason"] = f"round_feedback_store_failed: {type(exc).__name__}: {exc}"
    return receipt


def recall_round_feedback(
    *,
    battle_id: str,
    run_id: str,
    scenario: dict[str, Any],
    round_number: int,
    memory_base_url: str,
    memory_required: bool,
    previous_feedback: dict[str, Any] | None,
) -> dict[str, Any]:
    scenario_id = str(scenario.get("scenario_id", battle_id))
    token = str(previous_feedback.get("feedback_token", "")) if previous_feedback else ""
    query = f"{token} Battle multi-round feedback warm pond promoted negative"
    payload = {
        "q": query,
        "k": 5,
        "collections": ["lessons"],
        "tags": ["battle", "multi_round", "round_feedback", "warm_pond"],
        "threshold": 0.0,
    }
    receipt: dict[str, Any] = {
        "schema": "battle.round_feedback_recall_receipt.v1",
        "status": "PASS",
        "endpoint": "/recall",
        "memory_base_url": memory_base_url,
        "collection": "lessons",
        "battle_id": battle_id,
        "run_id": run_id,
        "round_number": round_number,
        "query": payload,
        "expected_feedback_token": token,
        "found": False,
        "item_count": 0,
        "top_keys": [],
        "attempts": [],
        "required": memory_required,
        "created_at": utc_now(),
    }
    try:
        with httpx.Client(
            base_url=memory_base_url,
            timeout=httpx.Timeout(10.0, connect=2.0),
        ) as client:
            data: dict[str, Any] = {}
            items: list[dict[str, Any]] = []
            matching: list[dict[str, Any]] = []
            selected: dict[str, Any] = {}
            for attempt in range(1, 6):
                response = client.post("/recall", json=payload)
                receipt["http_status"] = response.status_code
                response.raise_for_status()
                data = response.json()
                items = [item for item in data.get("items", []) if isinstance(item, dict)]
                matching = [
                    item
                    for item in items
                    if not token
                    or item.get("feedback_token") == token
                    or token in json.dumps(item, sort_keys=True)
                ]
                selected = matching[0] if matching else {}
                receipt["attempts"].append(
                    {
                        "attempt": attempt,
                        "found": bool(data.get("found")) and bool(selected),
                        "item_count": len(items),
                        "matching_item_count": len(matching),
                        "top_keys": [item.get("_key") for item in items[:5]],
                    }
                )
                if bool(data.get("found")) and selected:
                    break
                time.sleep(0.5)
        receipt.update(
            {
                "found": bool(data.get("found")) and bool(selected),
                "exact_token_match": bool(matching),
                "item_count": len(items),
                "matching_item_count": len(matching),
                "top_keys": [item.get("_key") for item in items[:5]],
                "meta": data.get("meta", {}),
                "feedback": normalize_feedback_item(selected, fallback=previous_feedback),
            }
        )
        if (not receipt["found"] or not receipt["exact_token_match"]) and memory_required:
            receipt["status"] = "BLOCKED"
            receipt["reason"] = "round_feedback_exact_token_not_found_by_recall"
    except Exception as exc:
        receipt["status"] = "BLOCKED" if memory_required else "SKIPPED"
        receipt["reason"] = f"round_feedback_recall_failed: {type(exc).__name__}: {exc}"
    return receipt


def normalize_feedback_item(
    item: dict[str, Any],
    *,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fallback = fallback or {}
    promoted = item.get("promoted_combination_ids") or fallback.get("promoted_combination_ids", [])
    negative = item.get("negative_combination_ids") or fallback.get("negative_combination_ids", [])
    return {
        "source": str(item.get("source", fallback.get("source", "memory_recall_lessons"))),
        "feedback_token": item.get("feedback_token", fallback.get("feedback_token")),
        "battle_id": item.get("battle_id", fallback.get("battle_id")),
        "run_id": item.get("run_id", fallback.get("run_id")),
        "scenario_id": item.get("scenario_id", fallback.get("scenario_id")),
        "round_number": item.get("round_number", fallback.get("round_number")),
        "promoted_combination_ids": [
            str(value) for value in promoted if value
        ],
        "negative_combination_ids": [
            str(value) for value in negative if value
        ],
    }


def write_multiround_blocked(
    *,
    out_dir: Path,
    battle_id: str,
    run_id: str,
    reason: str,
    round_summaries: list[dict[str, Any]],
    feedback_receipts: list[dict[str, Any]],
) -> dict[str, Any]:
    receipt = {
        "schema": "battle.multiround_run_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "status": "BLOCKED",
        "verdict": "BLOCKED",
        "reason": reason,
        "execution": {
            **battle_execution_scope(),
            "live": "docker_multiround_memory_feedback",
            "multi_round": True,
            "memory_feedback": True,
        },
        "claim_scope": "battle_v1_bounded_multiround_memory_feedback_proof",
        "non_claims": MULTIROUND_NON_CLAIMS,
        "rounds": round_summaries,
        "feedback_receipts": [receipt_path_for_feedback(item) for item in feedback_receipts],
        "artifacts": artifact_list(out_dir),
        "created_at": utc_now(),
    }
    write_json(out_dir / "multi-round-receipt.json", receipt)
    write_json(out_dir / "run-receipt.json", receipt)
    return receipt


def write_multiround_monitor_index(
    *,
    out_dir: Path,
    battle_id: str,
    scenario: dict[str, Any],
    receipt: dict[str, Any],
) -> None:
    write_json(
        out_dir / "monitor-index.json",
        {
            "schema": "battle.monitor_index.v1",
            "battle_id": battle_id,
            "campaign": "Battle v1 Multi-round",
            "scenario": scenario.get("scenario_id"),
            "title": scenario.get("title", "Battle v1 multi-round proof"),
            "status": receipt.get("status"),
            "verdict": receipt.get("verdict"),
            "players": [
                {"team": "arena", "persona": "Arena Team", "role": "target-builder", "receipt": "rounds/round-001/arena-receipt.json"},
                {"team": "red", "persona": "Red Team", "role": "async-exploit-workers", "receipt": "rounds/round-001/red/team-receipt.json"},
                {"team": "blue", "persona": "Blue Team", "role": "async-defense-workers", "receipt": "rounds/round-001/blue/team-receipt.json"},
                {"team": "judge", "persona": "Scorekeeper", "role": "objective-docker-replay", "receipt": "rounds/round-001/scorekeeper/scorekeeper-receipt.json"},
            ],
            "timeline": [
                {"stage": "round-001", "status": receipt.get("rounds", [{}])[0].get("status", "BLOCKED")},
                {"stage": "memory-feedback", "status": "PASS" if receipt.get("true_recall_ok") else "BLOCKED"},
                {"stage": "round-002", "status": receipt.get("rounds", [{}, {}])[-1].get("status", "BLOCKED")},
                {"stage": "score", "status": receipt.get("status")},
            ],
            "scoreboard": "run-receipt.json",
            "artifacts": artifact_list(out_dir),
        },
    )


def read_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def receipt_path_for_feedback(receipt: dict[str, Any]) -> str:
    if receipt.get("artifact_path"):
        return str(receipt["artifact_path"])
    schema = str(receipt.get("schema", ""))
    round_number = int(receipt.get("round_number", 0) or 0)
    if schema == "battle.round_feedback_recall_receipt.v1":
        return f"round-feedback/round-{round_number:03d}-memory-recall-receipt.json"
    if schema == "battle.round_feedback_store_receipt.v1":
        token = str(receipt.get("feedback_token", ""))
        return f"round-feedback/store-{safe_key(token) or 'unknown'}.json"
    return "round-feedback/unknown-receipt.json"
